# Methodology: measuring retrieval quality without labels

The retriever in this repo is ordinary — dense embeddings, BM25, reciprocal rank fusion.
The part worth your attention is how every claim about it is *checked*: with a small golden
set, a frozen baseline, and a refusal to assert any number that didn't come out of an actual
`eval/run.py` run. This page is the worked argument for three design choices, each backed by a
real ablation — including, prominently, the places where the measurement **contradicts** the
design. That contradiction is the point.

Every number below is reproducible with the commands shown, on the 12-case code demo
(`eval/golden.demo.jsonl`), self-indexed over this repo, pure hybrid unless stated.
Numbers were updated after the chunker fix that added module-level constant indexing
(see `docs/adr/0001` and the commit `fix(chunker)`).

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
| **BM25-only** | **0.917** | **1.0** | **1.0** | **0.958** |
| dense-only | 0.667 | 1.0 | 1.0 | 0.806 |
| hybrid (RRF + symbol boost) | 0.667 | 1.0 | 1.0 | 0.833 |
| hybrid + rerank (ms-marco, forced on all) | 0.667 | 0.917 | 0.917 | 0.778 |

Read that table before the rationale, because it refuses to tell the tidy story: **on this
demo, the dumbest configuration wins — by a wider margin than before.**

Per-intent breakdown reveals where each mode actually differs (all Hit@5 shown):

| Rank mode | retrieval | indexing | infrastructure |
|---|---|---|---|
| BM25-only | 1.0 | 1.0 | **1.0** |
| dense-only | 1.0 | 1.0 | 1.0 |
| hybrid | 1.0 | 1.0 | 1.0 |
| hybrid + rerank | 1.0 | 1.0 | **0.667** |

The aggregate masks the reranker's worst failure: it collapses `infrastructure` Hit@5 from 1.0
to 0.667 — two of three infrastructure queries pushed out of the top 5 entirely.

## Why hybrid + RRF — stated against the evidence

The conventional pitch is "hybrid beats either channel alone." Here it beats *neither*.
BM25-only dominates on every axis: Hit@1 0.917 vs. hybrid's 0.667, MRR 0.958 vs. 0.833.
Hit@5 is tied at 1.0 for BM25, dense, and hybrid, so the only differentiation is at
rank 1 — where BM25 wins decisively. An honest reading: **this demo does not justify
hybrid's added complexity.** Two things are true and worth saying out loud:

1. **The corpus is lexical and tiny.** Twelve queries, almost all identifier/keyword lookups
   against code, where BM25 (weighted slightly above dense, `RAG_BM25_WEIGHT=1.5`, plus a
   symbol-definition boost) already lands the answer. Fusion can't improve a channel that's
   already right; it can only add a second opinion that sometimes drags. On the "index recent
   git commits" query, the dense/symbol signal even promotes a *different* file above the
   intended one — which is how hybrid loses 0.25 of Hit@1 to plain BM25 here.
2. **At Hit@5, all three non-rerank modes are equivalent.** The pre-chunker-fix era showed
   dense edging out hybrid at Hit@5 (0.917 vs 0.833). After fixing the chunker gap, that
   edge vanished — the 12 cases are all reachable by all three modes. The Hit@1/MRR
   difference is the real story: BM25's symbol-definition boost puts the right answer first.

So why ship hybrid? Honestly: **not because this demo earns it.** The dense channel is
insurance for paraphrase queries — natural-language questions that share almost no tokens
with the implementation — which a code-only, 12-case demo barely contains. The
measurement's job here is to make that limitation visible, not to manufacture a win. The
contextual-retrieval experiment in [ROADMAP.md](../ROADMAP.md) is exactly the test that
would put hybrid where it should pay off.

## Why reranking is gated, not global

The last row is the cleanest result on the page. Forcing the default cross-encoder
(`ms-marco-MiniLM-L-6-v2`) to rerank **every** query is the *worst* configuration measured:
Hit@5 **1.0 → 0.917**, MRR **0.833 → 0.778**. The per-intent breakdown makes the failure
precise: the reranker collapses `infrastructure` Hit@5 from 1.0 to 0.667 — two of three
infrastructure queries (env-var config, excluded-dirs) pushed out of the top 5. A
general-purpose reranker trained on natural-language passage retrieval reorders code and
config lookups incorrectly. That is the measured argument for the production policy: rerank
is **off by default** and fires only on *weak or ambiguous* queries (auto-trigger on a low
top-1 cosine or a thin top-1/top-2 margin), with the heavier, code-tuned reranker confined
to code scope. "Add a reranker everywhere" is not a free win — here it is a measured loss.

> Honest boundary: the companion claim — that reranking *also* regresses prose/memory retrieval —
> is **not reproducible on this public demo**, which is 100% code-scope. It was measured on a
> private mixed corpus (see [DECISIONS.md](../DECISIONS.md)); it is stated there, not re-derived
> here, and no prose number is implied on this page.

## Why Hit@5 is the gated metric

![Hit@5 per commit](./hit5_history.svg)

This is where the ablation's *noise* becomes the argument. Across the four modes, Hit@1 swings
between 0.667 and 0.917 and MRR between 0.778 and 0.958 — large moves driven by a single case
flipping rank, on a 12-case set. Hit@5, meanwhile, is 1.0 for three of the four modes (and 0.917
for rerank) after the chunker fix that surfaced previously invisible module-level constants. On a
set this small, Hit@1 and MRR are noise-prone and Hit@5 is the stable signal. A regression gate
should fire on real degradation, not on a borderline case slipping from rank 1 to rank 2 — so
the gate (`eval/check.sh`, ±5pp) is anchored on Hit@5 and the README leads with it. The other
metrics are always reported, never hidden; they're just not what the gate trusts.

## Contextual chunk prefixing — null Stage 1 result

Each chunk is embedded with a short context line prepended — `source_type | repo | filename | symbol` — before the passage prefix that E5 requires. The hypothesis: this helps the dense channel disambiguate same-named symbols across files and improves recall on natural-language (paraphrase) queries.

The ablation runs WITH (`RAG_CHUNK_CONTEXT_PREFIX=on`) vs WITHOUT (`=off`) on the 12-case golden set returned identical results:

| Prefix mode | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---|---|
| WITH (default) | 0.583 | 1.0 | 1.0 | 0.778 |
| WITHOUT | 0.583 | 1.0 | 1.0 | 0.778 |

Null result: no measurable difference on this set. The explanation is the same as why BM25 dominates: 12 identifier/keyword queries give the dense channel no paraphrase surface to work with. The feature stays on (it costs nothing at runtime) and the experiment moves to Stage 2 — adding 3–5 paraphrase golden cases where it should matter. See [ADR-0004](../docs/adr/0004-chunk-prefixing-experiment-bar.md) for the full decision and bar.

This is also when the baseline drifted (MRR 0.833→0.778, Hit@1 0.667→0.583): the new ADR and docs/agents files added competing chunks that pushed the "excluded directories" infrastructure query from rank 1 to rank 3 on config.py. Hit@5 held at 1.0 — the right answer was still retrievable, just not the top result. Baseline re-frozen at the new values; the drift is expected living-corpus behavior.

## The discipline underneath all three

Each section is the same loop, applied: run the real eval, read the delta *especially* when it's
unflattering, decide, and write down what would change the answer. The ablation knob
(`RAG_RANK_MODE`) and the history script (`eval/plot_history.py`) exist so a reader can re-run
every claim here and catch us if a number drifts. A measurement system whose own demo shows the
simple baseline winning — and says so in the headline — is the asset this repository exists to
demonstrate. The retriever is just the thing being measured.
