# Methodology: measuring retrieval quality without labels

The retriever in this repo is ordinary — dense embeddings, BM25, reciprocal rank fusion.
The part worth your attention is how every claim about it is *checked*: with a small golden
set, a frozen baseline, and a refusal to assert any number that didn't come out of an actual
`eval/run.py` run. This page is the worked argument for three design choices, each backed by a
real ablation — including, prominently, the places where the measurement **contradicts** the
design. That contradiction is the point.

Every number below is reproducible with the commands shown, on the 12-case code demo
(`eval/golden.demo.jsonl`), self-indexed over this repo, pure hybrid unless stated.

## The ablation

```bash
RAG_SOURCE_ROOTS="$PWD" python ragcore/build.py
RAG_RANK_MODE=bm25   RAG_RERANK_AUTO=off python eval/run.py --label abl-bm25
RAG_RANK_MODE=dense  RAG_RERANK_AUTO=off python eval/run.py --label abl-dense
RAG_RANK_MODE=hybrid RAG_RERANK_AUTO=off python eval/run.py --label abl-hybrid
RAG_RANK_MODE=hybrid                     python eval/run.py --label abl-hybrid-rerank --rerank
```

| Rank mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| **BM25-only** | **0.750** | 0.833 | 0.833 | **0.792** |
| dense-only | 0.667 | 0.833 | **0.917** | 0.767 |
| hybrid (RRF + symbol boost) | 0.667 | 0.833 | 0.833 | 0.750 |
| hybrid + rerank (ms-marco, forced on all) | 0.583 | 0.833 | 0.833 | 0.708 |

Read that table before the rationale, because it refuses to tell the tidy story: **on this
demo, the dumbest configuration wins.**

## Why hybrid + RRF — stated against the evidence

The conventional pitch is "hybrid beats either channel alone." Here it beats *neither*.
BM25-only has the best Hit@1 (0.750) and MRR (0.792); dense-only has the best Hit@5 (0.917);
hybrid is middling on all three. So an honest reading is that **this demo does not justify
hybrid's added complexity.** Two things are true and worth saying out loud:

1. **The corpus is lexical and tiny.** Twelve queries, almost all identifier/keyword lookups
   against code, where BM25 (weighted slightly above dense, `RAG_BM25_WEIGHT=1.5`, plus a
   symbol-definition boost) already lands the answer. Fusion can't improve a channel that's
   already right; it can only add a second opinion that sometimes drags. On the "index recent
   git commits" query, the dense/symbol signal even promotes a *different* file above the
   intended one — which is how hybrid loses 0.083 of Hit@1 to plain BM25 here.
2. **Dense and lexical have opposite failure shapes.** Dense finds the answer somewhere in the
   top 5 more often (Hit@5 0.917) but ranks it worse at the top; BM25 nails rank 1 but misses a
   couple entirely. Hybrid splits the difference and so wins neither extreme.

So why ship hybrid? Honestly: **not because this demo earns it.** Hybrid is the only config that
is never *worst* on any axis (BM25 is worst on Hit@5, dense worst on Hit@1, rerank worst overall),
and the dense channel is insurance for paraphrase queries — natural-language questions that share
almost no tokens with the implementation — which a code-only, 12-case demo barely contains. The
measurement's job here is to make that limitation visible, not to manufacture a win. The
comparative-baseline and contextual-retrieval experiments in [ROADMAP.md](../ROADMAP.md) are
exactly the tests that would put hybrid where it should actually pay off.

## Why reranking is gated, not global

The last row is the cleanest result on the page. Forcing the default cross-encoder
(`ms-marco-MiniLM-L-6-v2`) to rerank **every** query is the *worst* configuration measured:
Hit@1 **0.667 → 0.583**, MRR **0.750 → 0.708**. A general-purpose reranker, applied
indiscriminately to already-decent lexical rankings, reorders the top and pushes correct rank-1
hits down. That is the measured argument for the production policy: rerank is **off by default**
and fires only on *weak or ambiguous* queries (auto-trigger on a low top-1 cosine or a thin
top-1/top-2 margin), with the heavier, code-tuned reranker confined to code scope. "Add a
reranker everywhere" is not a free win — here it is a measured loss.

> Honest boundary: the companion claim — that reranking *also* regresses prose/memory retrieval —
> is **not reproducible on this public demo**, which is 100% code-scope. It was measured on a
> private mixed corpus (see [DECISIONS.md](../DECISIONS.md)); it is stated there, not re-derived
> here, and no prose number is implied on this page.

## Why Hit@5 is the gated metric

![Hit@5 per commit](./hit5_history.svg)

This is where the ablation's *noise* becomes the argument. Across the four modes, Hit@1 swings
between 0.583 and 0.750 and MRR between 0.708 and 0.792 — large moves driven by a single case
flipping rank, on a 12-case set. Hit@5, meanwhile, is 0.833 for three of the four modes and has
**held flat at 0.833 across every commit that shipped the harness** (the chart above; regenerate
with `python eval/plot_history.py`) even as the self-indexed corpus grew. On a set this small,
Hit@1 and MRR are noise-prone and Hit@5 is the stable signal. A regression gate should fire on
real degradation, not on a borderline case slipping from rank 1 to rank 2 — so the gate
(`eval/check.sh`, ±5pp) is anchored on Hit@5 and the README leads with it. The other metrics are
always reported, never hidden; they're just not what the gate trusts.

## The discipline underneath all three

Each section is the same loop, applied: run the real eval, read the delta *especially* when it's
unflattering, decide, and write down what would change the answer. The ablation knob
(`RAG_RANK_MODE`) and the history script (`eval/plot_history.py`) exist so a reader can re-run
every claim here and catch us if a number drifts. A measurement system whose own demo shows the
simple baseline winning — and says so in the headline — is the asset this repository exists to
demonstrate. The retriever is just the thing being measured.
