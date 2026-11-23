import json
import re
from openai import OpenAI

from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_CHAT_MODEL,
    OPENROUTER_EMBEDDING_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
    EMBEDDING_DIMENSIONS,
)
from app.analytics import wallet_profile, wallet_transfers
# from app.fraud import wallet_risk
from app.neo4j_store import Neo4jStore


class GraphRAG:
    """GraphRAG client using OpenRouter for both chat and embedding requests."""

    def __init__(self, store: Neo4jStore):
        if not OPENROUTER_API_KEY:
            raise RuntimeError("Set OPENROUTER_API_KEY in .env to use RAG endpoints")

        self.client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
            },
        )
        self.store = store

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=OPENROUTER_EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        vector = response.data[0].embedding
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSIONS}, "
                f"received {len(vector)} from {OPENROUTER_EMBEDDING_MODEL}. "
                "Do not store this vector in the current Neo4j index."
            )
        return vector

    def index_wallets(self, limit: int = 100):
        wallets = self.store.query_records("""
        MATCH (w:Wallet)
        CALL {
          WITH w
          OPTIONAL MATCH (w)-[:SENT]->(x:Transfer)
          RETURN count(x) AS outgoing
        }
        CALL {
          WITH w
          OPTIONAL MATCH (x:Transfer)-[:TO]->(w)
          RETURN count(x) AS incoming
        }
        RETURN w.address AS address, outgoing, incoming,
               w.first_seen AS first_seen, w.last_seen AS last_seen
        ORDER BY outgoing + incoming DESC LIMIT $limit
        """, limit=max(1, min(limit, 500)))

        indexed = 0
        for wallet in wallets:
            text = (
                f"Ethereum wallet {wallet['address']}. It has {wallet['incoming']} "
                f"observed incoming ERC-20 transfer events and {wallet['outgoing']} "
                f"outgoing ERC-20 transfer events in the indexed period. First seen "
                f"Unix timestamp: {wallet.get('first_seen')}. Last seen Unix timestamp: "
                f"{wallet.get('last_seen')}. This is an activity summary, not an identity label."
            )
            vector = self.embed(text)
            self.store.run("""
            MERGE (d:Document {id: $id})
            SET d.text = $text,
                d.embedding = $embedding,
                d.embedding_model = $embedding_model,
                d.embedding_dimensions = $embedding_dimensions,
                d.kind = 'wallet_profile',
                d.wallet_address = $address,
                d.updated_at = datetime()
            """, id=f"wallet:{wallet['address']}", text=text,
                 embedding=vector, address=wallet["address"],
                 embedding_model=OPENROUTER_EMBEDDING_MODEL,
                 embedding_dimensions=EMBEDDING_DIMENSIONS)
            indexed += 1
        return {"indexed_wallet_profiles": indexed,
                "embedding_model": OPENROUTER_EMBEDDING_MODEL,
                "embedding_dimensions": EMBEDDING_DIMENSIONS}

    def ask(self, question: str, top_k: int = 5):
        vector = self.embed(question)
        docs = self.store.query_records("""
        CALL db.index.vector.queryNodes('document_embedding', $top_k, $embedding)
        YIELD node, score
        RETURN node.text AS text, node.wallet_address AS wallet_address, score
        ORDER BY score DESC
        """, top_k=max(1, min(top_k, 20)), embedding=vector)
        if not docs:
            raise RuntimeError(
                "No wallet profile embeddings found. Call POST /rag/index-wallets first."
            )

        addresses = set(re.findall(r"0x[a-fA-F0-9]{40}", question))
        addresses.update(d["wallet_address"] for d in docs if d.get("wallet_address"))
        graph_evidence = []
        for address in sorted(addresses)[:8]:
            graph_evidence.append({
                "profile": wallet_profile(self.store, address),
                # "risk_indicators": wallet_risk(self.store, address),
                "recent_transfers": wallet_transfers(self.store, address, 10),
            })

        evidence = {
            "semantic_wallet_profiles": docs,
            "graph_evidence": graph_evidence,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an Ethereum ERC-20 graph analyst. Answer only from the "
                    "supplied retrieved evidence. Distinguish observed facts from "
                    "heuristics. Never declare an address fraudulent based only on "
                    "a heuristic score. Explain when evidence is insufficient. "
                    "Include transaction hashes when available. Do not invent token "
                    "prices, wallet identities, balances, or events."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    "Retrieved evidence (JSON):\n"
                    + json.dumps(evidence, default=str, ensure_ascii=False)
                ),
            },
        ]
        response = self.client.chat.completions.create(
            model=OPENROUTER_CHAT_MODEL,
            messages=messages,
            max_tokens=900,
            temperature=0.2,
        )
        answer = response.choices[0].message.content or ""
        return {
            "answer": answer,
            "chat_model": OPENROUTER_CHAT_MODEL,
            "embedding_model": OPENROUTER_EMBEDDING_MODEL,
            "retrieved_documents": docs,
            "graph_evidence": graph_evidence,
        }
