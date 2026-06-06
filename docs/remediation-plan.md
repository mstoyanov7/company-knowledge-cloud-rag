# Remediation Plan — Critical Issues

> Companion to [`project-critique.md`](project-critique.md). This plan addresses the
> three 🔴 Critical findings, in dependency order. Each phase is independently
> shippable and verifiable.
>
> **Decisions locked:** embedding provider = **Ollama `nomic-embed-text`** (reuses the
> Ollama instance already used for the LLM); scope = **all three critical issues**.
>
> **Sequencing rationale:** Phase 1 (real embeddings) is the foundation — Phase 2
> measures it, and Phase 3's safety depends on having Phase 2's numbers as a
> regression guardrail. Do not start Phase 3 before Phase 2 produces a baseline.

---

## Phase 1 — Replace the token-hash embedding with real semantic embeddings

**Goal:** retrieval works on meaning, not shared tokens. A synonym query
("PTO allowance") retrieves the right page even with zero literal overlap.

### Current state (what we're changing)
- Two embedder classes, both calling `embed_text_token_hash`:
  - [`adapters/embeddings.py`](../services/rag-api/app/rag_api/adapters/embeddings.py) — `DeterministicQueryEmbedder` (query side, used by the Qdrant adapter).
  - [`ingestion/embeddings.py`](../services/sync-worker/app/sync_worker/ingestion/embeddings.py) — `DeterministicEmbedder` (index side).
- Qdrant collection is created with `size=settings.embedding_vector_size` and COSINE distance in [`persistence/vector_store.py:18`](../services/sync-worker/app/sync_worker/persistence/vector_store.py#L18).
- `default_embedding_provider` exists in [`config.py:76`](../libs/shared-schemas/python/shared_schemas/config.py#L76) **but is never used for selection** — no factory.
- `embedding_vector_size = 32`.

> ⚠️ **The one rule that must not break:** the index side and the query side must use
> the **same** provider and the **same** vector dimension. A mismatch silently
> returns garbage (cosine over incompatible spaces), not an error.

### Steps
1. **Define a shared embedder port.** Add an `EmbedderPort` protocol
   (`embed_text(str) -> list[float]`, `embed_texts(list[str]) -> list[list[float]]`,
   plus a `vector_size` property) in `libs/shared-schemas` so both services depend on
   one contract.
2. **Implement `OllamaEmbedder`.** New adapter calling Ollama's embeddings endpoint
   (`POST {LLM_OPENAI_BASE_URL}/embeddings` or `/api/embeddings`) with model
   `nomic-embed-text`. Reuse the httpx client style from
   [`adapters/llm/openai_compat.py`](../services/rag-api/app/rag_api/adapters/llm/openai_compat.py).
   Batch `embed_texts` for ingestion throughput; add retry/backoff consistent with
   the existing `ONENOTE_RETRY_*` pattern.
3. **Keep `TokenHashEmbedder`** (rename the existing classes) as the offline/no-network
   fallback for unit tests — explicitly labeled as non-semantic.
4. **Add a factory** keyed on `default_embedding_provider`
   (`"ollama"` → `OllamaEmbedder`, `"token-hash-v1"` → `TokenHashEmbedder`). Both the
   Qdrant adapter ([`qdrant.py:35`](../services/rag-api/app/rag_api/adapters/retrieval/qdrant.py#L35))
   and the sync-worker factory ([`onenote/factory.py:25`](../services/sync-worker/app/sync_worker/onenote/factory.py#L25))
   resolve the embedder through this factory.
5. **Derive vector size from the model, not config.** `nomic-embed-text` is **768-dim**.
   Set `embedding_vector_size` default to 768 (or, better, query it from the embedder so
   the two can never drift). Update `.env.example` and `.env`:
   `DEFAULT_EMBEDDING_PROVIDER=ollama`, `EMBEDDING_VECTOR_SIZE=768`.
6. **Re-create the Qdrant collection at the new dimension.** A 32-dim collection cannot
   hold 768-dim vectors. Add a guard in `vector_store.py` that detects a dimension
   mismatch on startup and recreates the collection (drop + create), then forces a full
   re-index. Document this as a one-time migration in the runbook.
7. **Pull the model in the environment.** Add `ollama pull nomic-embed-text` to
   [`scripts/start-onenote-stack.ps1`](../scripts/start-onenote-stack.ps1) (or document
   it as a prerequisite). Note in compose that `onenote-poller`/`sync-worker` now depend
   on Ollama reachability via `host.docker.internal`.
8. **Re-index the corpus** end-to-end with the new embedder
   (`onenote_bootstrap` / sync-worker run-once) against the generated test pages.

### Verification (Phase 1 done when…)
- A new test `tests/test_semantic_retrieval.py` case proves a **synonym query with no
  shared content tokens** retrieves the expected page (this *fails* on token-hash and
  *passes* on Ollama — it's the proof the change matters).
- Existing `pytest` suite still green (token-hash fallback keeps unit tests offline).
- Manual: ask a paraphrased question through the UI and confirm the right citation.

### Risks / mitigations
- **Ollama not running at query time** → retrieval 500s. Mitigation: clear startup
  health check + a documented fallback to token-hash for fully-offline demos.
- **Re-index cost / data loss** → the drop-and-recreate is destructive; gate it behind
  the dimension-mismatch check and log loudly.

---

## Phase 2 — Make evaluation rigorous and committed

**Goal:** turn the eval harness into thesis evidence — real numbers, baselines, and a
committed results table that proves each claimed contribution.

### Current state
- [`evaluation/harness.py`](../services/rag-api/app/rag_api/evaluation/harness.py) already
  computes `retrieval_hit_rate`, `mean_document_recall`, `mean_citation_correctness`,
  `mean_groundedness`, `mean_latency_ms`. Good bones.
- One dataset, [`onboarding_eval.json`](../eval/datasets/onboarding_eval.json), tuned
  against the toy embeddings; results in `eval/results/` are gitignored.

### Steps
1. **Add ranking metrics.** Extend the harness with **MRR** and **nDCG@k** (the current
   recall@k / hit-rate is binary and undersells ranking quality). These are standard and
   expected in a retrieval evaluation chapter.
2. **Expand and re-validate the dataset.** Grow beyond the current handful of cases to a
   defensible size (aim ≥ 30–50), covering: paraphrase/synonym queries, ACL-restricted
   queries (a user who should *not* see a page), freshness cases, and "no answer exists"
   cases. Re-confirm `expected_source_item_ids` against the **re-indexed** corpus.
3. **Run the baseline comparison (the core experiment).** Run the harness twice via the
   embedder factory:
   - `token-hash-v1` (the old lexical baseline)
   - `ollama / nomic-embed-text` (the new semantic system)
   Produce a side-by-side table. This A/B is the empirical justification for Phase 1 and
   a publishable result.
4. **Add the ACL ablation.** Run with ACL filtering on vs off to quantify the safety/quality
   trade-off — this is one of the thesis's stated contributions
   ([`07-diploma-novelty.md`](07-diploma-novelty.md)).
5. **Add the freshness experiment.** Using the assets in
   [`docs/experiments/`](experiments/), measure staleness for static vs polling vs
   incremental indexing — the third stated contribution.
6. **Commit results.** Un-ignore a curated `eval/results/` table (CSV/MD), or add
   `eval/results/baseline-table.md` that is explicitly tracked. Wire a `make eval` /
   script entry so results are reproducible.

### Verification (Phase 2 done when…)
- `rag_evaluate` outputs MRR + nDCG alongside existing metrics.
- A committed `eval/results/baseline-table.md` shows token-hash vs Ollama, with-ACL vs
  without, and freshness strategies — each with numbers.
- Numbers show the semantic system materially beating the lexical baseline (if it doesn't,
  that's a finding to investigate before the defense, not after).

---

## Phase 3 — Reduce the heuristic sprawl in `answer_service.py`

**Goal:** with real retrieval in place, delete the compensation logic that existed only
to paper over broken embeddings, and split the 2,430-line god module into testable stages.
**Guardrail:** Phase 2's baseline table is the regression oracle — every removal must keep
eval metrics ≥ baseline.

### Current state
- [`answer_service.py`](../services/rag-api/app/rag_api/services/answer_service.py) is
  2,430 lines / 99 KB: `_GENERIC_HEDGE_TERMS`, `_INVENTORY_GENERIC_TERMS`, ad-hoc stemming
  in `_normalize_token`, magic scoring weights (`+12`, `+8`, `+3`, `* 3.0`) in
  `_chunk_relevance_score` and the inventory matcher.
- Two regression tests appear to encode single anecdotes:
  [`test_wrong_guide_disambiguation.py`](../tests/test_wrong_guide_disambiguation.py),
  [`test_flutter_hmi_setup_regression.py`](../tests/test_flutter_hmi_setup_regression.py).

### Steps
1. **Establish the safety net first.** Phase 2 must be green and committed. Nothing in
   Phase 3 ships if eval metrics drop below the recorded baseline.
2. **Split into pipeline stages.** Extract clear modules: `retrieve → grade → assemble →
   guard`. Move inventory handling and clarification into their own files (clarification
   already partly lives in [`clarification.py`](../services/rag-api/app/rag_api/services/clarification.py)).
   Target: `answer_service.py` becomes a thin orchestrator.
3. **Remove lexical compensation that real embeddings make redundant.** Re-run eval after
   each removal: drop the hardcoded generic-term sets and hand-tuned phrase-boost weights
   where retrieval now handles the case semantically. Keep only what demonstrably holds
   metrics up.
4. **Replace magic constants with named, documented parameters.** Anything that survives
   gets a name, a docstring explaining *why* that weight, and ideally a value traceable to
   the Phase 2 tuning — so "why +12?" has an answer.
5. **Reclassify the anecdote tests.** Convert the two regression tests into dataset cases
   in the eval set (Phase 2) so they measure generalization, not a single patched example.

### Verification (Phase 3 done when…)
- `answer_service.py` is substantially smaller and split into single-responsibility modules.
- Eval metrics (Phase 2) are **≥ baseline** after the cleanup.
- Surviving heuristics are named and documented; no bare magic numbers.

---

## Cross-cutting (do alongside, cheap, de-risks the above)
- **Add CI** running `pytest`, the frontend `tsc + vitest`, and (once added) `ruff`/`mypy`,
  so each phase is guarded automatically. (High-priority process gap #4 in the critique.)
- **Commit the current working tree** before starting — 79 changed files / 57 untracked are
  uncommitted; don't refactor on top of unsaved work. (Critique #5.)

## Suggested order of execution
1. Commit current work + add CI skeleton (cross-cutting).
2. **Phase 1** — real embeddings + re-index + synonym smoke test.
3. **Phase 2** — metrics, dataset, baseline table (proves Phase 1).
4. **Phase 3** — refactor under the Phase 2 guardrail.
