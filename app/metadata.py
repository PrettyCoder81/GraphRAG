import json
from app.config import CACHE_DIR


def _decode_abi_string(result: str | None):
    if not result or result == "0x":
        return None
    raw = bytes.fromhex(result.removeprefix("0x"))
    # Standard ABI dynamic string: offset, length, UTF-8 data.
    if len(raw) >= 64:
        offset = int.from_bytes(raw[:32], "big")
        if offset + 32 <= len(raw):
            size = int.from_bytes(raw[offset:offset + 32], "big")
            data = raw[offset + 32:offset + 32 + size]
            try:
                value = data.decode("utf-8").strip("\x00")
                if value:
                    return value
            except UnicodeDecodeError:
                pass
    # Some legacy contracts return bytes32 instead of a dynamic string.
    if len(raw) == 32:
        value = raw.rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
        return value or None
    return None


class TokenMetadata:
    def __init__(self, rpc):
        self.rpc = rpc
        self.path = CACHE_DIR / "token_metadata.json"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.cache = {}

    def get(self, address: str) -> dict:
        address = address.lower()
        if address in self.cache:
            return self.cache[address]

        def call(selector):
            try:
                return self.rpc.call("eth_call", [{"to": address, "data": selector}, "latest"])
            except Exception:
                return None

        symbol = _decode_abi_string(call("0x95d89b41")) or "UNKNOWN"
        name = _decode_abi_string(call("0x06fdde03")) or "Unknown token"
        decimals_raw = call("0x313ce567")
        try:
            decimals = int(decimals_raw, 16) if decimals_raw else 18
            if decimals > 255:
                decimals = 18
        except (TypeError, ValueError):
            decimals = 18

        value = {"symbol": symbol, "name": name, "decimals": decimals}
        self.cache[address] = value
        return value

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
        temp.replace(self.path)
