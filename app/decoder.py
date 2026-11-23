from decimal import Decimal

TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa"
    "952ba7f163c4a11628f55a4df523b3ef"
)


def normalize_address(value: str) -> str:
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        raise ValueError(f"Invalid EVM address: {value!r}")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError(f"Invalid EVM address: {value!r}") from exc
    return value.lower()


def _hex_word(value: str, field: str) -> int:
    """Decode one 32-byte ABI word represented as 0x + 64 hex chars."""
    if not isinstance(value, str) or not value.startswith("0x") or len(value) != 66:
        raise ValueError(f"{field} must be exactly one 32-byte hex word")
    try:
        return int(value[2:], 16)
    except ValueError as exc:
        raise ValueError(f"{field} contains non-hex characters") from exc


def decode_topic_address(topic: str) -> str:
    if not isinstance(topic, str) or not topic.startswith("0x") or len(topic) != 66:
        raise ValueError("Indexed address topic must be exactly 32 bytes")
    raw = topic[2:]
    try:
        int(raw, 16)
    except ValueError as exc:
        raise ValueError("Indexed address topic contains non-hex characters") from exc
    # ABI-encoded address values are left-padded to 32 bytes.
    if raw[:24] != "0" * 24:
        raise ValueError("Indexed address topic has non-zero address padding")
    return normalize_address("0x" + raw[-40:])


def decode_transfer_log(log: dict) -> dict:
    """Decode a canonical ERC-20 Transfer event.

    Canonical EIP-20 layout:
      topics = [event signature, indexed from, indexed to]
      data   = uint256 amount (one 32-byte word)

    Some contracts emit the same event signature with `value` indexed. That
    non-standard layout has a fourth topic containing the amount and empty data.
    We support that layout explicitly rather than dropping those logs.
    Other layouts are rejected rather than guessed.
    """
    topics = log.get("topics") or []
    if not topics or str(topics[0]).lower() != TRANSFER_TOPIC:
        raise ValueError("Log does not have the ERC-20 Transfer event signature")

    if len(topics) < 3:
        raise ValueError("Transfer log must contain signature, from, and to topics")

    sender = decode_topic_address(topics[1])
    receiver = decode_topic_address(topics[2])
    data = log.get("data", "0x")

    if len(topics) == 3:
        # Standard EIP-20: uint256 value is a non-indexed argument in data.
        amount_raw = _hex_word(data, "ERC-20 Transfer data")
    elif len(topics) == 4 and data in ("", "0x", "0X"):
        # Alternate/non-standard layout: value is indexed as topics[3].
        amount_raw = _hex_word(topics[3], "Indexed Transfer amount")
    else:
        data_bytes = max(0, (len(data) - 2) // 2) if isinstance(data, str) else -1
        raise ValueError(
            "Unsupported Transfer event layout "
            f"(topics={len(topics)}, data_bytes={data_bytes}); "
            "expected 3 topics + 32-byte data, or 4 topics + empty data"
        )

    try:
        tx_hash = log["transactionHash"].lower()
        log_index = int(log["logIndex"], 16)
        block_number = int(log["blockNumber"], 16)
        block_hash = log["blockHash"].lower()
        transaction_index = int(log.get("transactionIndex", "0x0"), 16)
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Transfer log is missing or has invalid RPC metadata: {exc}") from exc

    return {
        "event_id": f"{tx_hash}:{log_index}",
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
        "block_hash": block_hash,
        "transaction_index": transaction_index,
        "token_address": normalize_address(log["address"]),
        "from_address": sender,
        "to_address": receiver,
        "amount_raw": str(amount_raw),
        "removed": bool(log.get("removed", False)),
    }


def scale_amount(amount_raw: str, decimals: int) -> Decimal:
    if not 0 <= int(decimals) <= 255:
        raise ValueError("ERC-20 decimals must be between 0 and 255")
    return Decimal(amount_raw) / (Decimal(10) ** int(decimals))
