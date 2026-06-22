# Cross-repo sweep — 63 codebases

A broader companion to the 7-corpus table in the [README](../README.md): the same retriever + the same `hitgate.run` pipeline, **zero per-corpus tuning**, swept across 63 repositories. Each repo is cloned shallow → indexed alone → a golden set is **auto-generated** (`hitgate.generate`) → scored → the clone is discarded.

## Read this first — what this is and isn't
- **The golden set is label-free** (mined from distinctive query→chunk pairs in each corpus), so these numbers measure **retrievability / regression — not human-judged relevance.** They run optimistic *by construction*; treat them as a self-consistency / regression signal, not a relevance leaderboard. (The hand-labeled reality is lower — see `docs/METHODOLOGY.md`.)
- **Selection bias is real and not hidden:** the 63 repos are almost entirely the author's own ecosystem (`LucasSantana-Dev/*`, `vsantana-organization/*`, `Criativaria-Projects/*`, `Fintech-fiap/*`). This is **breadth in N, not breadth in authorship.** The one genuinely third-party corpus benchmarked with care is **FastAPI v0.115** (README 7-corpus table, Hit@5 1.0).
- Each corpus is indexed **alone** (no cross-repo confusion), which inflates Hit@5 vs a shared multi-repo index.

## Aggregate (63 ok / 70 attempted; 7 skipped for too-few-cases)
**15,232 auto-generated cases** across TypeScript (33), Shell (17), Python (9), JavaScript (3), Java (1).

| Metric (case-weighted) | Value |
|---|---|
| **Hit@5** | **0.97** |
| Hit@1 | 0.76 |
| MRR | 0.85 |
| per-repo median Hit@5 | 1.00 |

## Where it struggles (misses left in on purpose)
| Corpus | n | Hit@5 | Note |
|---|---|---|---|
| pokedex | 12 | 0.917 | tiny corpus, Hit@1 only 0.25 (noise on n=12) |
| Criativaria/web-app | 216 | 0.931 | homogeneous Next.js components — siblings lexically indistinguishable (a real ceiling) |
| Lucky/backend | 3,252 | 0.944 | largest tree; one Prometheus-registry-vs-middleware vocabulary-drift miss |

The structural finding (also in `METHODOLOGY.md`): **corpus module clarity predicts Hit@1 better than language or size** — clean functional boundaries score high; same-layer sibling components are the genuine ceiling.

## Reproduce
The raw run is `results.tsv` (kept out of the package). Per-repo: `clone → ragcore.build → hitgate.generate → hitgate.run`. Re-run any single corpus with the [Quickstart](../README.md#quickstart-reproducible-in-10s).
