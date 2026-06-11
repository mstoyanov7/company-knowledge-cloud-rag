"""Real end-to-end scenario testing against the running rag-api.

Sends realistic questions to the live /api/v1/answer endpoint, which retrieves from
the real OneNote index in Qdrant (nomic-embed-text embeddings) and generates answers
with the configured LLM (gpt-oss:120b-cloud via Ollama). Captures the retrieved
context, the answer, latency split, and a pass/partial/fail verdict per scenario.

Prereqs: the stack is up (docker compose) and rag-api is healthy on RAG_API_PORT.

Run:
    python eval/run_live_scenarios.py

Writes eval/results/live_scenarios.json and eval/live-scenarios.md (thesis evidence).
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE / "datasets" / "live_scenarios.json"
OUT_JSON = HERE / "results" / "live_scenarios.json"
OUT_MD = HERE / "live-scenarios.md"

API_URL = "http://localhost:8081/api/v1/answer"
API_KEY = "cloudrag-rag-key"

REFUSAL_PREFIX = "I could not find that information"
HEDGE_MARKERS = ("I couldn't find", "here's what I found elsewhere", "related information")
CLARIFY_MARKERS = ("I found", "not sure which one")


def classify(payload: dict) -> str:
    answer = payload.get("answer", "") or ""
    if payload.get("clarification"):
        return "clarify"
    if all(m in answer for m in CLARIFY_MARKERS):
        return "clarify"
    if answer.startswith(REFUSAL_PREFIX):
        return "refusal"
    if any(m in answer for m in HEDGE_MARKERS):
        return "hedge"
    return "answered"


def call_api(scenario: dict) -> dict:
    body = {
        "question": scenario["question"],
        "user_context": {
            "user_id": "defense-eval",
            "email": "defense@example.com",
            "tenant_id": "local-tenant",
            "acl_tags": scenario["acl_tags"],
        },
        "answer_depth": "normal",
        "top_k": 4,
    }
    if scenario.get("topic_id"):
        body["topic_id"] = scenario["topic_id"]
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json", "X-RAG-API-Key": API_KEY},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    payload["_wall_ms"] = int((time.perf_counter() - started) * 1000)
    return payload


def evaluate(scenario: dict, outcome: str, cited_titles: list[str]) -> str:
    want = scenario["expected_behavior"]
    expected_page = scenario.get("expected_page")
    cited_match = any(expected_page.lower() in t.lower() for t in cited_titles) if expected_page else False

    if want == "answered":
        if outcome == "answered" and cited_match:
            return "PASS"
        if outcome in {"answered", "hedge"} and cited_match:
            return "PARTIAL"
        if outcome in {"hedge", "clarify"}:
            return "PARTIAL"
        return "FAIL"
    if want == "clarify":
        return "PASS" if outcome == "clarify" else "PARTIAL"
    if want == "refusal":
        return "PASS" if outcome in {"refusal", "hedge"} else "FAIL"
    if want == "denied":
        # denied persona must not retrieve the restricted page
        leaked = any("on call" in t.lower() or "on-call" in t.lower() for t in cited_titles)
        return "PASS" if (outcome in {"refusal", "hedge", "clarify"} and not leaked) else "FAIL"
    return "?"


def main() -> None:
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    results = []
    for sc in scenarios:
        try:
            payload = call_api(sc)
        except Exception as exc:  # noqa: BLE001
            results.append({**sc, "error": str(exc)})
            print(f"{sc['id']} {sc['name']}: ERROR {exc}")
            continue
        outcome = classify(payload)
        citations = payload.get("citations", [])
        cited_titles = [c["title"] for c in citations]
        meta = payload.get("metadata", {})
        verdict = evaluate(sc, outcome, cited_titles)
        record = {
            "id": sc["id"],
            "name": sc["name"],
            "category": sc["category"],
            "question": sc["question"],
            "topic_id": sc.get("topic_id"),
            "acl_tags": sc["acl_tags"],
            "expected_page": sc.get("expected_page"),
            "expected_behavior": sc["expected_behavior"],
            "criteria": sc["criteria"],
            "outcome": outcome,
            "verdict": verdict,
            "answer": payload.get("answer", ""),
            "cited_titles": cited_titles,
            "citations": [
                {"title": c["title"], "section_path": c.get("section_path"), "snippet": c.get("snippet", "")[:200]}
                for c in citations
            ],
            "retrieval_strategy": payload.get("retrieval_meta", {}).get("strategy"),
            "returned_count": meta.get("retrieved_chunk_count"),
            "retrieval_latency_ms": meta.get("retrieval_latency_ms"),
            "completion_latency_ms": meta.get("completion_latency_ms"),
            "duration_ms": meta.get("duration_ms"),
        }
        results.append(record)
        print(f"{sc['id']} {sc['name']:42s} -> {outcome:8s} [{verdict:7s}] cites={cited_titles}")

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    verdicts = [r.get("verdict") for r in results if "verdict" in r]
    summary = {v: verdicts.count(v) for v in ("PASS", "PARTIAL", "FAIL")}
    write_markdown(results, summary)
    print("\nSummary:", summary)
    print("Saved", OUT_JSON, "and", OUT_MD)


def write_markdown(results: list[dict], summary: dict) -> None:
    lines = [
        "# Real end-to-end scenario testing — live OneNote index",
        "",
        "Generated by `eval/run_live_scenarios.py` against the running `rag-api`",
        "(Qdrant + `nomic-embed-text` retrieval, `gpt-oss:120b-cloud` generation) over the",
        "real OneNote content (54 pages + 19 attachments, 10 sections).",
        "",
        f"**Verdicts:** PASS {summary.get('PASS',0)} · PARTIAL {summary.get('PARTIAL',0)} · FAIL {summary.get('FAIL',0)} "
        f"(of {len(results)} scenarios)",
        "",
    ]
    for r in results:
        if "error" in r:
            lines += [f"## {r['id']} — {r['name']} (ERROR: {r['error']})", ""]
            continue
        lat = f"{r['retrieval_latency_ms']} ms retrieval + {r['completion_latency_ms']} ms generation"
        lines += [
            f"## {r['id']} — {r['name']}  ·  **{r['verdict']}**",
            "",
            f"- **Category:** {r['category']}  |  **topic:** {r['topic_id'] or '(none)'}  |  **acl:** {', '.join(r['acl_tags'])}",
            f"- **User question:** {r['question']}",
            f"- **Retrieved context:** {', '.join(r['cited_titles']) or '(none retrieved)'}",
            f"- **Outcome:** {r['outcome']}  |  **latency:** {lat}",
            f"- **Expected / criteria:** {r['criteria']}",
            "",
            "**Chatbot answer:**",
            "",
            "> " + (r["answer"][:700].replace("\n", "\n> ") if r["answer"] else "(empty)"),
            "",
        ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
