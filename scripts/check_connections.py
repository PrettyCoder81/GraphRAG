from app.rpc import EthereumRPC
from app.neo4j_store import Neo4jStore


def main():
    rpc = EthereumRPC()
    chain_id = rpc.chain_id()
    latest = rpc.block_number()
    print(f"Ethereum chain ID: {chain_id}")
    print(f"Latest block: {latest}")
    if chain_id != 1:
        raise SystemExit("RPC endpoint is not Ethereum Mainnet (expected chain ID 1).")

    store = Neo4jStore()
    try:
        store.verify()
        print("Neo4j connection: OK")
    finally:
        store.close()


if __name__ == "__main__":
    main()
