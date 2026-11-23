import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")
ALCHEMY_RPC_URL = (os.getenv("ALCHEMY_RPC_URL") or
                   f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
ALCHEMY_RPC_URL = ALCHEMY_RPC_URL.replace("${ALCHEMY_API_KEY}", ALCHEMY_API_KEY)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "1qaz2wsx")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# OpenRouter provides OpenAI-compatible chat and embeddings endpoints.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "qwen/qwen3.8-27b")
# Keep text-embedding-3-small initially for compatibility with the existing
# 1536-dimensional Neo4j vector index and any profiles already indexed with it.
OPENROUTER_EMBEDDING_MODEL = os.getenv(
    "OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small"
)
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Ethereum Neo4j GraphRAG")

EMBEDDING_DIMENSIONS = env_int("EMBEDDING_DIMENSIONS", 1536)

LOOKBACK_DAYS = env_int("LOOKBACK_DAYS", 20)
LOG_BLOCK_CHUNK = max(1, env_int("LOG_BLOCK_CHUNK", 10))
INGEST_BATCH_SIZE = max(1, env_int("INGEST_BATCH_SIZE", 500))
RPC_TIMEOUT_SECONDS = max(5, env_int("RPC_TIMEOUT_SECONDS", 60))
RPC_MAX_RETRIES = max(1, env_int("RPC_MAX_RETRIES", 5))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "0.05"))
CHECKPOINT_DIR = ROOT / "data" / "checkpoints"
CACHE_DIR = ROOT / "data" / "cache"
