# Project Critique — Cloud-RAG Company Knowledge Assistant

> Critical review written as a diploma reviewer would assess the project before a
> defense. Findings are ordered by how much each would hurt in evaluation.
> Date of review: 2026-06-06.

First, credit where due: this is a genuinely substantial, well-structured system.
Hexagonal ports/adapters, ACL-aware retrieval, an OneNote sync pipeline with
reconciliation, OIDC + local auth, audit logging, OTel hooks, an eval harness,
k6/Locust benchmarks, and 151 passing tests. The engineering breadth is above
what most diploma projects show. What follows is the gap analysis.

---

## 🔴 Critical — these undermine the thesis itself

### 1. "Semantic retrieval" is not semantic — it's a 32-dimension lexical hash
The only embedding implementation is
[`embeddings.py`](../libs/shared-schemas/python/shared_schemas/embeddings.py) —
`embed_text_token_hash`, which blake2b-hashes each token into one of **32 buckets**
with a ±1 sign. The code itself says *"This is not a production embedding model."*
There is **no alternative provider** — `default_embedding_provider = "token-hash-v1"`
in [`config.py:76`](../libs/shared-schemas/python/shared_schemas/config.py#L76) is
the only option; no sentence-transformers, no OpenAI/Ollama embeddings path.

Consequences:
- Qdrant vector search is effectively a noisy bag-of-words overlap. Two paraphrases
  with no shared tokens ("How much leave do I get?" vs "What is the PTO allowance?")
  will not match — the exact failure mode RAG is supposed to solve.
- A 32-dim space cannot separate a real corpus — hash collisions are frequent and
  meaning is lost.
- An examiner who asks "show me retrieval working on a synonym query" exposes this
  in one question.

**How to fix:** Wire a real embedding adapter behind the existing `embed_text` port
([`adapters/embeddings.py`](../services/rag-api/app/rag_api/adapters/embeddings.py)) —
`sentence-transformers/all-MiniLM-L6-v2` (384-dim, local, free) or Ollama's
`nomic-embed-text`. It is an adapter swap plus re-indexing and changing
`EMBEDDING_VECTOR_SIZE`. Keep `token-hash-v1` only as a documented offline-test
fallback.

### 2. Heuristic sprawl is masking the broken retrieval
Because the embeddings can't carry meaning,
[`answer_service.py`](../services/rag-api/app/rag_api/services/answer_service.py) has
grown to **2,430 lines / 99 KB** of hand-tuned compensation: hardcoded
`_GENERIC_HEDGE_TERMS`, `_INVENTORY_GENERIC_TERMS`, ad-hoc stemming in
`_normalize_token`, and magic scoring weights (`+12`, `+8`, `+3`, `* 3.0`) scattered
through `_chunk_relevance_score` and the inventory matcher. None of these constants
are justified or tuned by experiment — they are empirical patches.

Problems on three fronts: maintainability, scientific defensibility ("why +12?" has
no answer), and the signal that the core mechanism doesn't work so symptoms are
being papered over. Two test files —
[`test_wrong_guide_disambiguation.py`](../tests/test_wrong_guide_disambiguation.py)
and [`test_flutter_hmi_setup_regression.py`](../tests/test_flutter_hmi_setup_regression.py)
— read like "I hit a specific bad answer and added a rule." That is overfitting to
anecdotes, not generalization.

**How to fix:** Once real embeddings are in, delete most of this. Move what remains
into small, named, individually testable scorers with documented rationale. Split
`answer_service.py` into pipeline stages (retrieve → grade → assemble → guard).

### 3. Evaluation is present but not rigorous enough to be a research contribution
The novelty doc ([`docs/07-diploma-novelty.md`](07-diploma-novelty.md)) proposes
freshness-aware + ACL-aware + cited RAG with "measurable evaluation," but:
- `eval/results/` is gitignored — **no committed results, no baseline comparison.**
  A diploma needs numbers: recall@k, MRR/nDCG, answer faithfulness, and an A/B
  (e.g. static vs polling vs incremental for the freshness claim; with-ACL vs
  without for the ACL claim).
- The single dataset [`eval/datasets/onboarding_eval.json`](../eval/datasets/onboarding_eval.json)
  was almost certainly tuned against the toy embeddings, so current numbers are
  meaningless for a real model.

**How to fix:** Define metrics, run them before/after the embedding swap, and commit
a results table per claimed contribution. That table *is* the thesis evidence.

---

## 🟠 High — engineering process gaps

### 4. No CI, no linting, no type checking
No `.github/workflows`, and `pyproject.toml` dev deps are just `pytest` — no `ruff`,
`black`, `mypy`, no coverage.
**Fix:** Add a GitHub Actions workflow running `ruff check`, `mypy`, `pytest --cov`,
and the frontend `tsc + vitest`. Add `ruff`/`mypy` config to `pyproject.toml`.

### 5. Repository is in a messy, half-committed state
`git status` shows **79 files changed (+8,121 / −1,547) and 57 untracked files** — an
entire UI rewrite plus new features (`AuthGate`, `AdminPanel`, `auth.ts`,
admin/feedback/trending APIs) sitting uncommitted. The last commit is *"Drop
openwebui and build UI from scratch"* but the new UI isn't in history. Disk loss =
thesis loss, and there's no reviewable history.
**Fix:** Commit in logical chunks now, with messages. Don't hand in a project whose
main feature exists only in the working tree.

### 6. Dead/duplicate artifacts confuse the story
The tree carries `claude-ui/` (a separate abandoned "Atlas Knowledge Assistant" HTML
UI), `apps/openwebui/` (legacy), `generated_onenote_pages_automotive/`, and
`cloud_rag_diploma.egg-info/`. There are **three** UI directories — a reviewer can't
tell which is real.
**Fix:** Delete `claude-ui/` and the legacy openwebui app, or move generated fixtures
under `tests/fixtures`. One canonical UI.

---

## 🟡 Medium — security & correctness

### 7. The system ships open and with weak defaults
[`.env.example`](../.env.example) defaults `AUTH_ENABLED=false` and
`AUTH_REQUIRED=false` — the API is unauthenticated out of the box. Plus
`AUTH_SESSION_SECRET=replace-with-a-long-random-secret`,
`POSTGRES_PASSWORD=cloudrag`, and
`AUTH_BOOTSTRAP_ADMIN_PASSWORD=change-this-admin-password`. Nothing enforces that
these change in a non-local `APP_ENV`.
**Fix:** Default auth on; fail fast at startup if `APP_ENV != local` and the session
secret/admin password are still placeholders.

### 8. The "API key" is shipped to the browser
`VITE_RAG_API_KEY` is injected into the frontend
([`docker-compose.yml:81`](../docker-compose.yml#L81)) and bundled into client JS —
so `RAG_API_KEY` is effectively public. It's a soft gate, not a security control,
and shouldn't be described as one in the thesis. Real auth is the session/OIDC
layer; be precise about that distinction.

### 9. Qdrant exposed without auth
[`docker-compose.yml:30`](../docker-compose.yml#L30) publishes 6333/6334 with no API
key and no healthcheck (unlike postgres/redis). Fine for local, worth a sentence in
the "production hardening" section.

---

## 🟢 Lower — polish

- **Frontend:** no ESLint; conversation history is `localStorage`-only (acceptable
  for a PoC, but state the limitation). `App.tsx` is fine at 196 lines.
- **README drift:** still documents the OneNote/openwebui flow heavily after the
  pivot to the custom UI; "Repository Shape" lists `apps/openwebui` as primary-ish.
- **No ADRs / decision log:** a short "why ports-and-adapters, why Qdrant, why
  OneNote" record strengthens the architecture chapter.
- **Magic numbers in config** (`RETRIEVAL_CANDIDATE_MULTIPLIER=3`, scoring weights)
  should be traceable to the evaluation.

---

## If you only do four things before the defense
1. **Replace the hash embedding with a real model and re-index.** Without this, the
   project doesn't demonstrate RAG. (Critical #1)
2. **Produce a real evaluation table** with baselines for each claimed contribution.
   (Critical #3)
3. **Commit everything and add CI.** Don't defend uncommitted work. (#4, #5)
4. **After #1, gut the heuristic compensation** in `answer_service.py` and split it.
   (#2)

The architecture and engineering effort are strong enough to carry a good grade —
but the toy embedding is a load-bearing flaw that turns "Cloud-RAG semantic
retrieval" into "lexical keyword overlap with extra steps." Fix that and the rest of
the system finally gets to show what it can do.
