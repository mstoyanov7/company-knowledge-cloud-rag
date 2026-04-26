from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a k6 JSON summary into the Phase 7 CSV template format.")
    parser.add_argument("summary_json", help="Path to a k6 summary JSON file.")
    parser.add_argument("--output", default="benchmarks/results/k6-summary.csv", help="Output CSV path.")
    parser.add_argument("--run-id", default="", help="Benchmark run identifier.")
    parser.add_argument("--scenario", default="", help="Scenario name, for example smoke or stress.")
    parser.add_argument("--tool", default="k6", help="Tool name.")
    args = parser.parse_args()

    data = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    row = {
        "run_id": args.run_id,
        "date": "",
        "scenario": args.scenario,
        "tool": args.tool,
        "users_or_vus": "",
        "duration_seconds": "",
        "requests": _value(metrics, "http_reqs", "count"),
        "throughput_rps": _value(metrics, "http_reqs", "rate"),
        "failure_rate": _value(metrics, "rag_failure_rate", "rate") or _value(metrics, "http_req_failed", "rate"),
        "http_p50_ms": _value(metrics, "http_req_duration", "p(50)"),
        "http_p95_ms": _value(metrics, "http_req_duration", "p(95)"),
        "http_p99_ms": _value(metrics, "http_req_duration", "p(99)"),
        "answer_p50_ms": _value(metrics, "rag_answer_latency_ms", "p(50)"),
        "answer_p95_ms": _value(metrics, "rag_answer_latency_ms", "p(95)"),
        "answer_p99_ms": _value(metrics, "rag_answer_latency_ms", "p(99)"),
        "retrieval_p50_ms": _value(metrics, "rag_retrieval_latency_ms", "p(50)"),
        "retrieval_p95_ms": _value(metrics, "rag_retrieval_latency_ms", "p(95)"),
        "retrieval_p99_ms": _value(metrics, "rag_retrieval_latency_ms", "p(99)"),
        "completion_p50_ms": _value(metrics, "rag_completion_latency_ms", "p(50)"),
        "completion_p95_ms": _value(metrics, "rag_completion_latency_ms", "p(95)"),
        "completion_p99_ms": _value(metrics, "rag_completion_latency_ms", "p(99)"),
        "freshness_p50_ms": _value(metrics, "rag_freshness_delay_ms", "p(50)"),
        "freshness_p95_ms": _value(metrics, "rag_freshness_delay_ms", "p(95)"),
        "freshness_p99_ms": _value(metrics, "rag_freshness_delay_ms", "p(99)"),
        "avg_citation_count": _value(metrics, "rag_citation_count", "avg"),
        "notes": "",
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    print(f"Wrote {output}")


def _value(metrics: dict, metric_name: str, field_name: str):
    values = (metrics.get(metric_name) or {}).get("values") or {}
    return values.get(field_name, "")


if __name__ == "__main__":
    main()
