"""Embed the semantic eval manifest with a local Ollama. RUN ON THE HOST MACHINE.

Standard library only - no repo imports, no extra packages - so it runs with
any Python 3.10+ directly on Windows where Ollama listens on localhost:11434.

    python eval\\build_semantic_fixture.py

Reads  eval/datasets/semantic_texts.json   (written by build_semantic_manifest.py)
Writes eval/datasets/semantic_fixture.json (vectors keyed by chunk / query hash)

The fixture freezes the real nomic-embed-text vectors so the semantic eval
tier is deterministic and runs offline afterwards.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "datasets" / "semantic_texts.json"
OUTPUT = HERE / "datasets" / "semantic_fixture.json"
OLLAMA_URL = "http://localhost:11434/v1/embeddings"
BATCH = 32


def _embed_batch(model: str, texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            data = sorted(payload["data"], key=lambda item: item.get("index", 0))
            return [item["embedding"] for item in data]
        except Exception as error:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"  retry after error: {error}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def main() -> None:
    if not MANIFEST.exists():
        sys.exit(f"Manifest not found: {MANIFEST} - run build_semantic_manifest.py first.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    model = manifest["model"]
    expected_size = int(manifest["vector_size"])

    def _round(vector: list[float]) -> list[float]:
        return [round(float(value), 6) for value in vector]

    documents: dict[str, list[float]] = {}
    items = manifest["documents"]
    print(f"Embedding {len(items)} document chunks with {model} ...")
    for start in range(0, len(items), BATCH):
        batch = items[start : start + BATCH]
        vectors = _embed_batch(model, [item["text"] for item in batch])
        for item, vector in zip(batch, vectors):
            if len(vector) != expected_size:
                sys.exit(f"Model returned dimension {len(vector)}, expected {expected_size}.")
            documents[item["chunk_key"]] = _round(vector)
        print(f"  documents {min(start + BATCH, len(items))}/{len(items)}")

    queries: dict[str, list[float]] = {}
    items = manifest["queries"]
    print(f"Embedding {len(items)} query variants ...")
    for start in range(0, len(items), BATCH):
        batch = items[start : start + BATCH]
        vectors = _embed_batch(model, [item["text"] for item in batch])
        for item, vector in zip(batch, vectors):
            queries[item["key"]] = _round(vector)
        if (start // BATCH) % 5 == 0 or start + BATCH >= len(items):
            print(f"  queries {min(start + BATCH, len(items))}/{len(items)}")

    OUTPUT.write_text(
        json.dumps(
            {
                "model": model,
                "vector_size": expected_size,
                "query_prefix": manifest["query_prefix"],
                "document_prefix": manifest["document_prefix"],
                "documents": documents,
                "queries": queries,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    size_mb = OUTPUT.stat().st_size / 1024 / 1024
    print(f"DONE -> {OUTPUT} ({size_mb:.1f} MB, {len(documents)} docs, {len(queries)} queries)")


if __name__ == "__main__":
    main()
