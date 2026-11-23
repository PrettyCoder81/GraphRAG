from app.config import OPENROUTER_BASE_URL, OPENROUTER_CHAT_MODEL, OPENROUTER_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS

def test_openrouter_defaults_are_configured():
    assert OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert OPENROUTER_CHAT_MODEL
    assert OPENROUTER_EMBEDDING_MODEL
    assert EMBEDDING_DIMENSIONS == 1536
