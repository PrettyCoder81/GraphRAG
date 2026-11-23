from app.ingestion import fetch_range_resilient


class FakeRPC:
    def transfer_logs(self, start, end):
        if end - start > 1:
            raise RuntimeError("range too large")
        return [{"block": block} for block in range(start, end + 1)]


def test_recursive_range_split():
    logs = fetch_range_resilient(FakeRPC(), 10, 14)
    assert [item["block"] for item in logs] == [10, 11, 12, 13, 14]
