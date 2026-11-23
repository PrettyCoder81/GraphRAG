from app.neo4j_store import Neo4jStore


def main():
    store = Neo4jStore()
    try:
        store.verify()
        print("Database summary:")
        print(store.summary())
        print("Latest transfer events:")
        for row in store.query_records("""
        MATCH (src:Wallet)-[:SENT]->(x:Transfer)-[:TO]->(dst:Wallet)
        MATCH (x)-[:OF_TOKEN]->(token:Token)
        RETURN x.tx_hash AS tx_hash, x.log_index AS log_index,
               x.timestamp AS timestamp, src.address AS from_address,
               dst.address AS to_address, token.symbol AS token, x.amount_raw AS amount_raw
        ORDER BY x.timestamp DESC LIMIT 10
        """):
            print(row)
    finally:
        store.close()


if __name__ == "__main__":
    main()
