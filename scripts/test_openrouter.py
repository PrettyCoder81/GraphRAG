"""Verify OpenRouter chat and embedding access without connecting to Neo4j."""
from openai import OpenAI
from app.config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_CHAT_MODEL,
    OPENROUTER_EMBEDDING_MODEL, OPENROUTER_SITE_URL, OPENROUTER_APP_NAME,
    EMBEDDING_DIMENSIONS,
)


def main():
    if not OPENROUTER_API_KEY:
        raise SystemExit("Set OPENROUTER_API_KEY in .env first")

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        },
    )

    emb = client.embeddings.create(
        model=OPENROUTER_EMBEDDING_MODEL,
        input="Ethereum wallet transferred ERC-20 tokens.",
        dimensions=EMBEDDING_DIMENSIONS,
    )
    vector = emb.data[0].embedding
    print(f"Embedding OK: model={OPENROUTER_EMBEDDING_MODEL}, dimensions={len(vector)}")
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise SystemExit(
            f"Expected {EMBEDDING_DIMENSIONS} dimensions, got {len(vector)}. "
            "Do not use this vector with the current Neo4j index."
        )

    chat = client.chat.completions.create(
        model=OPENROUTER_CHAT_MODEL,
        messages=[
            {"role": "user", "content": "Reply with exactly: OpenRouter chat OK"}
        ],
        max_tokens=30,
        temperature=0,
    )
    print("Chat OK:", chat.choices[0].message.content)


if __name__ == "__main__":
    main()
