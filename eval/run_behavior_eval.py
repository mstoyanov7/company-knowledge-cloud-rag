"""Behavioural + access-control evaluation for the answer engine.

Complements the answer-level harness (`rag_evaluate`). Where that harness scores
retrieval/citation/groundedness on *answerable* cases, this script measures:

  1. Outcome distribution — for each probe, does the engine answer, hedge
     ("partially related"), ask a clarifying question, or refuse? This quantifies
     the graded behaviour described in the thesis (Chapter IV).
  2. Access-control ablation — for sensitive pages, the same question is asked by
     a persona that lacks the ACL tag and by one that has it. The denied persona
     must never retrieve or cite the restricted page; the allowed persona must.

Run (offline, deterministic — mock retriever + mock LLM):

    set RETRIEVAL_PROVIDER=mock
    set DEFAULT_LLM_PROVIDER=mock
    set SECURITY_AUDIT_ENABLED=false
    set AUTH_ENABLED=false
    set APP_DATABASE_URL=sqlite:///./.cache/eval.sqlite3
    set MOCK_CORPUS_PATH=eval/datasets/eval_corpus.json
    python eval/run_behavior_eval.py

Writes eval/results/behavior_latest.json and prints a summary.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

from shared_schemas import AnswerRequest, UserContext, get_settings

from rag_api.dependencies import get_answer_service

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "behavior_eval.json"
ANSWERABLE_DATASET = HERE / "datasets" / "company_knowledge_eval.json"
OUTPUT = HERE / "results" / "behavior_latest.json"
GUARDRAIL_KINDS = ("answered", "extractive", "hedged", "clarify", "refusal")

REFUSAL_PREFIX = "I could not find that information"
HEDGE_MARKERS = ("I couldn't find a definitive answer", "related information from the notes")
CLARIFY_MARKERS = ("I found", "not sure which one")


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
            user_id="behavior-eval",
            email="eval@example.com",
            tenant_id="local-tenant",
            acl_tags=acl_tags,
        ),
        top_k=3,
    )
    return await service.answer(request)


async def run() -> dict:
    settings = get_settings()
    service = get_answer_service(settings)
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    outcome_results = []
    for case in dataset["outcome_cases"]:
        response = await _answer(service, case["question"], case["acl_tags"])
        outcome = classify_outcome(response)
        outcome_results.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "expected_outcome": case["expected_outcome"],
                "actual_outcome": outcome,
                "match": outcome == case["expected_outcome"],
                "cited_ids": [c.source_item_id for c in response.citations],
            }
        )

    acl_results = []
    for case in dataset["acl_ablation"]:
        target = case["target_source_item_id"]
        denied = await _answer(service, case["question"], case["denied_acl_tags"])
        allowed = await _answer(service, case["question"], case["allowed_acl_tags"])
        denied_ids = [c.source_item_id for c in denied.citations]
        allowed_ids = [c.source_item_id for c in allowed.citations]
        acl_results.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "target_source_item_id": target,
                "denied_persona": {
                    "acl_tags": case["denied_acl_tags"],
                    "cited_ids": denied_ids,
                    "target_leaked": target in denied_ids,
                    "filtered_count": denied.retrieval_meta.filtered_count,
                    "outcome": classify_outcome(denied),
                },
                "allowed_persona": {
                    "acl_tags": case["allowed_acl_tags"],
                    "cited_ids": allowed_ids,
                    "target_retrieved": target in allowed_ids,
                },
            }
        )

    # Guardrail-firing distribution: tally the pipeline's own answer_kind marker
    # (which uniquely identifies the 4.3.3 "replaced by source extract" outcome)
    # across every answerable case plus the behavioural probes.
    guardrail_counter: Counter = Counter()
    guardrail_cases = []
    answerable = json.loads(ANSWERABLE_DATASET.read_text(encoding="utf-8"))
    for case in answerable["cases"]:
        response = await _answer(service, case["question"], case["user_context"]["acl_tags"])
        kind = getattr(response.metadata, "answer_kind", None) or "answered"
        guardrail_counter[kind] += 1
        guardrail_cases.append({"case_id": case["case_id"], "answer_kind": kind})
    for case in dataset["outcome_cases"]:
        response = await _answer(service, case["question"], case["acl_tags"])
        kind = getattr(response.metadata, "answer_kind", None) or "answered"
        guardrail_counter[kind] += 1
        guardrail_cases.append({"case_id": case["case_id"], "answer_kind": kind})

    outcome_dist = Counter(r["actual_outcome"] for r in outcome_results)
    report = {
        "summary": {
            "outcome_case_count": len(outcome_results),
            "outcome_distribution": dict(outcome_dist),
            "guardrail_case_count": sum(guardrail_counter.values()),
            "guardrail_distribution": {kind: guardrail_counter.get(kind, 0) for kind in GUARDRAIL_KINDS},
            "outcome_match_rate": round(
                sum(r["match"] for r in outcome_results) / len(outcome_results), 4
            )
            if outcome_results
            else 0.0,
            "acl_case_count": len(acl_results),
            "acl_no_leak": all(not r["denied_persona"]["target_leaked"] for r in acl_results),
            "acl_allowed_retrieves": all(
                r["allowed_persona"]["target_retrieved"] for r in acl_results
            ),
        },
        "outcome_cases": outcome_results,
        "acl_ablation": acl_results,
        "guardrail_cases": guardrail_cases,
    }
    return report


def main() -> None:
    report = asyncio.run(run())
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    s = report["summary"]
    print("Outcome distribution:", s["outcome_distribution"])
    print("Guardrail distribution (answer_kind over", s["guardrail_case_count"], "cases):", s["guardrail_distribution"])
    print("Outcome match rate:  ", s["outcome_match_rate"])
    print("ACL: no restricted page leaked to denied persona:", s["acl_no_leak"])
    print("ACL: allowed persona retrieves the restricted page:", s["acl_allowed_retrieves"])
    for r in report["acl_ablation"]:
        d, a = r["denied_persona"], r["allowed_persona"]
        print(
            f"  {r['case_id']:24s} denied->{d['outcome']:8s} leaked={d['target_leaked']} "
            f"filtered={d['filtered_count']:2d} | allowed_retrieved={a['target_retrieved']}"
        )
    print("Saved", OUTPUT)


if __name__ == "__main__":
    main()
