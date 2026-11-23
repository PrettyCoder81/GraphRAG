from neo4j import GraphDatabase
from app.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT wallet_address IF NOT EXISTS FOR (w:Wallet) REQUIRE w.address IS UNIQUE",
    "CREATE CONSTRAINT token_address IF NOT EXISTS FOR (t:Token) REQUIRE t.address IS UNIQUE",
    "CREATE CONSTRAINT transfer_event_id IF NOT EXISTS FOR (x:Transfer) REQUIRE x.event_id IS UNIQUE",
    "CREATE CONSTRAINT transaction_hash IF NOT EXISTS FOR (t:Transaction) REQUIRE t.hash IS UNIQUE",
    "CREATE CONSTRAINT block_number IF NOT EXISTS FOR (b:Block) REQUIRE b.number IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE INDEX transfer_timestamp IF NOT EXISTS FOR (x:Transfer) ON (x.timestamp)",
    "CREATE INDEX transfer_tx_hash IF NOT EXISTS FOR (x:Transfer) ON (x.tx_hash)",
    "CREATE INDEX wallet_last_seen IF NOT EXISTS FOR (w:Wallet) ON (w.last_seen)",
]


class Neo4jStore:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
        self.database = NEO4J_DATABASE

    def verify(self):
        self.driver.verify_connectivity()

    def close(self):
        self.driver.close()

    def run(self, query: str, **params):
        with self.driver.session(database=self.database) as session:
            return list(session.run(query, **params))

    def initialize(self, vector_dimensions: int = 1536):
        for statement in SCHEMA_STATEMENTS:
            self.run(statement)
        self.run(f"""
        CREATE VECTOR INDEX document_embedding IF NOT EXISTS
        FOR (d:Document) ON (d.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {int(vector_dimensions)},
            `vector.similarity_function`: 'cosine'
        }}}}
        """)

    def write_transfers(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        query = """
        UNWIND $rows AS row
        MERGE (src:Wallet {address: row.from_address})
          ON CREATE SET src.first_seen = row.timestamp
          SET src.first_seen = CASE WHEN src.first_seen IS NULL OR row.timestamp < src.first_seen
                                    THEN row.timestamp ELSE src.first_seen END,
              src.last_seen = CASE WHEN src.last_seen IS NULL OR row.timestamp > src.last_seen
                                   THEN row.timestamp ELSE src.last_seen END
        MERGE (dst:Wallet {address: row.to_address})
          ON CREATE SET dst.first_seen = row.timestamp
          SET dst.first_seen = CASE WHEN dst.first_seen IS NULL OR row.timestamp < dst.first_seen
                                    THEN row.timestamp ELSE dst.first_seen END,
              dst.last_seen = CASE WHEN dst.last_seen IS NULL OR row.timestamp > dst.last_seen
                                   THEN row.timestamp ELSE dst.last_seen END
        MERGE (token:Token {address: row.token_address})
          ON CREATE SET token.symbol = row.symbol,
                        token.name = row.name,
                        token.decimals = row.decimals
        SET token.symbol = CASE WHEN token.symbol IS NULL OR token.symbol = 'UNKNOWN'
                                THEN row.symbol ELSE token.symbol END,
            token.name = CASE WHEN token.name IS NULL OR token.name = 'Unknown token'
                              THEN row.name ELSE token.name END,
            token.decimals = row.decimals
        MERGE (block:Block {number: row.block_number})
          ON CREATE SET block.hash = row.block_hash,
                        block.timestamp = row.timestamp
        MERGE (txn:Transaction {hash: row.tx_hash})
          ON CREATE SET txn.block_number = row.block_number,
                        txn.transaction_index = row.transaction_index
        MERGE (x:Transfer {event_id: row.event_id})
          ON CREATE SET x.tx_hash = row.tx_hash,
                        x.log_index = row.log_index,
                        x.block_number = row.block_number,
                        x.block_hash = row.block_hash,
                        x.timestamp = row.timestamp,
                        x.amount_raw = row.amount_raw,
                        x.amount_decimal = row.amount_decimal,
                        x.amount = row.amount,
                        x.removed = row.removed
        MERGE (src)-[:SENT]->(x)
        MERGE (x)-[:TO]->(dst)
        MERGE (x)-[:OF_TOKEN]->(token)
        MERGE (x)-[:EMITTED_IN]->(txn)
        MERGE (txn)-[:IN_BLOCK]->(block)
        """
        self.run(query, rows=rows)
        return len(rows)

    def query_records(self, query: str, **params):
        return [dict(record) for record in self.run(query, **params)]

    def summary(self):
        rows = self.query_records("""
        CALL { MATCH (w:Wallet) RETURN count(w) AS wallets }
        CALL { MATCH (t:Token) RETURN count(t) AS tokens }
        CALL { MATCH (x:Transfer) RETURN count(x) AS transfers,
                      min(x.timestamp) AS first_transfer_timestamp,
                      max(x.timestamp) AS last_transfer_timestamp }
        CALL { MATCH (t:Transaction) RETURN count(t) AS transactions }
        CALL { MATCH (b:Block) RETURN count(b) AS blocks }
        RETURN wallets, tokens, transfers, transactions, blocks,
               first_transfer_timestamp, last_transfer_timestamp
        """)
        return rows[0] if rows else {}
