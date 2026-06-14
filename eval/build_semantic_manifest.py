"""Collect every text the semantic eval tier needs embedded.

Walks the extended corpus and the extended eval dataset, derives the exact
retrieval query variants the answer engine will issue at run time (the
deterministic ``analyze_question`` plan — the LLM planner is not used in the
deterministic tiers), and writes them to ``eval/datasets/semantic_texts.json``.

That manifest is then embedded once on a machine with Ollama by
``eval/build_semantic_fixture.py``; the resulting fixture makes the semantic
tier fully reproducible offline.

Run (sandbox / repo root):  python eval/build_semantic_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "services" / "rag-api" / "app"))
sys.path.insert(0, str(HERE.parent / "libs" / "shared-schemas" / "python"))

from rag_api.services.query_understanding import analyze_question  # noqa: E402

CORPUS = HERE / "datasets" / "extended_corpus.json"
DATASET = HERE / "datasets" / "extended_eval.json"
OUTPUT = HERE / "datasets" / "semantic_texts.json"

# Mirror shared_schemas.embeddings._task_prefixes_for_model for nomic models.
QUERY_PREFIX = "search_query: "
DOCUMENT_PREFIX = "search_document: "


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def main() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    documents = [
        {
            "chunk_key": f"{doc['source_item_id']}#{doc.get('chunk_index', 0)}",
            "text": f"{DOCUMENT_PREFIX}{doc['chunk_text']}",
        }
        for doc in corpus["documents"]
    ]

    questions: list[str] = [case["question"] for case in dataset["answerable"]]
    questions += [probe["question"] for probe in dataset["probes"]]
    questions += [case["question"] for case in dataset["acl_ablation"]]

    queries: dict[str, dict] = {}
    for question in questions:
        analysis = analyze_question(question)
        for variant in analysis.search_queries:
            key = _sha1(variant)
            if key not in queries:
                queries[key] = {"key": key, "raw": variant, "text": f"{QUERY_PREFIX}{variant}"}

    OUTPUT.write_text(
        json.dumps(
            {
                "model": "nomic-embed-text",
                "vector_size": 768,
                "document_prefix": DOCUMENT_PREFIX,
                "query_prefix": QUERY_PREFIX,
                "documents": documents,
                "queries": sorted(queries.values(), key=lambda item: item["key"]),
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"documents: {len(documents)}  unique query variants: {len(queries)}")
    print(f"written: {OUTPUT}")


if __name__ == "__main__":
    main()
