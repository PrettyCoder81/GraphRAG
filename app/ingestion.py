import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.config import (
    CHECKPOINT_DIR, LOOKBACK_DAYS, LOG_BLOCK_CHUNK, INGEST_BATCH_SIZE
)
from app.decoder import decode_transfer_log, scale_amount
from app.metadata import TokenMetadata
from app.rpc import EthereumRPC


def load_json(path: str):
    from pathlib import Path
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Checkpoint JSON is invalid: {target}. Back it up or reset it.") from exc


def save_json_atomic(path, data):
    from pathlib import Path
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(target)


def fetch_range_resilient(rpc: EthereumRPC, start: int, end: int):
    """Fetch logs; on a rejected range split recursively down to individual blocks."""
    try:
        return rpc.transfer_logs(start, end)
    except Exception:
        if start >= end:
            raise
        midpoint = (start + end) // 2
        left = fetch_range_resilient(rpc, start, midpoint)
        right = fetch_range_resilient(rpc, midpoint + 1, end)
        return left + right


def determine_range(rpc: EthereumRPC, lookback_days: int):
    now = datetime.now(timezone.utc)
    start_timestamp = int((now - timedelta(days=lookback_days)).timestamp())
    end_block = rpc.finalized_block_number()
    start_block = rpc.find_block_at_or_after(start_timestamp, end_block)
    return start_block, end_block, start_timestamp


def batches(items, batch_size):
    for offset in range(0, len(items), batch_size):
        yield items[offset:offset + batch_size]


def run_ingestion(
    start_override: int | None = None,
    end_override: int | None = None,
    checkpoint_name: str = "mainnet_erc20_365d",
    reset_checkpoint: bool = False,
):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"{checkpoint_name}.json"
    checkpoint = load_json(checkpoint_path)
    if reset_checkpoint and checkpoint_path.exists():
        checkpoint_path.unlink()
        checkpoint = {}

    from app.neo4j_store import Neo4jStore

    rpc = EthereumRPC()
    if rpc.chain_id() != 1:
        raise RuntimeError(f"Expected Ethereum Mainnet chain ID 1, got {rpc.chain_id()}")

    store = Neo4jStore()
    store.verify()
    metadata = TokenMetadata(rpc)
    timestamp_cache = {}
    try:
        is_fixed_range = start_override is not None or end_override is not None
        if is_fixed_range:
            if start_override is None or end_override is None:
                raise ValueError("Pass both --start-block and --end-block for a fixed range")
            if start_override > end_override:
                raise ValueError("start block must be <= end block")
            start_block, end_block = int(start_override), int(end_override)
            window_start_timestamp = None
            expected_mode = "fixed"
        else:
            expected_mode = "rolling_365d"
            if (checkpoint.get("mode") == expected_mode
                    and checkpoint.get("lookback_days") == LOOKBACK_DAYS
                    and checkpoint.get("start_block") is not None):
                # Keep the original start block when resuming, while allowing the end to advance.
                start_block = int(checkpoint["start_block"])
                end_block = rpc.finalized_block_number()
                window_start_timestamp = checkpoint.get("window_start_timestamp")
            else:
                start_block, end_block, window_start_timestamp = determine_range(rpc, LOOKBACK_DAYS)

        can_resume = (
            checkpoint.get("mode") == expected_mode
            and checkpoint.get("start_block") == start_block
            and (not is_fixed_range or checkpoint.get("end_block") == end_block)
            and (is_fixed_range or checkpoint.get("lookback_days") == LOOKBACK_DAYS)
        )
        current_block = int(checkpoint.get("next_block", start_block)) if can_resume else start_block

        checkpoint.update({
            "network": "ethereum-mainnet",
            "mode": expected_mode,
            "lookback_days": LOOKBACK_DAYS if expected_mode == "rolling_365d" else None,
            "start_block": start_block,
            "end_block": end_block,
            "window_start_timestamp": window_start_timestamp,
            "next_block": current_block,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        save_json_atomic(checkpoint_path, checkpoint)

        total_written = 0
        chunk_size = max(1, LOG_BLOCK_CHUNK)
        while current_block <= end_block:
            chunk_start = current_block
            chunk_end = min(chunk_start + chunk_size - 1, end_block)
            logs = fetch_range_resilient(rpc, chunk_start, chunk_end)
            decoded = []
            block_numbers = sorted({int(log["blockNumber"], 16) for log in logs if not log.get("removed", False)})
            for number in block_numbers:
                block = rpc.block_by_number(number)
                timestamp_cache[number] = int(block["timestamp"], 16)

            malformed_in_chunk = 0
            malformed_examples = []
            for log in logs:
                if log.get("removed", False):
                    continue
                try:
                    row = decode_transfer_log(log)
                except (KeyError, ValueError) as exc:
                    # A topic0 match alone does not prove the contract used the
                    # canonical ERC-20 event layout. Keep the batch moving, but
                    # report enough context to investigate skipped records.
                    malformed_in_chunk += 1
                    if len(malformed_examples) < 3:
                        data = log.get("data", "")
                        data_bytes = (len(data) - 2) // 2 if isinstance(data, str) and data.startswith("0x") else -1
                        malformed_examples.append(
                            f"tx={log.get('transactionHash')} "
                            f"contract={log.get('address')} "
                            f"block={log.get('blockNumber')} "
                            f"topics={len(log.get('topics') or [])} "
                            f"data_bytes={data_bytes} reason={exc}"
                        )
                    continue
                row["timestamp"] = timestamp_cache[row["block_number"]]
                token = metadata.get(row["token_address"])
                row.update(token)
                exact_amount = scale_amount(row["amount_raw"], row["decimals"])
                row["amount_decimal"] = format(exact_amount, "f")
                row["amount"] = float(exact_amount)
                decoded.append(row)

            for batch in batches(decoded, INGEST_BATCH_SIZE):
                total_written += store.write_transfers(batch)
            metadata.save()

            # Advance only after all Neo4j batches for the chunk completed successfully.
            current_block = chunk_end + 1
            checkpoint.update({
                "end_block": end_block,
                "next_block": current_block,
                "last_completed_block": chunk_end,
                "transfer_events_written_this_run": total_written,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            save_json_atomic(checkpoint_path, checkpoint)
            print(f"Blocks {chunk_start}-{chunk_end}: "
                  f"{len(logs)} logs returned; {total_written} events written this run")
            if malformed_in_chunk:
                print(f"Skipped {malformed_in_chunk} malformed/non-standard Transfer logs in this chunk.")
                for example in malformed_examples:
                    print(f"  {example}")

        print(f"Ingestion complete: {total_written} transfer events processed.")
        print(f"Checkpoint: {checkpoint_path}")
        return total_written
    finally:
        store.close()
