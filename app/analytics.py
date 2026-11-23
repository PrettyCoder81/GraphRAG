from app.neo4j_store import Neo4jStore

def wallet_profile(store: Neo4jStore, address: str):
    address = address.lower()
    rows = store.query_records("""
    MATCH (w:Wallet {address: $address})
    CALL {
        WITH w
        OPTIONAL MATCH (w)-[:SENT]->(x:Transfer)
        RETURN count(x) AS outgoing_events
    }
    CALL {
        WITH w
        OPTIONAL MATCH (x:Transfer)-[:TO]->(w)
        RETURN count(x) AS incoming_events
    }
    RETURN w.address AS address, w.first_seen AS first_seen,
            w.last_seen AS last_seen, outgoing_events, incoming_events
    """, address=address)
    return rows[0] if rows else {"address": address, "found": False}

def wallet_transfers(store: Neo4jStore, address: str, limit: int = 50):
    return store.query_records("""
    MATCH (src:Wallet)-[:SENT]->(x:Transfer)-[:TO]->(dst:Wallet)
    MATCH (x)-[:OF_TOKEN]->(token:Token)
    WHERE src.address = $address OR dst.address = $address
    RETURN x.tx_hash AS tx_hash, x.log_index AS log_index,
           x.block_number AS block_number, x.timestamp AS timestamp,
           src.address AS from_address, dst.address AS to_address,
           token.symbol AS token_symbol, token.address AS token_address,
           token.decimals AS token_decimals,
           x.amount AS amount, x.amount_raw AS amount_raw
    ORDER BY x.timestamp DESC LIMIT $limit
    """, address=address.lower(), limit=max(1, min(limit, 500)))

def wallet_counterparties(store: Neo4jStore, address: str, limit: int = 50):
    return store.query_records("""
    MATCH (w:Wallet {address: $address})-[:SENT]->(x:Transfer)-[:TO]->(other:Wallet)
    RETURN other.address AS address, 'outgoing' AS direction, count(x) AS events
    UNION ALL
    MATCH (other:Wallet)-[:SENT]->(x:Transfer)-[:TO]->(w:Wallet {address: $address})
    RETURN other.address AS address, 'incoming' AS direction, count(x) AS events
    ORDER BY events DESC LIMIT $limit
    """, address=address.lower(), limit=max(1, min(limit, 200)))

def top_tokens(store: Neo4jStore, limit: int = 20):
    return store.query_records("""
    MATCH (x:Transfer)-[:OF_TOKEN]->(t:Token)
    RETURN t.address AS address, t.symbol AS symbol, t.name AS name,
           t.decimals AS decimals, count(x) AS transfer_events
    ORDER BY transfer_events DESC LIMIT $limit
    """, limit=max(1, min(limit, 100)))

def wallet_paths(store: Neo4jStore, source: str, target: str, max_hops: int = 4):
    # Relationship pattern is fixed in Cypher; max_hops is tightly bounded.
    max_hops = max(1, min(int(max_hops), 5))
    return store.query_records(f"""
    MATCH p = (s:Wallet {{address: $source}})-[:SENT|TO*1..{max_hops}]-(t:Wallet {{address: $target}})
    RETURN [n IN nodes(p) WHERE n:Wallet | n.address] AS wallets,
           length(p) AS relationship_hops
    ORDER BY relationship_hops ASC LIMIT 10
    """, source=source.lower(), target=target.lower())
