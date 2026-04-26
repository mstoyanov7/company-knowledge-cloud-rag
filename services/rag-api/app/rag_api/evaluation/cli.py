from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from shared_schemas import get_settings
from sync_worker.persistence import PostgresOpsStore

from rag_api.evaluation import RagEvaluationHarness, load_evaluation_dataset


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed RAG evaluation dataset.")
    parser.add_argument("--dataset", default="eval/datasets/onboarding_eval.json", help="Dataset JSON or JSONL path.")
    parser.add_argument("--output", default="eval/results/latest.json", help="Evaluation report output path.")
    parser.add_argument("--record-db", action="store_true", help="Persist the report into PostgreSQL evaluation_runs.")
    args = parser.parse_args()

    asyncio.run(_run_async(args.dataset, args.output, args.record_db))


async def _run_async(dataset_path: str, output_path: str, record_db: bool) -> None:
    settings = get_settings()
    cases = load_evaluation_dataset(dataset_path)
    report = await RagEvaluationHarness(settings).run(cases, dataset_path=dataset_path)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")

    if record_db:
        PostgresOpsStore(settings).record_evaluation_report(report)

    print(report.summary.model_dump_json(indent=2))


if __name__ == "__main__":
    run()
