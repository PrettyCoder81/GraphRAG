import time
import threading
import requests
from app.config import ALCHEMY_RPC_URL, RPC_TIMEOUT_SECONDS, RPC_MAX_RETRIES, REQUEST_DELAY_SECONDS

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class EthereumRPC:
    def __init__(self, url: str | None = None):
        self.url = url or ALCHEMY_RPC_URL
        if not self.url or "YOUR_ALCHEMY_API_KEY" in self.url:
            raise RuntimeError("Configure ALCHEMY_RPC_URL / ALCHEMY_API_KEY in .env")
        self.session = requests.Session()
        self._rpc_id = 0
        self._lock = threading.Lock()

    def call(self, method: str, params: list):
        last_error = None
        for attempt in range(RPC_MAX_RETRIES):
            with self._lock:
                self._rpc_id += 1
                request_id = self._rpc_id
            try:
                response = self.session.post(
                    self.url,
                    json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
                    timeout=RPC_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    error = payload["error"]
                    raise RuntimeError(f"RPC {method} error {error.get('code')}: {error.get('message')}")
                if "result" not in payload:
                    raise RuntimeError(f"Malformed JSON-RPC response for {method}")
                if REQUEST_DELAY_SECONDS > 0:
                    time.sleep(REQUEST_DELAY_SECONDS)
                return payload["result"]
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= RPC_MAX_RETRIES:
                    break
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"{method} failed after {RPC_MAX_RETRIES} attempts: {last_error}") from last_error

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def block_by_number(self, number: int):
        return self.call("eth_getBlockByNumber", [hex(number), False])

    def block_by_tag(self, tag: str):
        return self.call("eth_getBlockByNumber", [tag, False])

    def finalized_block_number(self) -> int:
        try:
            block = self.block_by_tag("finalized")
            return int(block["number"], 16)
        except Exception:
            # Conservative fallback for providers that do not accept the finalized tag.
            return max(0, self.block_number() - 12)

    def find_block_at_or_after(self, target_timestamp: int, upper_block: int) -> int:
        low, high = 0, upper_block
        while low < high:
            mid = (low + high) // 2
            block = self.block_by_number(mid)
            timestamp = int(block["timestamp"], 16)
            if timestamp < target_timestamp:
                low = mid + 1
            else:
                high = mid
        return low

    def transfer_logs(self, start_block: int, end_block: int):
        if start_block > end_block:
            return []
        return self.call("eth_getLogs", [{
            "fromBlock": hex(start_block),
            "toBlock": hex(end_block),
            "topics": [TRANSFER_TOPIC],
        }])
