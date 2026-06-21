# ADR-0007: Package the eval harness as a standalone zero-dep `hitgate` (flat-layout rename, engine as `[hybrid]` extra)

## Status

Accepted (2026-06-21). Decided via `research-and-decide`: 2-agent Phase-1 research (repo coupling
cartography + Python packaging best-practice) → `decision-critic` adversarial review → orchestrator
verification of the critic's Claims-To-Verify → this record. Implements **Move 2 of [ADR-0006](0006-reach-strategy-retrieval-gate-positioning.md)**
(make the harness the standalone installable) and resolves the package-name item ADR-0006 left "confirm
at build."

The critic's review **flipped the leading option** (from "keep `eval/` in place + `package-dir` mapping +
a dual-mode bootstrap" to the clean rename below); the flip was adopted only after verifying the deciding
claims directly (see *Verification* — the README does not promise zero-install loose-script execution, and
the rename is baseline-safe).

## Context

[ADR-0006](0006-reach-strategy-retrieval-gate-positioning.md) made the eval harness the product and called
for it to become a standalone, zero-dependency, pip-installable package, with the bundled hybrid retriever
(`ragcore`, which needs sentence-transformers + numpy + rank-bm25) as an optional `[hybrid]` extra. Today
`pyproject.toml` packages **only `ragcore`** (the retriever); the `eval/` harness is not importable and
wires itself together with scattered `sys.path.insert` hacks. The repo is also a **self-indexing demo** —
its eval indexes the repo's own source, scored against a frozen golden set gated at ±5pp on Hit@5 — so any
restructure must not silently invalidate that baseline.

**Verified coupling (read-only cartography + orchestrator spot-checks):**
- Genuinely zero third-party deps: `compare.py`, `diff.py`, `plot_history.py`, `example_external_retriever.py`.
- `run.py` imports `ragcore` **only** inside `builtin_retriever()` (lazy, when `--retriever` is None); the
  Hit@K/MRR metric math is dependency-free.
- Need `ragcore` (→ `[hybrid]`): `generate.py`, `audit_contamination.py`, `test_determinism.py`, and run.py's
  builtin path. So a "zero-dep core + optional engine" split is real and clean.
- Current coupling: 6 `sys.path.insert` sites across `eval/*.py` + `ragcore/*.py`.
- External-facing commands that must be migrated: ~37 `eval/…` references across README (18),
  docs/METHODOLOGY (12), `skills/rag-eval/SKILL.md` (4, installed at `~/.claude`), `.github/workflows/eval.yml`
  (3), plus `tests/` imports and `plot_history.py`'s hardcoded `eval/run.py` / `eval/golden.demo.jsonl`.

## Verification (claims the decision rests on, checked directly)

- **The README does NOT promise zero-install loose-script execution.** Its quickstart runs
  `pip install sentence-transformers rank-bm25 numpy` **first**, then `python eval/run.py`. "Reproducible in
  ~10 seconds" refers to eval speed, not "no install." → Dropping loose-script mode costs nothing the README
  guarantees, and `pip install hitgate[hybrid]` is a *cleaner* quickstart than the three-package line. (This
  is the critic's stated decider for the flip.)
- **The rename is baseline-safe.** Every `expect_path_contains` in `golden.demo.jsonl` is a **bare filename**
  (`run.py`, `config.py`, `compare.py`) — zero contain a slash; matching is substring-on-filename. And the
  chunk-embedding context prefix (`build.py:243`) uses `{path.name}` (basename), **not** the directory path,
  so a dir rename leaves every embedding identical. Only the stored `path` string changes; any BM25 drift
  from the dir token is within ±5pp and confirmed by re-running the gate. (Corrects the cartography agent's
  false "rename invalidates all baselines" claim.)
- **Greenfield:** `evidence-first-rag` is not on PyPI (zero external users), so a rename breaks only the
  project's own docs/CI/skill — all maintainer-controlled, one PR.

## Decision

Adopt **flat-layout, rename `eval/` → `hitgate/`** (the package directory; dist name = import name =
`hitgate`, chosen by the owner over `retrieval-gate`/`rageval`). Specifically:

- **Flat layout, not src-layout.** The repo is both a package and a self-indexing demo; src-layout would
  break clone-and-run and fight the self-index. (Both research agents and packaging.python.org guidance agree
  for this case.)
- **Standardize execution on `python -m hitgate.run` + console-scripts** (`hitgate-run`, `hitgate-check`,
  `hitgate-compare`, `hitgate-diff`, `hitgate-generate`). **Drop loose-script `python eval/run.py`.** Replace
  all 6 `sys.path` hacks with proper package imports (absolute `from hitgate.X` / relative `.X`, and qualified
  `from ragcore.X` for the engine). No dual-mode bootstrap — adding a 7th `sys.path` shim to preserve
  loose-script mode would invert the very goal of removing them (the critic's strongest point).
- **Zero-dep core + `[hybrid]` extra.** Base `pip install hitgate` pulls **no** third-party deps (pure-stdlib
  metric math + the `--retriever` protocol). `pip install hitgate[hybrid]` adds
  `sentence-transformers`, `rank-bm25`, `numpy` for the bundled `ragcore` engine. Both `hitgate` and `ragcore`
  ship in the wheel; the heavy deps are gated by the extra, and the engine-touching code paths use a **lazy
  import with a helpful `ImportError`** ("pip install hitgate[hybrid]"), so `import hitgate` always works
  dependency-free. (Precedent: sentence-transformers[train], huggingface_hub[torch], datasets[audio].)
- **Harness ships code-only; golden/baseline data stays repo-only.** Installed users bring their own corpus
  and golden set (already the README's "bring your own corpus" framing); the 101-case self-index demo data is
  repo-demo material. Avoids `importlib.resources`/wheel-size/versioning friction.

**Sequenced rollout (pilot → full; each step an independent, revertible commit):**
1. **Decouple deps (no moves):** add the `[hybrid]` optional-dependency group, move the 3 heavy deps out of
   base, add lazy `ImportError` guards in `ragcore` (retrieval/build) and the engine-consuming eval modules.
   Confirm base `import` works dep-free **and** the ±5pp gate + full test suite pass with `[hybrid]`. *This
   step alone delivers the ADR-0006 Move 2 split, before any rename.*
2. **Rename `eval/` → `hitgate/`;** rewrite imports to proper package imports; remove all 6 `sys.path` hacks;
   add `hitgate/__init__.py` + `hitgate/__main__.py` + console-scripts in `pyproject.toml`.
3. **Re-run the ±5pp gate** on the renamed self-index; confirm Hit@K holds (embeddings are filename-prefixed →
   rename-invariant). Re-freeze the baseline **only if** drift exceeds ±5pp — deliberately, per the
   living-benchmark policy, never silently.
4. **Migrate the ~37 references** (README, METHODOLOGY, SKILL.md, CI) to `python -m hitgate.X` / `hitgate-*` /
   `bash hitgate/check.sh`; update `tests/` imports to `from hitgate.X`; fix `plot_history.py`'s hardcoded
   paths.
5. **Update the installed `~/.claude/skills/rag-eval/SKILL.md`** (cross-repo).
6. **Smoke test:** `pip install -e .[hybrid]` (all execution modes) and `pip install .` (no extra → confirm
   zero-dep `import hitgate`).
7. **Only then publish `hitgate` to PyPI.**

## Alternatives considered

- **Option A — keep `eval/` in place, map import via `package-dir={"hitgate":"eval"}` + a single `sys.path`
  bootstrap to preserve loose-script mode.** Rejected: removing 6 `sys.path` hacks by adding a 7th is
  goal-inversion; the dir≠import indirection + dual-mode execution is fragile (IDE/type-checker confusion,
  untested across loose/`-m`/console-script modes) and preserves a backward-compat that doesn't need
  preserving (greenfield; README already pip-installs first).
- **Option C — src-layout move `eval/` → `src/hitgate/`.** Rejected: breaks clone-and-run (needs editable
  install), maximal churn, worst fit for a self-indexing demo. Both research agents reject it.
- **Option D — two separate distributions (`hitgate` harness + `ragcore` engine).** Deferred: over-engineered
  for one repo; one dist + extras is simpler and well-precedented. Revisit only if harness and engine diverge.
- **Ship golden/baseline data in-wheel (`importlib.resources`).** Rejected: installed users bring their own
  corpus; bundling demo data adds wheel-size/versioning friction for no user benefit.
- **Names `retrieval-gate` / `rageval`.** Considered; owner chose `hitgate` (compact, dist==import, available).

## Consequences

**Positive.** Cleanest possible layout: dir == import == dist (`hitgate`), no `package-dir` indirection, no
`sys.path` hacks, unambiguous for IDEs/type-checkers/contributors. Delivers the zero-dependency installable
harness that ADR-0006's whole reference+usage strategy depends on. Quickstart improves to
`pip install hitgate[hybrid]`. Embeddings are rename-invariant, so the gated baseline is safe.

**Negative / accepted.** Loose-script `python eval/run.py` is dropped — repo-clone devs use
`pip install -e .[hybrid]` then `python -m hitgate.run` (standard Python). ~37 doc/command refs + tests +
the cross-repo installed skill must be migrated (mechanical, one PR). A confirmatory gate re-run is required
after the rename (re-freeze only on >±5pp drift).

**Neutral.** No retriever or gate **behavior** changes; `ragcore` is untouched except for lazy-import guards.

## Revisit when

- The post-rename ±5pp gate drifts beyond tolerance → investigate the cause before re-freezing; do not
  silently re-baseline.
- A genuine need for install-free loose-script execution emerges (e.g., a teaching context) → reconsider a
  thin `python -m` entry, never `sys.path` hacks.
- The harness and the `ragcore` engine diverge enough that independent versioning matters → revisit Option D
  (split into two distributions).
- The `hitgate` name proves to confuse the target audience (opaque "Hit@K" jargon) → the rename is mechanical
  pre-publish; reconsider before the first PyPI release.
