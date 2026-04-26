from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import mean
from uuid import uuid4

from shared_schemas import (
    AppSettings,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationSummary,
)

from rag_api.dependencies import get_answer_service


class RagEvaluationHarness:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.answer_service = get_answer_service(settings)

    async def run(self, cases: list[EvaluationCase], *, dataset_path: str) -> EvaluationReport:
        results: list[EvaluationCaseResult] = []
        for case in cases:
            started = time.perf_counter()
            response = await self.answer_service.answer(
                _answer_request_from_case(case)
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            retrieved_source_ids = [citation.source_item_id for citation in response.citations]
            expected_sources = set(case.expected_source_item_ids)
            retrieved_sources = set(retrieved_source_ids)
            correct_citations = [source_id for source_id in retrieved_source_ids if source_id in expected_sources]

            citation_correctness = (
                len(correct_citations) / len(retrieved_source_ids)
                if retrieved_source_ids
                else 0.0
            )
            document_recall = (
                len(expected_sources.intersection(retrieved_sources)) / len(expected_sources)
                if expected_sources
                else 1.0
            )
            groundedness = _answer_term_score(response.answer, case.expected_answer_terms)

            results.append(
                EvaluationCaseResult(
                    case_id=case.case_id,
                    question=case.question,
                    answer=response.answer,
                    retrieved_source_item_ids=retrieved_source_ids,
                    expected_source_item_ids=case.expected_source_item_ids,
                    citation_correctness=citation_correctness,
                    document_recall=document_recall,
                    retrieval_hit=bool(expected_sources.intersection(retrieved_sources)),
                    groundedness=groundedness,
                    latency_ms=latency_ms,
                    metadata={
                        "retrieval_strategy": response.retrieval_meta.strategy,
                        "returned_count": response.retrieval_meta.returned_count,
                        "filtered_count": response.retrieval_meta.filtered_count,
                    },
                )
            )

        return EvaluationReport(
            summary=EvaluationSummary(
                run_id=f"eval-{uuid4().hex[:12]}",
                dataset_path=dataset_path,
                case_count=len(results),
                retrieval_hit_rate=_mean([1.0 if result.retrieval_hit else 0.0 for result in results]),
                mean_document_recall=_mean([result.document_recall for result in results]),
                mean_citation_correctness=_mean([result.citation_correctness for result in results]),
                mean_groundedness=_mean([result.groundedness for result in results]),
                mean_latency_ms=_mean([float(result.latency_ms) for result in results]),
            ),
            cases=results,
        )


def load_evaluation_dataset(path: str | Path) -> list[EvaluationCase]:
    dataset_path = Path(path)
    if dataset_path.suffix == ".jsonl":
        return [
            EvaluationCase.model_validate_json(line)
            for line in dataset_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("cases", [])
    return [EvaluationCase.model_validate(case) for case in raw]


def _answer_request_from_case(case: EvaluationCase):
    from shared_schemas import AnswerRequest

    return AnswerRequest(
        question=case.question,
        user_context=case.user_context,
        source_filters=case.source_filters,
        top_k=case.top_k,
    )


def _answer_term_score(answer: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    normalized = answer.lower()
    matched = sum(1 for term in expected_terms if term.lower() in normalized)
    return matched / len(expected_terms)


def _mean(values: list[float]) -> float:
    return mean(values) if values else 0.0
