# Answer-Engine Evaluation — committed evidence

Deterministic, offline results behind the experimental chapter of the thesis. All
numbers below are reproducible with the **mock retriever + mock LLM** (no Docker, no
network), so they are stable across runs and machines. The retriever here is purely
lexical (keyword overlap); semantic retrieval quality is measured separately in
[`baseline-table.md`](baseline-table.md), and live end-to-end numbers come from the
runbook in [`LIVE_RUNBOOK.md`](LIVE_RUNBOOK.md).

Corpus: [`datasets/eval_corpus.json`](datasets/eval_corpus.json) — 22 chunk-documents
across 10 topic areas, ACL tags `public`/`employees`/`engineering`/`hr`/`finance`/
`security`; 3 pages are access-restricted.

Reproduce:

```powershell
$env:RETRIEVAL_PROVIDER='mock'; $env:DEFAULT_LLM_PROVIDER='mock'
$env:SECURITY_AUDIT_ENABLED='false'; $env:AUTH_ENABLED='false'
$env:APP_DATABASE_URL='sqlite:///./.cache/eval.sqlite3'
$env:MOCK_CORPUS_PATH='eval/datasets/eval_corpus.json'
rag_evaluate --dataset eval/datasets/company_knowledge_eval.json --output eval/results/company_knowledge_latest.json
python eval/run_behavior_eval.py
```

## 1. Answerable cases — [`company_knowledge_eval.json`](datasets/company_knowledge_eval.json) (19 cases)

| Metric | All 19 | Answered only (15) |
| --- | --- | --- |
| Retrieval hit rate | 0.79 | — |
| Mean document recall | 0.79 | 1.00 |
| Mean citation correctness | 0.52 | 0.66 |
| Mean MRR | 0.79 | — |
| Mean nDCG@k | 0.79 | — |
| Mean groundedness | 0.84 | **1.00** |

Outcome of the 19 cases: **15 answered, 3 clarify, 1 hedge, 0 hallucination**. The
four non-answers are the graceful-degradation paths firing because the *lexical*
retriever cannot disambiguate (clarify) or find a direct match (hedge) — not wrong
answers. On every case it does answer, groundedness is 1.00 (no unsupported claim).
Citation correctness < 1 comes from citing one adjacent page on topically close
queries; document recall stays 1.00 there, so the answer is correct with an extra
source.

## 2. Graded behaviour — [`behavior_eval.json`](datasets/behavior_eval.json) (7 probes)

Outcome distribution across deliberately hard probes (absent topics, ambiguous
queries, topically-related-only): **answered 2, hedge 3, clarify 2**. All four graded
modes (answered / hedge / clarify / refusal) are exercised across the suite; the
engine never fabricates a confident answer.

## 3. Access-control ablation — 3 restricted pages, denied vs allowed persona

| Restricted page | Denied persona outcome | Leaked to denied? | Allowed persona retrieves? | Candidates filtered (denied) |
| --- | --- | --- | --- | --- |
| On-call compensation (`hr`) | hedge | **No** | **Yes** | 36 |
| Security incident response (`security`) | hedge | **No** | **Yes** | 36 |
| Vendor invoice processing (`finance`) | refusal | **No** | **Yes** | 36 |

**0/3 leaks**; the allowed persona retrieves and cites the page in **3/3** cases. The
denied persona never receives the restricted content — the filter removes it inside
the retrieval query, so it never reaches grading, the prompt, or the citations.
