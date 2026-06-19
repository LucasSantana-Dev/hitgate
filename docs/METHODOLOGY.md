# Methodology: measuring retrieval quality without labels

The retriever in this repo is ordinary — dense embeddings, BM25, reciprocal rank fusion.
The part worth your attention is how every claim about it is *checked*: with a small golden
set, a frozen baseline, and a refusal to assert any number that didn't come out of an actual
`eval/run.py` run. This page is the worked argument for three design choices, each backed by a
real ablation — including, prominently, the places where the measurement **contradicts** the
design. That contradiction is the point.

Every number below is reproducible with the commands shown, on the 23-case code demo
(`eval/golden.demo.jsonl`), self-indexed over this repo, pure hybrid unless stated.
The golden set was expanded from 12 → 17 → 23 cases across three sessions; numbers
reflect the full 23-case set (12 identifier + 11 paraphrase queries).

## The ablation

```bash
RAG_SOURCE_ROOTS="$PWD" python ragcore/build.py
RAG_RANK_MODE=bm25   RAG_RERANK_AUTO=off python eval/run.py --label abl-bm25
RAG_RANK_MODE=dense  RAG_RERANK_AUTO=off python eval/run.py --label abl-dense
RAG_RANK_MODE=hybrid RAG_RERANK_AUTO=off python eval/run.py --label abl-hybrid
RAG_RANK_MODE=hybrid                     python eval/run.py --label abl-hybrid-rerank --rerank
```

Current numbers on the 23-case golden set (12 identifier + 11 paraphrase queries):

| Rank mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| BM25-only | 0.522 | 0.783 | 0.826 | 0.639 |
| dense-only | 0.478 | 0.783 | 0.826 | 0.617 |
| **hybrid (RRF + symbol boost)** | 0.348 | 0.783 | **0.913** | 0.579 |

The 23-case set tells the most complete story. BM25 wins precision (Hit@1=0.522, MRR=0.639)
because 12/23 cases are identifier-match queries where lexical overlap dominates. Dense wins
the indexing intent class (Hit@5=1.0, see below) because paraphrase indexing queries
("collects top results as bundle", "third-party document finder") are semantically richer
than their code. Hybrid achieves the best overall Hit@5 (0.913) — the only mode that holds
Hit@5=1.0 on both retrieval and infrastructure simultaneously — at the cost of Hit@1 and MRR.

Per-intent breakdown (Hit@5 across three modes, 23-case set):

| Rank mode | retrieval (n=9) | indexing (n=7) | infrastructure (n=7) |
|---|---|---|---|
| BM25-only | 0.889 | 0.714 | 0.857 |
| dense-only | 0.778 | **1.0** | 0.714 |
| **hybrid** | **1.0** | 0.714 | **1.0** |

The per-intent table makes the tradeoffs precise:
- BM25 wins precision on retrieval queries (identifier/API names) but misses paraphrase indexing cases.
- Dense achieves perfect indexing Hit@5 (all paraphrase indexing queries resolved semantically) but collapses on infrastructure (adapters, tooling).
- Hybrid maintains perfect Hit@5 on both retrieval and infrastructure; indexing is the remaining gap (0.714) — two chunkers.py paraphrase cases remain persistent misses regardless of mode, one recoverable by the reranker.

## Why hybrid + RRF — the story that got clearer as the golden set grew

On the original 12-case identifier-only set, hybrid beat *neither* BM25 nor dense. The
honest headline was "the dumbest configuration wins." That finding still holds for
identifier queries: BM25 wins Hit@1 (0.522 on the full 23-case set, vs hybrid's 0.348)
and the dense channel adds noise on code symbols where BM25 already has the answer.

The 23-case set reveals where the design's bet pays off. Hybrid is the *only* mode that
achieves Hit@5=1.0 on both `retrieval` and `infrastructure` simultaneously — despite BM25
winning raw precision and dense winning indexing. The RRF fusion threads the needle across
all three intent classes. The cost is precision: hybrid's Hit@1 (0.348) is the lowest of
the three modes, because the dense channel sometimes elevates a semantically close but
rank-2 match above the BM25-confident rank-1 hit.

**What changed the answer over three iterations:** the golden set's composition. At 12
identifier cases, BM25 wins everything. At 17 (adding 5 paraphrase cases), hybrid's
Hit@5 advantage became visible. At 23 (11 paraphrase), the intent-class picture is
complete: hybrid is the only mode that prevents any class from collapsing. Two chunkers.py
paraphrase cases remain persistent misses regardless of mode — a vocabulary gap deeper
than either channel can bridge without reranking.

## Why reranking is gated, not global

The reranker story on the 17-case set is more nuanced but the production policy unchanged.
Forcing `ms-marco-MiniLM-L-6-v2` to rerank every query improves indexing (Hit@5 0.833→1.0,
recovering the "assigns content category" paraphrase case) but collapses infrastructure
(Hit@5 1.0→0.75) and drops retrieval MRR (0.679→0.595). The infrastructure collapse is the
same failure mode as on the 12-case set — a general-purpose NL-passage reranker incorrectly
reorders config and tooling lookups. The aggregate Hit@5 is unchanged (0.941), masking the
intra-class trade.

The measured argument for the production policy remains: rerank is **off by default** and
fires only on *weak or ambiguous* queries (auto-trigger on a low top-1 cosine or a thin
top-1/top-2 margin), with the heavier code-tuned reranker confined to code scope.

> Honest boundary: the companion claim — that reranking *also* regresses prose/memory retrieval —
> is **not reproducible on this public demo**, which is 100% code-scope. It was measured on a
> private mixed corpus (see [DECISIONS.md](../DECISIONS.md)); it is stated there, not re-derived
> here, and no prose number is implied on this page.

## Reranker Pareto table — quality vs size vs latency

Measured on the 17-case golden set, hybrid mode, CPU (Apple M1):

| Model | Size | Warm latency¹ | Hit@1 | Hit@5 | MRR | Infra Hit@5 |
|---|---|---|---|---|---|---|
| *(no rerank)* | — | 0 ms | 0.471 | **0.941** | 0.681 | **1.0** |
| `ms-marco-MiniLM-L-6-v2` *(default)* | 88 MB | 48 ms | 0.529 | **0.941** | 0.696 | 0.75 |
| `BAAI/bge-reranker-v2-m3` | 2.1 GB | 88 ms | **0.647** | **0.941** | **0.767** | **1.0** |

¹ Warm = model already loaded; measured over 5 runs, top-5 candidates per query.

**Reading the table:** `bge-reranker-v2-m3` is strictly better than `ms-marco-L-6-v2`
on every quality metric — +12pp Hit@1, +7pp MRR — and crucially does *not* collapse
infrastructure Hit@5 the way ms-marco does (1.0 vs 0.75). The latency trade is modest:
88ms vs 48ms warm, both well under any interactive budget. The only reason to prefer
ms-marco is size: 88MB is a no-friction install; 2.1GB requires the user to have disk
space and patience. The default therefore stays `ms-marco-L-6-v2`; set
`RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3` when you can afford the footprint.

**What the table cannot say:** both models were measured only on this repo's 17-case
code-only set. Neither model's behaviour on prose, memory, or mixed corpora is captured
here. The private-corpus finding (that reranking regresses prose) was measured with
ms-marco; whether bge-v2-m3 also regresses prose is unknown and not implied.

## Why Hit@5 is the gated metric

![Hit@5 per commit](./hit5_history.svg)

Hit@1 ranges from 0.304 to 0.522 across modes on the 23-case set; MRR from 0.562 to 0.639
— large swings driven by single cases flipping between rank 1 and rank 2. Hit@5 is tighter:
0.826 for BM25 and dense, 0.913 for hybrid. On a set this small, Hit@1 and MRR are
noise-prone and Hit@5 is the stable signal. A regression gate should fire on real
degradation, not on a borderline case slipping from rank 1 to rank 2 — so the gate
(`eval/check.sh`, ±5pp) is anchored on Hit@5 and the README leads with it. The other
metrics are always reported, never hidden; they're just not what the gate trusts.

## Contextual chunk prefixing — three-stage experiment

Each chunk is embedded with a short context line prepended — `source_type | repo | filename | symbol` — before the E5 `passage:` prefix. The hypothesis: this helps the dense channel disambiguate same-named symbols and improves recall on natural-language (paraphrase) queries where the query shares no tokens with the implementation.

**Stage 1 (12-case identifier set):** null result — WITH and WITHOUT prefix both produced MRR=0.778, Hit@1=0.583. Expected: all 12 cases are BM25-dominant identifier lookups.

**Stage 2 (17-case, +5 paraphrase):** positive — +0.050 MRR, +0.059 Hit@1, 0.0 Hit@5 delta. The gain came from one case where the prefix added `config.py` as a semantic anchor, jumping rank 5→1.

**Stage 3 (23-case, +11 paraphrase)** refined the picture:

| Prefix mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| WITHOUT context prefix | 0.304 | 0.739 | **0.957** | 0.562 |
| **WITH context prefix (default)** | **0.348** | **0.783** | 0.913 | **0.579** |
| **Delta** | **+0.044** | **+0.044** | **−0.044** | **+0.017** |

The Hit@5 regression (−0.044) is new. It is driven by a single case: "breaks source code at logical declaration boundaries" targeting `chunkers.py` drops from rank 5 (WITHOUT) to MISS (WITH prefix). Root cause: the prefix context (`"code | … | chunkers.py | chunk_python"`) causes the dense channel to score `build.py` chunks higher on a query that mentions "source code" — semantically overlapping tokens that the prefix amplifies.

**The full picture:** prefix is a *precision optimizer*, not a *coverage optimizer*.

| Effect | Mechanism |
|---|---|
| Gains where filename = semantic anchor | "folder names" → config.py; "auto rerank" → retrieval.py |
| Neutral when prefix adds no new signal | pack.py, mcp_server.py — rank unchanged in both modes |
| Loses where prefix causes false positives | "source code… fragments" → build.py outscores chunkers.py |
| Recoverable via reranker | chunkers.py miss goes rank 6 → 1 with cross-encoder reranking |

The decision to ship default-on stands: cost is zero (prefix used at embed time only, not stored), MRR direction remains positive (+0.017 on 23 cases), and the one reproducible Hit@5 regression is compensated by the gated reranker. See [ADR-0004](docs/adr/0004-chunk-prefixing-experiment-bar.md) for the full three-stage experiment record.

## The discipline underneath all three

Each section is the same loop, applied: run the real eval, read the delta *especially* when it's
unflattering, decide, and write down what would change the answer. The ablation knob
(`RAG_RANK_MODE`) and the history script (`eval/plot_history.py`) exist so a reader can re-run
every claim here and catch us if a number drifts. A measurement system whose own demo shows the
simple baseline winning — and says so in the headline — is the asset this repository exists to
demonstrate. The retriever is just the thing being measured.
