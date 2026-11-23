
from datetime import datetime, timedelta, timezone
from ethereum_client import rpc_call

TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa"
    "952ba7f163c4a11628f55a4df523b3ef"
)

def find_start_block(rpc, target_timestamp, latest_block):
    low = 0
    high = latest_block

    while low < high:
        mid = (low + high) // 2

        print(low, high)

        block = rpc(
            "eth_getBlockByNumber",
            [hex(mid), False]
        )

        timestamp = int(block["timestamp"], 16)

        if timestamp < target_timestamp:
            low = mid + 1
        else:
            high = mid

    return low

if __name__ == '__main__':

    chain_id = rpc_call('eth_chainId', [])
    latest_block = rpc_call("eth_blockNumber", [])

    # calculate the date timestamp
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=365)
    target_timestamp = int(start_date.timestamp())

    start_block = find_start_block(
        rpc_call,
        target_timestamp,
        int(latest_block, 16)
    )

    finalized = rpc_call(
        "eth_getBlockByNumber",
        ["finalized", False]
    )

    end_block = int(finalized["number"], 16)

    print("Chain ID:", int(chain_id, 16))
    print("Latest block:", int(latest_block, 16))
    print("Start block:", start_block)
    print("End block:", end_block)


    logs = rpc_call(
        "eth_getLogs",
        [{
            "fromBlock": hex(start_block),
            "toBlock": hex(end_block),

            "topics": [
                TRANSFER_TOPIC
            ]
        }]
    )