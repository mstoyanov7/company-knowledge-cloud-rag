from __future__ import annotations

import asyncio

from rag_api.evaluation import RagEvaluationHarness
from shared_schemas import AppSettings, EvaluationCase, UserContext


def test_evaluation_harness_records_retrieval_and_citation_metrics() -> None:
    settings = AppSettings(
        app_env="test",
        retrieval_provider="mock",
        security_audit_enabled=False,
    )
    cases = [
        EvaluationCase(
            case_id="engineering-access",
            question="What repository access should engineering teammates request?",
            expected_source_item_ids=["sp-002"],
            expected_answer_terms=["repository", "on-call"],
            user_context=UserContext(
                user_id="eval-engineer",
                email="engineer@example.com",
                tenant_id="local-tenant",
                acl_tags=["engineering"],
            ),
        )
    ]

    report = asyncio.run(RagEvaluationHarness(settings).run(cases, dataset_path="memory://test"))

    assert report.summary.case_count == 1
    assert report.summary.retrieval_hit_rate == 1.0
    assert report.summary.mean_document_recall == 1.0
    assert report.summary.mean_citation_correctness == 1.0
    assert report.cases[0].retrieved_source_item_ids == ["sp-002"]
