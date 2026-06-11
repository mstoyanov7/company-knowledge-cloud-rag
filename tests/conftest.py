import os

# Unit tests must be deterministic and offline: force the lexical token-hash
# embedder regardless of what .env or the developer's environment selects, so the
# suite never reaches out to an Ollama backend. The real semantic embedder is
# exercised separately in test_ollama_embeddings.py (skipped when unreachable).
os.environ["DEFAULT_EMBEDDING_PROVIDER"] = "token-hash-v1"
os.environ["EMBEDDING_VECTOR_SIZE"] = "64"
