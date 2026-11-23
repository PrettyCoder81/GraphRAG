from app.config import EMBEDDING_DIMENSIONS
from app.neo4j_store import Neo4jStore


def main():
    store = Neo4jStore()
    try:
        store.verify()
        store.initialize(EMBEDDING_DIMENSIONS)
        print("Neo4j constraints, indexes, and vector index are initialized.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
