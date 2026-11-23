from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from app.neo4j_store import Neo4jStore
from app.analytics import (
    wallet_profile, wallet_transfers, wallet_counterparties,
    wallet_transaction_counts, top_tokens, wallet_paths,
)
# from app.fraud import wallet_risk
from app.rag import GraphRAG

store = Neo4jStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        store.verify()
    except Exception as exc:
        print(f"WARNING: Neo4j is not reachable at startup: {exc}")
    yield
    store.close()


app = FastAPI(
    title="Ethereum Neo4j GraphRAG API",
    description="Ethereum Mainnet ERC-20 graph analytics, exploration, heuristic risk signals and RAG.",
    version="1.0.0",
    lifespan=lifespan,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


@app.get("/")
def root():
    return {"name": "Ethereum Neo4j GraphRAG", "docs": "/docs",
            "network": "Ethereum Mainnet", "scope": "ERC-20 Transfer events",
            "historical_window": "Trailing LOOKBACK_DAYS ending at finalized block"}


@app.get("/health")
def health():
    try:
        store.verify()
        return {"status": "ok", "neo4j": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/analytics/summary")
def analytics_summary():
    try:
        return store.summary()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/analytics/top-tokens")
def analytics_top_tokens(limit: int = Query(default=20, ge=1, le=100)):
    return top_tokens(store, limit)


@app.get("/wallet/{address}")
def get_wallet(address: str):
    return wallet_profile(store, address)


@app.get("/wallet/{address}/transfers")
def get_wallet_transfers(address: str, limit: int = Query(default=50, ge=1, le=500)):
    return wallet_transfers(store, address, limit)


@app.get("/wallet/{address}/transaction-counts")
def get_wallet_transaction_counts(address: str):
    """Return exact unique transaction-hash and ERC-20 event counts."""
    return wallet_transaction_counts(store, address)


@app.get("/wallet/{address}/counterparties")
def get_wallet_counterparties(address: str, limit: int = Query(default=50, ge=1, le=200)):
    return wallet_counterparties(store, address, limit)


@app.get("/graph/paths")
def get_paths(source: str, target: str, max_hops: int = Query(default=4, ge=1, le=5)):
    return wallet_paths(store, source, target, max_hops)


# @app.get("/fraud/{address}")
# def get_fraud_indicators(address: str):
#     return wallet_risk(store, address)


@app.post("/rag/index-wallets")
def rag_index_wallets(limit: int = Query(default=100, ge=1, le=500)):
    try:
        return GraphRAG(store).index_wallets(limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/rag/ask")
def rag_ask(request: AskRequest):
    try:
        return GraphRAG(store).ask(request.question, request.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
