# hitgate 0.1.0

A **pytest-style, label-free regression gate for retrieval quality** — plus the small hybrid retriever it was built to measure. Point it at *your* retriever and find out whether a change helped or hurt, when you have **no labeled data and no users to A/B against**.

## Install
```bash
pip install hitgate            # the harness — measures ANY retriever via --retriever
pip install "hitgate[hybrid]"  # + the bundled BM25+dense+RRF retriever used in the demo
```

## What it does
- **Measures retrieval *ranking* on your own corpus, with no ground-truth labels** — it auto-generates a golden set from your corpus structure and scores Hit@1/3/5 + MRR.
- **A CI regression gate vs a frozen baseline** (`hitgate/check.sh`, ±5pp) — catches "did my last change quietly make retrieval worse," which answer-quality evals (RAGAS/DeepEval) don't.
- **Retriever-agnostic** — any callable `(query, top, scope) -> [{"path": ...}]` works: `python -m hitgate.run --retriever yourmod:fn`.

## Quickstart (reproducible in ~10s)
```bash
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build           # index this repo
RAG_RERANK_AUTO=off python -m hitgate.run --label demo    # -> Hit@5 1.0, Hit@1 0.663, MRR 0.795 (101 self-generated cases)
```

## Be honest about what the numbers mean (read this)
- The label-free golden set is **mined from distinctive terms in your corpus**, so it measures **retrievability / regression — not human-judged relevance.** The self-demo Hit@5 1.0 is reproducible but optimistic *by construction*; on hand-labeled natural-language queries the same engine scores far lower (~0.27 on "where is X defined").
- The benchmark **leaves its misses in** and ships a miss taxonomy — see `docs/METHODOLOGY.md`. The ablation where the *simple* baseline wins (BM25-only Hit@1 0.752 > hybrid 0.663) is published on purpose.
- **Single-author personal tooling, no SLA.** Published for the *methodology* — use it as a regression gate, not a relevance leaderboard.

## What this is NOT
- Not a RAG *answer*-quality eval (faithfulness/groundedness) — use RAGAS / DeepEval / promptfoo for that. hitgate gates **retrieval ranking**, label-free.
- Not a funded product. The bundled retriever is the *thing it measures*, not the pitch.

## Stack
Python · SQLite · sentence-transformers (intfloat/multilingual-e5-small) · optional BAAI/bge-reranker-v2-m3 · BM25 + Reciprocal Rank Fusion · MCP stdio server · code-aware tokenizer (camelCase/snake_case).

**Repo:** https://github.com/LucasSantana-Dev/hitgate · **Methodology:** `docs/METHODOLOGY.md` · **Decisions:** `docs/adr/`
