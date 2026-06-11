"""Run the extended (300+) deterministic evaluation.

Executes every case in eval/datasets/extended_eval.json against the answer
engine with mock providers (deterministic lexical retrieval + extractive mock
LLM), then writes per-case results and per-category aggregates.

Run (offline, deterministic):

    RETRIEVAL_PROVIDER=mock DEFAULT_LLM_PROVIDER=mock \
    SECURITY_AUDIT_ENABLED=false AUTH_ENABLED=false \
    APP_DATABASE_URL=sqlite:///./.cache/eval.sqlite3 \
    MOCK_CORPUS_PATH=eval/datasets/extended_corpus.json \
    python eval/run_extended_eval.py

Writes eval/results/extended_latest.json and prints a summary.

The work can be split into parts (--part answerable --start N --end M,
--part probes, --part acl) and merged with --part aggregate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from shared_schemas import AnswerRequest, EvaluationCase, UserContext, get_settings

from rag_api.dependencies import get_answer_service
from rag_api.evaluation.harness import RagEvaluationHarness

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "extended_eval.json"
OUTPUT = HERE / "results" / "extended_latest.json"

REFUSAL_PREFIX = "I could not find that information"
HEDGE_MARKERS = ("I couldn't find a definitive answer", "related information from the notes")
CLARIFY_MARKERS = ("I found", "not sure which one")

# Outcomes that count as "safe" for probes about knowledge that is absent or
# only adjacent: anything except a confident direct answer.
SAFE_OUTCOMES = {"refusal", "hedge", "clarify"}


def classify_outcome(response) -> str:
    answer = response.answer or ""
    if getattr(response, "clarification", None) is not None:
        return "clarify"
    if answer.startswith(REFUSAL_PREFIX):
        return "refusal"
    if any(marker in answer for marker in HEDGE_MARKERS):
        return "hedge"
    if all(marker in answer for marker in CLARIFY_MARKERS):
        return "clarify"
    return "answered"


async def _answer(service, question: str, acl_tags: list[str]):
    request = AnswerRequest(
        question=question,
        user_context=UserContext(
            user_id="eval-user",
            email="eval@example.com",
            tenant_id="local-tenant",
            acl_tags=acl_tags,
        ),
        top_k=5,
    )
    return await service.answer(request)


PARTS_DIR = HERE / "results" / "extended_parts"


async def run_answerable(dataset: dict, start: int, end: int) -> None:
    settings = get_settings()
    selected = dataset["answerable"][start:end]
    harness = RagEvaluationHarness(settings)
    cases = [
        EvaluationCase.model_validate({k: v for k, v in case.items() if k != "category"})
        for case in selected
    ]
    report = await harness.run(cases, dataset_path=str(DATASET))
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = PARTS_DIR / f"answerable_{start:03d}_{end:03d}.json"
    out.write_text(json.dumps([r.model_dump(mode="json") for r in report.cases],
                              ensure_ascii=False), encoding="utf-8")
    print(f"answerable[{start}:{end}] -> {len(report.cases)} results -> {out.name}")


async def run_probes(dataset: dict) -> None:
    settings = get_settings()
    service = get_answer_service(settings)
    probe_results = []
    for probe in dataset["probes"]:
        response = await _answer(service, probe["question"], probe["acl_tags"])
        probe_results.append({
            "case_id": probe["case_id"],
            "category": probe["category"],
            "question": probe["question"],
            "outcome": classify_outcome(response),
            "citations": [c.source_item_id for c in response.citations],
        })
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = PARTS_DIR / "probes.json"
    out.write_text(json.dumps(probe_results, ensure_ascii=False), encoding="utf-8")
    print(f"probes -> {len(probe_results)} results -> {out.name}")


async def run_acl(dataset: dict) -> None:
    settings = get_settings()
    service = get_answer_service(settings)
    acl_results = []
    for case in dataset["acl_ablation"]:
        target = case["target_source_item_id"]
        denied = await _answer(service, case["question"], case["denied_acl_tags"])
        allowed = await _answer(service, case["question"], case["allowed_acl_tags"])
        acl_results.append({
            "case_id": case["case_id"],
            "question": case["question"],
            "denied_outcome": classify_outcome(denied),
            "leaked": target in [c.source_item_id for c in denied.citations],
            "allowed_outcome": classify_outcome(allowed),
            "allowed_retrieved": target in [c.source_item_id for c in allowed.citations],
        })
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = PARTS_DIR / "acl.json"
    out.write_text(json.dumps(acl_results, ensure_ascii=False), encoding="utf-8")
    print(f"acl -> {len(acl_results)} pairs -> {out.name}")


def aggregate(dataset: dict) -> None:
    category_by_id = {case["case_id"]: case["category"] for case in dataset["answerable"]}

    answerable_cases = []
    for part in sorted(PARTS_DIR.glob("answerable_*.json")):
        answerable_cases.extend(json.loads(part.read_text(encoding="utf-8")))
    probe_cases = json.loads((PARTS_DIR / "probes.json").read_text(encoding="utf-8"))
    acl_cases = json.loads((PARTS_DIR / "acl.json").read_text(encoding="utf-8"))

    per_category: dict[str, list] = defaultdict(list)
    for result in answerable_cases:
        per_category[category_by_id[result["case_id"]]].append(result)

    def _agg(results):
        return {
            "cases": len(results),
            "retrieval_hit_rate": round(mean(1.0 if r["retrieval_hit"] else 0.0 for r in results), 4),
            "mean_reciprocal_rank": round(mean(r["reciprocal_rank"] for r in results), 4),
            "mean_groundedness": round(mean(r["groundedness"] for r in results), 4),
            "mean_citation_correctness": round(mean(r["citation_correctness"] for r in results), 4),
        }

    answerable_summary = {
        "overall": _agg(answerable_cases),
        "by_category": {cat: _agg(results) for cat, results in sorted(per_category.items())},
    }

    outcome_by_category: dict[str, Counter] = defaultdict(Counter)
    for probe in probe_cases:
        outcome_by_category[probe["category"]][probe["outcome"]] += 1
    probe_summary = {}
    for category, counts in outcome_by_category.items():
        total = sum(counts.values())
        safe = sum(n for outcome, n in counts.items() if outcome in SAFE_OUTCOMES)
        probe_summary[category] = {
            "cases": total,
            "outcomes": dict(counts),
            "safe_rate": round(safe / total, 4),
            "clarify_rate": round(counts.get("clarify", 0) / total, 4),
        }

    acl_summary = {
        "pairs": len(acl_cases),
        "executions": 2 * len(acl_cases),
        "leaks_to_denied_persona": sum(1 for c in acl_cases if c["leaked"]),
        "allowed_persona_retrievals": sum(1 for c in acl_cases if c["allowed_retrieved"]),
    }

    total_executions = len(answerable_cases) + len(probe_cases) + 2 * len(acl_cases)
    payload = {
        "dataset": dataset["name"],
        "total_executions": total_executions,
        "answerable_summary": answerable_summary,
        "probe_summary": probe_summary,
        "acl_summary": acl_summary,
        "answerable_cases": answerable_cases,
        "probe_cases": probe_cases,
        "acl_cases": acl_cases,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"TOTAL executions: {total_executions}")
    print("Answerable overall:", json.dumps(answerable_summary["overall"]))
    for cat, agg in answerable_summary["by_category"].items():
        print(f"  {cat}: {json.dumps(agg)}")
    for cat, summary in probe_summary.items():
        print(f"Probes [{cat}]: {json.dumps(summary)}")
    print("ACL:", json.dumps(acl_summary))
    print(f"Saved {OUTPUT}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=["answerable", "probes", "acl", "aggregate"],
                        default="aggregate")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=10_000)
    args = parser.parse_args()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    if args.part == "answerable":
        asyncio.run(run_answerable(dataset, args.start, args.end))
    elif args.part == "probes":
        asyncio.run(run_probes(dataset))
    elif args.part == "acl":
        asyncio.run(run_acl(dataset))
    else:
        aggregate(dataset)


if __name__ == "__main__":
    main()
