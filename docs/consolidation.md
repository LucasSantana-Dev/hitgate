# Consolidation plan: shelfmark and brainchat into hitgate

Status: plan only. No code is moved by this document. Each step below is a separate PR, gated by
the hitgate eval (`hitgate/check.sh`) and the existing test suite.

## Why

Three repos tell one story with three entry points. The portfolio reads better as one project that
builds a retriever and measures it than as three small ones that cross-reference each other.

| Repo | What it is | State (checked 2026-10-17) |
|---|---|---|
| hitgate | Label-free regression gate for retrieval, plus a bundled hybrid retriever (`ragcore/`, about 1.4k lines) | PyPI `hitgate` 0.1.1 |
| shelfmark | The agent-memory flavor of the same retriever: about 4.2k lines of Python, MCP server, client layers, purge, diff packs | PyPI `shelfmark-rag` 1.1.0, 1 star |
| brainchat | Ruby CLI that answers questions over an index and cites chunk paths. It shells out to `rag-query` | RubyGems `brainchat` 0.1.0, 0 stars |

The dependency already runs one way: brainchat calls hitgate's `rag-query`, and hitgate's README
already points to shelfmark as the "agent memory" packaging. That makes the merge mostly a matter
of moving shelfmark's extra capabilities behind hitgate's package boundary, and documenting
brainchat as the reference consumer.

## Guardrails

1. hitgate's core stays dependency-free (`dependencies = []` in `pyproject.toml`). Anything that
   needs PyYAML or another new dependency goes behind an extra such as `hitgate[agent]`.
2. Every moved feature arrives with its tests. A feature whose tests cannot run on the hitgate CI
   (no model download beyond the cached e5-small) stays in shelfmark.
3. The self-indexed gate must stay green after each step: `bash hitgate/check.sh ci` within the 5
   point tolerance. Adding files to the repo changes the self-indexed corpus, so re-freeze the
   baseline deliberately, never silently.
4. brainchat stays Ruby. Rewriting it in Python would throw away a working gem and buy nothing.

## What is reusable, and where it lands

Evidence is file level (shelfmark's module list against hitgate's `ragcore/` and `hitgate/`). Step 1
below does the function-level diff before anything moves.

### From shelfmark

| shelfmark piece | Why keep it | Lands in hitgate |
|---|---|---|
| `eval/split_holdout.py`, `eval/holdout-policy.md` | Group split by target file fixes a real leak (8 of 10 holdout cases shared a file with training). hitgate has `audit_contamination` but no split tool | `hitgate/split.py` plus `docs/holdout-policy.md` |
| `eval/case_quality.py` | Flags weak golden cases. Pairs with `hitgate-generate` | `hitgate/case_quality.py`, called from `hitgate-init` |
| `eval/sweep.py`, `eval/retrieval_calib.py` | Config A/B harness and calibration. Overlaps with `hitgate.compare` and the ADR-0005 margin sweep | Fold into `hitgate/sweep.py` only if the diff shows more than a thin wrapper. Otherwise skip |
| `layers_test.py` and layer routing in `indexer.py` | One index file per client, with query isolation. Not present in `ragcore/` | `ragcore/layers.py`, optional, under `hitgate[agent]` |
| `purge.py` and `purge_test.py` | Offboard one client from every index surface. Pairs with layers | `ragcore/purge.py`, same extra |
| `session_chunker.py` | Chunks agent transcripts. hitgate's adapters README already names "assistant transcripts" as an optional source | `hitgate/adapters/` source adapter, not core |
| `symbols.py`, `populate_symbols.py` | `ragcore/retrieval.py` already has a symbol boost. Compare before moving | Merge only the delta |
| `diff_pack.py` | Change-scoped context from a git diff | `ragcore/diff_pack.py` under `hitgate[agent]`, if still wanted |
| `mcp_server.py` | Superset of `ragcore/mcp_server.py` (adds `search_knowledge` and scope labels) | Replace the `ragcore` one with the superset plus a test |
| `BENCHMARK.md` | Holdout table with the re-baseline note | Link from `docs/benchmarks.md`, do not copy |
| `sources.yaml` config | YAML sources need PyYAML | Extra only, or a JSON equivalent to stay dependency-free |

### From brainchat

| brainchat piece | Why keep it | Lands in hitgate |
|---|---|---|
| The `rag-query --format json` contract | brainchat already broke once when hitgate changed `--scope-repo all` (hitgate#134). The contract needs a test on the hitgate side | A JSON fixture plus contract test in `tests/` |
| Citation checks (`[n]` resolves to `path:lines`) | Same family of idea as the gate: verify, do not trust | Documented as a recipe, not ported |
| The Ruby CLI itself | Working, published, 1.3k lines with specs | Stays in its own repo until archived |

## Order of steps

1. **Function-level diff.** Compare `shelfmark/retrieval.py`, `chunkers.py`, `config.py`,
   `pack.py`, `query.py` and `indexer.py` against `ragcore/`. Output: a table of real differences
   in a PR description. Nothing moves yet. Decide whether shelfmark's retrieval is a superset,
   a fork that diverged, or the same code.
2. **Evaluation tools first** (`split`, `case_quality`, holdout policy). They are small, need no new
   dependencies, and strengthen the story hitgate already tells. Release as hitgate 0.2.0.
3. **Contract test for `rag-query --format json`.** Protects brainchat before anything else changes.
4. **Agent features behind `hitgate[agent]`:** layers, purge, session adapter, MCP server superset.
   One PR each, each with its tests, each re-running the self-indexed gate.
5. **Compatibility shim.** Publish a final `shelfmark-rag` release that depends on
   `hitgate[hybrid,agent]` and keeps the `shelfmark-build` and `shelfmark-query` script names as
   thin aliases. Existing installs keep working. Index location differs (`~/.shelfmark` against
   `RAG_INDEX_DIR`), so the shim documents a one-time rebuild instead of a migration script.
6. **Docs.** A short `docs/chat-over-your-index.md` describing the brainchat pattern. README
   "Related projects" line updated. shelfmark's and brainchat's READMEs get a top note pointing here.
7. **Archive.** Only after steps 3 to 6 land and one release cycle passes with no issue reports.

## What gets archived, and what stays

| Repo | Decision | Condition |
|---|---|---|
| shelfmark | Archive on GitHub (read-only) | After the shim release. `shelfmark-rag` stays on PyPI, never yanked |
| brainchat | Archive on GitHub (read-only) | After the contract test and the docs recipe. The gem stays on RubyGems |
| Their issues and PRs | Close with a pointer to hitgate | Per item, not in bulk |

Archiving is reversible but outward-facing, so it needs the owner's explicit go-ahead at step 7.
Deleting either repo is not part of this plan.

## Risks

- **Module name collisions.** shelfmark uses top-level modules (`retrieval`, `indexer`). hitgate
  namespaces everything under `ragcore` and `hitgate`. Imports must be rewritten, not copied.
- **Index schema drift.** Both use e5-small and SQLite, but schema and chunk prefixes may differ.
  Assume a rebuild and say so in the shim release notes.
- **Dependency creep.** shelfmark requires PyYAML. Core must not.
- **Positioning dilution.** hitgate is "the gate". Agent memory features must stay clearly secondary
  in the README, one line and a link, so the headline does not blur.
- **Numbers.** shelfmark's published benchmark has a holdout of about 10 cases. Do not carry its
  figures into hitgate's README. Re-measure on hitgate's own sets.

## Open questions for the owner

1. Is `shelfmark-rag` on PyPI used by anyone besides the owner? The shim step assumes at least
   one outside install is possible.
2. Should agent-memory features live in `ragcore` under an extra, or in a separate `hitgate-agent`
   distribution built from the same repo?
3. Archive brainchat, or keep it as a living example of a consumer of the contract?
