# Changelog

Not a conventional "what changed" list. Consistent with [DECISIONS.md](./DECISIONS.md),
every entry that touches retrieval or the eval pairs a **measured before/after** with the
**trigger that would reopen it** — a change with no measurement and no tripwire doesn't earn
an entry here. Pure docs are listed plainly and labelled as carrying no metric. Dates are
when the change landed on `main`.

Numbers are code-scope, pure hybrid (`RAG_RERANK_AUTO=off`). Because the demo self-indexes
this repo, exact chunk counts drift commit-to-commit; entries cite the stable **file count**
and the **metric deltas**, not a chunk number that's wrong by the next commit.

## 2026-06-20 — external corpus benchmarks (7 corpora)

### Added
- **7 external corpus benchmarks** — same retriever, zero tuning, run against codebases this
  project had no hand in building. Each corpus indexed separately (`RAG_INDEX_DIR`), golden
  cases generated with `eval/generate.py`, curated manually, audited with
  `eval/audit_contamination.py`, then frozen into `eval/baseline.<corpus>.json`.

  | Corpus | Language | n | Hit@5 | Hit@1 | MRR |
  |---|---|---|---|---|---|
  | FastAPI v0.115 | Python | 25 | **1.0** | 0.64 | 0.790 |
  | forge-space/mcp-gateway | TypeScript | 20 | **1.0** | 0.70 | 0.821 |
  | portfolio/src | React/TS | 15 | **1.0** | 0.60 | 0.778 |
  | ai-dev-toolkit/packages/core | Python+TS | 20 | **1.0** | 0.85 | 0.925 |
  | homelab/homelab\_manager | Python | 20 | 0.950 | 0.85 | 0.900 |
  | Lucky/packages/backend | TypeScript | 21 | 0.905 | 0.71 | 0.810 |
  | Criativaria/web-app | Next.js/TS | 27 | 0.741 | 0.59 | 0.660 |

  **Hit@5=1.0 on four of seven** with no per-corpus tuning. The two non-1.0 corpora have
  structural causes: Lucky loses to Prometheus registry / middleware vocabulary drift (one
  true MISS); Criativaria is a homogeneous Next.js component library where sibling
  components are lexically indistinguishable — a genuine retrieval ceiling (3 true MISSes).
  **Reopen (Criativaria):** if the reranker (`bge-reranker-v2-m3`) measurably recovers the
  3 MISS cases without regressing the 24 passing cases.

- **Index bug found and fixed** during the Lucky benchmark: Stryker JS/TS mutation testing
  creates `.stryker-tmp/sandbox-*/` directories with full source copies, inflating the Lucky
  index 3× (237 → 79 files). Fixed by adding `.stryker-tmp` to `EXCLUDED_DIR_PARTS` in
  `ragcore/config.py`. **No metric delta on the self-index** (`.stryker-tmp` was already
  absent from this repo). **Reopen:** if another mutation-testing tool writes to a different
  sandbox path pattern.

- **`/rag-eval` skill updated** with a calibration table: when someone runs the skill on a
  new corpus, it now tells them what Hit@5 range to expect based on corpus structure (clean
  functional boundaries vs. homogeneous component layer).

- **`docs/METHODOLOGY.md` extended** with per-corpus sections and an 8-row cross-corpus
  table (including the self-index). Key finding documented: corpus module clarity (functional
  layer separation vs. same-layer sibling components) is a better predictor of Hit@1 than
  language or corpus size. **No metric delta on the gated self-index baseline.**

## 2026-06-17 — cache HF model in CI

### Changed
- **CI caches the e5 embedding model** (`actions/cache` on `~/.cache/huggingface`). On a cache
  hit the eval + determinism steps run **fully offline** (`HF_HUB_OFFLINE=1`), so HuggingFace is
  never contacted — kills the intermittent **HTTP 429** download flake that red-failed a run. First
  run (cache miss) still downloads online and populates the cache. **No metric delta** (CI plumbing).
  **Reopen:** if the model name changes, bump the cache key.

## 2026-06-17 — pytest in CI

### Changed
- **CI now runs the unit suite** (`.github/workflows/eval.yml`) after the eval + determinism
  gates — so the `tests/` are enforced, not just runnable. Reuses the e5 model the eval gate
  already cached; installs only `pytest` (the adapter tests duck-type LangChain, no extra dep).
  **No metric delta** (CI/test plumbing). **Reopen:** drop it if the suite turns flaky in CI.

## 2026-06-17 — LangChain retriever adapter

### Added
- **`adapters/langchain_retriever.py`** — `to_harness(lc_retriever, path_key="source")` maps any
  LangChain retriever (`.invoke` / `.get_relevant_documents`) into the harness `--retriever`
  protocol. **No hard dependency** — duck-typed, so it imports without LangChain installed.
- **`adapters/example_langchain_retriever.py`** — runnable example: a LangChain `BM25Retriever`
  over the repo's code, strictly opt-in (`pip install langchain-community`). **Measured through
  the gate:** `Hit@5 0.917 / Hit@1 0.75 / MRR 0.833` — edges the bundled hybrid (0.667/0.833),
  i.e. the 12-case demo is too small to discriminate retrievers (see `docs/METHODOLOGY.md`), not
  a retriever-quality claim.
- **`tests/test_langchain_adapter.py`** — dependency-free mapping tests with fake Documents:
  metadata→path, top-k, page_content fallback, legacy `get_relevant_documents`, custom path_key.
  **22 tests pass.**
- **`adapters/README.md`** — documents the retriever-adapter category + the runnable example.
  `langchain-community` added to `requirements-dev.txt` (optional; **core stays at 3 deps**).

## 2026-06-17 — retriever-agnostic harness

### Added
- **`eval/run.py --retriever module.path:callable`** — the eval harness now measures *any*
  retriever, not just the bundled one. A retriever is any callable
  `(query, top, scope) -> Sequence[Mapping]` returning results ranked best-first, each with a
  `"path"`. Rank is assigned by position, so external retrievers stay trivial. Default is the
  bundled hybrid; `--rerank` applies to it only.
- **`eval/example_external_retriever.py`** — a dependency-free "bring your own" template (a dumb
  keyword matcher). **Measured (proves agnosticism):** scored through the same gate, the demo
  yields `Hit@5 1.0 / Hit@1 0.833 / MRR 0.917` — *higher* than the bundled hybrid (0.667/0.833),
  which is the 12-case demo being too easy to discriminate retrievers (see METHODOLOGY.md), not a
  claim that keyword-matching beats hybrid.
- **`tests/test_harness.py`** — retriever-agnostic metric math (stub retriever, no model),
  `--retriever` resolution (default/spec/malformed/unknown-module), and the example's protocol
  shape. **Measured:** 17 tests pass (6 new).

### Changed
- **README repositioned** so the **evaluation harness** is the headline product (a pytest-style
  regression gate for retrieval quality), with a "use it on your own retriever" section. The
  bundled hybrid engine is framed as the reference implementation it measures.
- **Bundled-retriever behaviour is unchanged** — the gate still reports `Hit@1 0.667 / Hit@5 0.833`
  (rank-by-position is identical to the engine's own rank order). **No metric delta.**

## 2026-06-17 — methodology + ablation

### Added
- **`RAG_RANK_MODE` (hybrid | dense | bm25)** in `ragcore/retrieval.py` so single-channel
  ranking is reproducible, not asserted. Enables the ablation below. `RAG_HYBRID=0` kept as a
  back-compatible alias for `dense`.
- **`docs/METHODOLOGY.md`** — the label-free measurement argument, backed by a real ablation
  on the 12-case code demo (pure, `RAG_RERANK_AUTO=off`):

  | mode | Hit@1 | Hit@3 | Hit@5 | MRR |
  |---|---|---|---|---|
  | BM25-only | 0.750 | 0.833 | 0.833 | 0.792 |
  | dense-only | 0.667 | 0.833 | 0.917 | 0.767 |
  | hybrid | 0.667 | 0.833 | 0.833 | 0.750 |
  | hybrid+rerank (forced) | 0.583 | 0.833 | 0.833 | 0.708 |

  Honest headline: **BM25-only edges hybrid here, and forced reranking is the worst config** —
  the measured arguments for gating rerank (not running it globally) and for trusting Hit@5
  (stable) over Hit@1/MRR (noise-prone on 12 cases). The prose-rerank regression is *not*
  reproducible on this code-only demo and is attributed to DECISIONS.md, not re-derived.
- **`eval/plot_history.py`** — Hit@5 per commit across git history (per-commit, self-indexed),
  → `docs/hit5_history.svg`. **Measured:** Hit@5 held **0.833 across all 10 harness-bearing
  commits**. Optional `matplotlib` dev dep (`requirements-dev.txt`); core stays at 3 deps.
- **`tests/`** — real assertions on the identifier tokenizer, the `RAG_RANK_MODE` branches,
  RRF result shape, and reranker graceful-fallback. **Measured:** 11 passed. (`pytest` is a dev dep.)

### Changed
- **Excluded `tests/`/`spec/` dirs from indexing** (`ragcore/config.py`). Test scaffolding is not
  the implementation a "where is X" query searches; indexing it returned tests instead of code
  (drove Hit@1 to 0.500 before exclusion). **Reopen:** if a user needs tests searchable, make the
  exclusion configurable.
- **Baseline re-frozen** to `Hit@1 0.667 / Hit@5 0.833` (was `0.75 / 0.833`). Adding `eval/plot_history.py`
  to the self-indexed corpus demoted the "git commits" case from rank 1→2 (still within top-5, so
  **Hit@5 held**). Deliberate re-baseline per the living-benchmark policy (>±5pp on Hit@1).
  **Reopen:** any gated metric (Hit@5) moves beyond ±5pp.

## 2026-06-17

### Fixed
- **`eval/check.sh` now runs on a fresh clone.** Before: it hardcoded `../venv/bin/python3`
  and defaulted to internal files (`golden.jsonl`, `baseline-golden.json`) absent from the
  public repo, plus a `cd` that broke the relative index path — so the gate the repo *preaches*
  could not actually run on a clone. After: `${PYTHON:-python3}`, defaults to the committed
  `golden.demo.jsonl` + `baseline.example.json`, CWD-independent absolute paths, auto-builds
  the index if missing, forces `RAG_RERANK_AUTO=off` to match the frozen baseline.
  **Measured:** from a clean checkout, reproduces **Hit@5 0.833** within ±5pp in ~4s
  (before: could not run at all).
  **Reopen:** if a fresh-clone run ever fails to reproduce the baseline.
- **`eval/audit_contamination.py` `--dataset` resolution.** Relative paths now resolve against
  cwd (standard) then fall back to the repo root, so the tool works when invoked from another
  directory; a missing path errors clearly, naming both locations tried.
  **Reopen:** n/a (non-metric robustness fix).

### Changed
- **Baseline re-frozen to the live self-indexed corpus.** This session's additions grew the
  corpus **10 → 12 code files**, which drifted **Hit@1 0.833 → 0.75** and **MRR 0.833 → 0.792**;
  **Hit@5 held at 0.833**. `eval/baseline.example.json` was re-frozen to the current values, and
  the README now leads with Hit@5 as the gated headline.
  **Reopen / re-freeze trigger:** any gated metric moves beyond the ±5pp tolerance — a
  deliberate re-baseline, never a silent edit. (This is the honest behaviour of a self-indexing
  benchmark; see [DECISIONS.md](./DECISIONS.md).)

### Added
- **`eval/audit_contamination.py`** — flags un-winnable golden cases (expected path not in the
  corpus), the disease that caps a score with a constant penalty. **Measured:** clean demo =
  **0/12 contaminated** (exit 0); an injected not-in-corpus case is flagged (exit 1). Generalises
  the audit that historically moved this project's internal baseline **~8pp** ([DECISIONS.md](./DECISIONS.md) §1).
  **Reopen:** if a real un-winnable case ever ships uncaught.
- **`eval/test_determinism.py`** — asserts same query → same top-K ordering. **Measured:**
  **12/12** demo queries stable across 2 identical runs.
  **Reopen:** any query whose ordering drifts run-to-run.
- **Advisory CI** (`.github/workflows/eval.yml`) — runs the eval + determinism gates on push/PR.
  **Measured:** green in ~2m28s on a clean Ubuntu runner (real model download + build + eval).
  Explicitly advisory, no SLA.
  **Reopen (drop it):** if it turns flaky or the embedding-model download makes it unreliable.
- **`ARCHITECTURE.md`, `ROADMAP.md`, `docs/measure-challenge-decide-audit.md`** — documentation.
  **No metric delta** (markdown is outside the code-scope eval, so it does not move the numbers).

## 2026-06-16

### Added
- **Initial public release.** Decoupled hybrid engine (`intfloat/multilingual-e5-small` + BM25 +
  Reciprocal Rank Fusion, with a selective code-scope cross-encoder reranker) and the evaluation
  harness, extracted from a personal memory index and made tool-neutral.
  **Measured:** self-indexed demo **Hit@5 0.833** at 10 code files, pure hybrid.
