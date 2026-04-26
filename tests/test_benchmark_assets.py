from __future__ import annotations

import json
from pathlib import Path


def test_benchmark_dataset_contains_required_cases_and_fields() -> None:
    dataset = json.loads(Path("benchmarks/datasets/onboarding_questions.json").read_text(encoding="utf-8"))

    assert dataset["name"] == "onboarding-benchmark-v1"
    assert len(dataset["cases"]) >= 5
    for case in dataset["cases"]:
        assert case["case_id"]
        assert case["question"]
        assert "expected_source_item_ids" in case
        assert case["user_context"]["tenant_id"]
        assert case["user_context"]["acl_tags"]


def test_k6_scenarios_exist() -> None:
    for script_name in ["smoke.js", "stress.js", "spike.js", "soak.js"]:
        script = Path("benchmarks/k6") / script_name
        assert script.exists()
        assert "chatIteration" in script.read_text(encoding="utf-8")
