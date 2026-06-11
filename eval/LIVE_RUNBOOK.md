# Live end-to-end evaluation — runbook

The offline harness ([`answer-eval-table.md`](answer-eval-table.md)) validates the
*logic* deterministically with the mock retriever + mock LLM. This runbook produces
the **live** numbers that cannot be generated offline:

- end-to-end answer latency with a **real LLM** (Ollama), split into retrieval vs
  generation,
- retrieval quality over the full generated OneNote content pack in `generated_onenote_pages/`,
- throughput / latency **under concurrency** (k6 + Locust).

These require the running stack and (for the generated corpus) a one-time OneNote
import, which is why they are run here rather than in CI.

---

## 0. Prerequisites

```powershell
# Ollama with the models the thesis uses
ollama pull nomic-embed-text
ollama pull gpt-oss:120b-cloud      # or any OpenAI-compatible chat model

# Load-test tools (one-time)
winget install k6                   # or: choco install k6
pip install locust
```

## 1. Bring up the stack

```powershell
docker compose up -d postgres redis qdrant rag-api
# wait for health
curl http://localhost:8081/health    # RAG_API_PORT in .env is 8081
```

## 2. Ingest the corpus into Qdrant

The 75 pages in `generated_onenote_pages/` are HTML meant for OneNote. Two options:

- **A — real OneNote (what the committed numbers used):** import the folder into a
  OneNote notebook, set `ONENOTE_GRAPH_MODE=live` + the device-code auth in `.env`,
  then run a bootstrap sync:

  ```powershell
  .\scripts\start-onenote-stack.ps1 -Build -Bootstrap
  ```

- **B — mock Graph mode (smaller synthetic corpus, no auth):** set
  `ONENOTE_GRAPH_MODE=mock` and run the bootstrap job; this seeds Qdrant with the
  sample pages served by the mock Graph client (good for plumbing/perf, not for the
  full generated-corpus retrieval-quality numbers).

Confirm the index is populated:

```powershell
curl http://localhost:6333/collections/onenote_chunks
```

## 3. Live answer-quality + latency  →  fills Таблица «t_perf» (latency columns)

```powershell
$env:RETRIEVAL_PROVIDER='qdrant'; $env:DEFAULT_LLM_PROVIDER='ollama'
$env:DEFAULT_EMBEDDING_PROVIDER='ollama'
rag_evaluate --dataset eval/datasets/company_knowledge_eval.json `
  --output eval/results/live_answer.json --record-db
```

Read off `retrieval_latency_ms` and `completion_latency_ms` from the per-case
metadata (the API returns both). Report median and p95; the generation latency
should dominate under a real model.

## 4. Load test  →  fills Таблица «t_perf» (concurrency rows)

```powershell
# k6 — ramp scenarios (smoke / soak / spike / stress)
k6 run benchmarks/k6/smoke.js
k6 run benchmarks/k6/soak.js
k6 run benchmarks/k6/spike.js
k6 run benchmarks/k6/stress.js
python benchmarks/scripts/k6_summary_to_csv.py   # tidy the JSON summaries

# Locust — concurrent users against the answer endpoint
locust -f benchmarks/locust/locustfile.py --host http://localhost:8081
```

Record, per scenario: concurrent users (VUs), mean response time, p95, requests/s.

## 5. Paste numbers into the thesis

`thesis/08_eksperiment.md` has the table skeleton `[[TAB: t_perf | ...]]` with `—`
placeholders and an `[[SHOT: f_bench | ...]]` slot for the k6 summary screenshot.
Replace the `—` cells with your measured values (keep two latency columns split into
retrieval vs generation), then rebuild:

```powershell
python thesis/build_docx.py
```

> If you send me the raw k6/Locust summaries and the `live_answer.json`, I will fill
> the table and write the accompanying analysis paragraph.
