# Portfolio benchmark — hitgate across 70 real repositories (auto-generated sweep)

A breadth check: the same hitgate pipeline, zero per-repo tuning, run against **every code
repository in one maintainer's GitHub footprint** — personal account + five organizations. It
complements the small, hand-curated [7-corpus benchmark](METHODOLOGY.md#external-corpus-benchmarks):
that one is *deep* (manual curation, adversarial queries); this one is *wide* (70 repos, fully
automated).

## Read this first — what this sweep does and does not prove

Every golden set here was **auto-generated** (`hitgate.generate --min-confidence medium`, heuristic,
no LLM) from each repo's own symbols and docstrings — **not** hand-written. That has a direct
consequence you must read the numbers through:

- **Hit@5 saturates (median 1.0) and is *not* the signal.** When the query is derived from a file's
  own identifiers, retrieval almost always surfaces that file somewhere in the top 5. A high Hit@5
  here is close to tautological.
- **Hit@1 and MRR are the signal.** The auto-query still has to win **rank 1** against the *entire*
  corpus — every other file competing on the same vocabulary. That is a real, if easier-than-human,
  test of ranking quality.
- **This is a floor-of-generalizability signal, not a difficulty benchmark.** Auto-queries are
  easier than the adversarial paraphrases a human writes. For the hard, curated test see
  [METHODOLOGY.md](METHODOLOGY.md); read this page for *consistency at breadth*.

No repo was tuned, excluded for looking bad, or curated. Skips and weak performers are listed in full
below — leaving the misses in is the [first thing this project refuses to fake](../DECISIONS.md).

## Headline

| | |
|---|---|
| Repos targeted | 70 (LucasSantana-Dev + 5 orgs, non-fork, with code) |
| **Evaluated** | **63** (7 skipped — too few high-signal auto-cases) |
| Auto-generated cases | **15,232** |
| **Hit@1** (right file at rank 1) | **mean 0.800 · median 0.811** |
| Hit@5 | mean 0.984 · median 1.000 *(saturated — see caveat)* |
| MRR | mean 0.882 |

**The right file is ranked #1 about 80% of the time across 63 real, untuned, heterogeneous
codebases.** That is the result that matters: the retriever generalizes far past the repo it was
built on.

## By language — structure, not language, drives the variance

| Language | repos | cases | Hit@1 (mean / median) | Hit@5 mean | MRR mean |
|---|---|---|---|---|---|
| TypeScript | 33 | 10,502 | 0.780 / 0.807 | 0.979 | 0.867 |
| Shell | 17 | 1,917 | 0.833 / 0.814 | 0.994 | 0.909 |
| Python | 9 | 2,351 | 0.788 / 0.811 | 0.983 | 0.871 |
| JavaScript | 3 | 382 | 0.886 / 0.897 | 0.990 | 0.932 |
| Java | 1 | 80 | 0.713 / 0.713 | 0.988 | 0.835 |
| **All** | **63** | **15,232** | **0.800 / 0.811** | **0.984** | **0.882** |

Hit@1 sits in a tight 0.71–0.89 band across five languages. This **reconfirms at scale** the
[curated benchmark's finding](METHODOLOGY.md#cross-corpus-summary): corpus *structure* (how clearly
modules are separated) predicts performance more than language does.

## Hit@1 distribution (the real signal)

```
min 0.250   p25 0.723   median 0.811   p75 0.882   max 1.000
Hit@5 == 1.0 in 33/63 repos · Hit@5 < 0.95 in only 5 repos
```

## Where it shines, and where it struggles (no cherry-picking)

**Top (Hit@1):** `star-wars-starships-frontend` (1.000), `ai-dev-toolkit-setup` (1.000),
`portfolio` (0.963), `rent-calculation` (0.955), `Lucky-redesign` (0.955).

**Weakest (Hit@1):** `pokedex` (0.250, n=12 — tiny repo, the small-n noise the curated methodology
warns about), `homelab-old` (0.586), `liraflix` (0.624), `radinho-paradise-fivem` (0.632),
`mcp-dev-tools` (0.645).

**The 5 repos where even Hit@5 < 0.95** — all TypeScript, all the same structural cause (sibling
components/modules sharing vocabulary):

| Repo | Hit@5 | Hit@1 | n |
|---|---|---|---|
| LucasSantana-Dev/pokedex | 0.917 | 0.250 | 12 |
| Criativaria-Projects/web-app | 0.931 | 0.690 | 216 |
| LucasSantana-Dev/Lucky | 0.944 | 0.697 | 3,252 |
| vsantana-organization/EduBank | 0.944 | 0.822 | 90 |
| Life-Connect-Organization/Life-Connect | 0.947 | 0.735 | 1,391 |

**Consistency check that matters:** `Criativaria/web-app` lands at Hit@5 = 0.931 here, echoing its
**0.741 on the hand-curated set** — the *same* homogeneous Next.js component-library ceiling, surfaced
by two independent methods. The auto-sweep is easier (0.931 > 0.741), but it points at the same weak
spot. That cross-method agreement is the strongest evidence in this page.

## Skipped (honest accounting — 7 repos)

Skipped because `--min-confidence medium` produced fewer than 8 high-signal cases (small, template, or
docstring-sparse Kotlin/Java repos):
`verificador-cpf`, `nlw-setup`, `Fintech-fiap/public_security`, `Fintech-fiap/LocaWeb_Challenge`,
`Fintech-fiap/smartHealthMap`, `Criativaria/video-0608-deepseek`, `Fintech-fiap/fintech`.

Full per-repo results: [`portfolio-benchmark.tsv`](portfolio-benchmark.tsv).

## Reproduce

Per repo, the pipeline is the standard external-corpus flow, fully automated (no manual curation):

```bash
export RAG_INDEX_DIR="$CLONE/.rag-index" RAG_SOURCE_ROOTS="$CLONE"
python -m ragcore.build                                              # index that repo
python -m hitgate.generate --output golden.jsonl --min-confidence medium   # auto golden set
python -m hitgate.run --dataset golden.jsonl --label <repo>          # Hit@K / MRR
```

## What this adds (and what it doesn't)

**Adds:** a generalizability floor — hitgate ranks the right file #1 ~80% of the time across 63 real,
untuned codebases spanning five languages and six owners, with the variance tracking module structure
exactly as the curated benchmark predicted.

**Doesn't:** prove difficulty-robustness. Auto-generated queries are easier than human paraphrases;
the saturated Hit@5 is an artifact of that, not a quality claim. The curated 7-corpus benchmark
remains the rigorous test; this is the wide-angle companion.
