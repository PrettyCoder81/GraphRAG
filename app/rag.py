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
from app.analytics import (
    wallet_profile,
    wallet_transfers,
    wallet_transaction_counts,
)
# from app.fraud import wallet_risk
from app.neo4j_store import Neo4jStore

ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")


class GraphRAG:
    def __init__(self, store: Neo4jStore):
        self.client = None
        self.store = store

    def _get_client(self):
        if self.client is None:
            if not OPENROUTER_API_KEY:
                raise RuntimeError(
                    "Set OPENROUTER_API_KEY in .env to use embedding or LLM features"
                )
            self.client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title": OPENROUTER_APP_NAME,
                },
            )
        return self.client

    def embed(self, text: str) -> list[float]:
        if not OPENROUTER_EMBEDDING_MODEL or "YOUR_" in OPENROUTER_EMBEDDING_MODEL:
            raise RuntimeError("Set OPENROUTER_EMBEDDING_MODEL to an available model slug in .env")
        response = self._get_client().embeddings.create(
            model=OPENROUTER_EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        vector = response.data[0].embedding
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSIONS}, "
                f"received {len(vector)} from {OPENROUTER_EMBEDDING_MODEL}."
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
                d.kind = 'wallet_profile',
                d.wallet_address = $address,
                d.embedding_model = $embedding_model,
                d.updated_at = datetime()
            """, id=f"wallet:{wallet['address']}", text=text,
                 embedding=vector, address=wallet["address"],
                 embedding_model=OPENROUTER_EMBEDDING_MODEL)
            indexed += 1

        return {"indexed_wallet_profiles": indexed,
                "embedding_model": OPENROUTER_EMBEDDING_MODEL}

    @staticmethod
    def _extract_content(message) -> str:
        """Normalize OpenAI-compatible text content and fail on empty output."""
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        return ""

    def _answer_count_question(self, question: str):
        """Answer exact wallet transaction/event-count questions using Cypher."""
        lower = question.lower()
        if not re.search(r"\bhow\s+many\b", lower):
            return None

        addresses = ADDRESS_RE.findall(question)
        if not addresses:
            return None

        asks_transactions = bool(re.search(r"\btransactions?\b", lower))
        asks_transfers = bool(re.search(r"\btransfers?\b", lower))
        if not (asks_transactions or asks_transfers):
            return None

        address = addresses[0].lower()
        counts = wallet_transaction_counts(self.store, address)

        if not counts.get("found"):
            answer = (
                f"I couldn't find wallet {address} in the currently indexed Neo4j graph. "
                "No count can be reported for this address in the indexed ERC-20 dataset."
            )
            return {
                "answer": answer,
                "retrieval_method": "cypher_exact_count",
                "graph_evidence": [counts],
                "retrieved_documents": [],
            }

        if asks_transactions:
            total = counts["total_transactions"]
            answer = (
                f"Wallet {address} participated in {total:,} unique Ethereum transaction "
                "hashes represented by ERC-20 Transfer events in the currently indexed "
                "dataset. Of these, {incoming:,} were incoming and {outgoing:,} were "
                "outgoing. A transaction is counted once even if it emitted multiple "
                "ERC-20 Transfer events. This is not a count of every Ethereum transaction "
                "or native ETH transfer.".format(
                    incoming=counts["incoming_transactions"],
                    outgoing=counts["outgoing_transactions"],
                )
            )
        else:
            answer = (
                f"Wallet {address} is associated with {counts['total_transfer_events']:,} "
                "unique ERC-20 Transfer events in the currently indexed dataset. "
                f"Incoming events: {counts['incoming_transfer_events']:,}; "
                f"outgoing events: {counts['outgoing_transfer_events']:,}. "
                "A single Ethereum transaction may contain multiple Transfer events."
            )

        return {
            "answer": answer,
            "retrieval_method": "cypher_exact_count",
            "graph_evidence": [counts],
            "retrieved_documents": [],
        }

    def ask(self, question: str, top_k: int = 5):
        # Exact quantitative questions should be answered from Cypher, not embeddings.
        count_result = self._answer_count_question(question)
        if count_result is not None:
            return count_result

        addresses = sorted({a.lower() for a in ADDRESS_RE.findall(question)})
        docs = []
        try:
            vector = self.embed(question)
            docs = self.store.query_records("""
            CALL db.index.vector.queryNodes('document_embedding', $top_k, $embedding)
            YIELD node, score
            RETURN node.text AS text,
                   node.wallet_address AS wallet_address,
                   score
            ORDER BY score DESC
            """, top_k=max(1, min(top_k, 20)), embedding=vector)
        except Exception:
            # If a wallet address is explicit, exact graph evidence can still be useful
            # even if the vector index is not initialized or embeddings are unavailable.
            if not addresses:
                raise

        if not docs and not addresses:
            raise RuntimeError(
                "No wallet profile embeddings were retrieved. Run POST "
                "/rag/index-wallets first, or ask a question containing a wallet address."
            )

        addresses.extend(
            d["wallet_address"] for d in docs
            if d.get("wallet_address") and d["wallet_address"] not in addresses
        )

        graph_evidence = []
        for address in addresses[:8]:
            graph_evidence.append({
                "profile": wallet_profile(self.store, address),
                # "risk_indicators": wallet_risk(self.store, address),
                "recent_transfers": wallet_transfers(self.store, address, 10),
            })

        evidence = {
            "semantic_wallet_profiles": docs,
            "graph_evidence": graph_evidence,
            "scope_note": (
                "The graph represents ERC-20 Transfer events in the ingested window; "
                "it does not represent every Ethereum transaction or native ETH transfers."
            ),
        }

        if not OPENROUTER_CHAT_MODEL or "YOUR_" in OPENROUTER_CHAT_MODEL:
            raise RuntimeError("Set OPENROUTER_CHAT_MODEL to an available model slug in .env")

        completion = self._get_client().chat.completions.create(
            model=OPENROUTER_CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an Ethereum ERC-20 graph analyst. Answer only from the "
                        "supplied retrieved evidence. Distinguish observed facts from "
                        "heuristics. Never declare an address fraudulent based only on "
                        "a heuristic score. Say when evidence is insufficient. Include "
                        "transaction hashes when available. Do not invent token prices, "
                        "wallet identities, balances, or events."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\nRetrieved evidence (JSON):\n"
                        f"{json.dumps(evidence, default=str, ensure_ascii=False)}"
                    ),
                },
            ],
            max_tokens=900,
            temperature=0.2,
        )

        if not completion.choices:
            raise RuntimeError(
                f"OpenRouter returned no choices for model {OPENROUTER_CHAT_MODEL}. "
                "Check the model slug, provider availability and account credits."
            )

        choice = completion.choices[0]
        answer = self._extract_content(choice.message)
        if not answer:
            finish_reason = getattr(choice, "finish_reason", None)
            raise RuntimeError(
                "OpenRouter returned an empty assistant message. "
                f"model={getattr(completion, 'model', OPENROUTER_CHAT_MODEL)!r}, "
                f"finish_reason={finish_reason!r}. Check model compatibility, output "
                "token limits and OpenRouter activity logs."
            )

        return {
            "answer": answer,
            "retrieval_method": "hybrid_vector_and_graph",
            "model": getattr(completion, "model", OPENROUTER_CHAT_MODEL),
            "retrieved_documents": docs,
            "graph_evidence": graph_evidence,
        }
