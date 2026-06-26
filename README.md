# hitgate

[![eval-gate (advisory)](https://github.com/LucasSantana-Dev/hitgate/actions/workflows/eval.yml/badge.svg)](https://github.com/LucasSantana-Dev/hitgate/actions/workflows/eval.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**Evaluate your RAG retrieval without labeled datasets** — a regression-gated quality harness for retrieval ranking, built around a small hybrid retriever. Measure whether a change helps or hurts when you have no labels, no users to A/B against, and no budget for manual annotation.

## The Problem

Building RAG systems is straightforward. Knowing whether a change made retrieval better or worse is hard — especially with a small corpus and no production telemetry. You can't A/B test with one user. You can't afford hand-labeled golden sets. LLM judges are expensive and opaque.

**hitgate solves one specific problem:** detect retrieval regressions label-free. Like a test suite for ranking quality.

## What hitgate Does (and Doesn't)

✓ **Proves whether retrieval improved or regressed** between two runs (regression detection)  
✓ **Works with zero labeled data** — no golden sets required to start  
✓ **Gates on measurable deltas** — reports Hit@K, MRR, per-intent breakdown  
✓ **Plugs into your retriever** — point `--retriever` at any callable `(query, top, scope) → [results]`  

✗ **Does not measure absolute quality** — Hit@5=1.0 on a self-indexed corpus is optimistic by design  
✗ **Not a framework or hosted service** — a harness you fork and customize  
✗ **Not a maintained product** — personal tooling shared for the methodology  

> **Comparison to RAGAS / DeepEval / Braintrust:** Those tools gate *answer* quality (faithfulness, relevancy) via labeled golden sets or LLM judges. hitgate gates *retrieval ranking* label-free. Different layer, complementary — and the only one that requires zero labels to start. Full comparison: [**docs/COMPARISONS.md**](docs/COMPARISONS.md).

---

## Quick Start (10 seconds)

```bash
pip install -e ".[hybrid]"   # harness + bundled hybrid retriever

# Index a repo and run the eval gate
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build
RAG_RERANK_AUTO=off python -m hitgate.run --label demo

# ...or point the gate at YOUR retriever
python -m hitgate.run --retriever myretriever:retrieve --label mine
```

What you get: Hit@5, Hit@1, MRR + per-case breakdown showing which queries failed and why.

---

## How It Works

### Hybrid Retrieval

- **Dense embeddings** (`intfloat/multilingual-e5-small`) + **BM25 lexical search**  
- **Reciprocal Rank Fusion** to combine both signals  
- **Code-aware tokenizer** — splits `camelCase`/`snake_case` so "get user profile" matches `getUserProfile`  
- **Language-aware chunking** — Python via AST, TS/JS/Shell via regex, fallback to word count  
- **Optional reranking** — cross-encoder scoped to code queries only, graceful fallback if unavailable  

### The Eval Gate

1. **Run your retriever** against a golden set of queries (you write 20–50 JSON cases)
2. **Measure Hit@1/3/5, MRR** — does the expected file rank in top K?
3. **Freeze a baseline** when you like the results
4. **Gate future changes** — CI exits 1 if any metric regresses by >5pp

Config via env var (`RAG_*`); see [`ragcore/config.py`](./ragcore/config.py).

---

## Metrics Explained

| Metric | Meaning |
|--------|---------|
| **Hit@K** | % of queries where the expected file appears in top K results |
| **Hit@5** | Regression-gated headline metric (allows room for ranking imprecision) |
| **Hit@1** | Perfect-ranking metric (strict but useful for identifying misses) |
| **MRR** | Mean Reciprocal Rank — average of `1/rank` across queries |

Self-indexed results are optimistic by construction — **point the gate at your own retriever for numbers that mean something.**

---

## Bring Your Own Retriever — 4-Step Quickstart

A retriever is any callable:
```python
retrieve(query: str, top: int, scope: str | None) -> Sequence[Mapping]
# Results ranked best-first; each a Mapping with at least "path" (optionally "start_line")
```

### 0. Bootstrap candidate golden cases (optional)

```bash
RAG_SOURCE_ROOTS="/path/to/corpus" python -m hitgate.generate \
    --output hitgate/candidates.jsonl \
    --min-confidence medium
```

Review and curate to remove vague queries or wrong expected paths.

### 1. Write golden cases

```jsonl
{"query": "how does pagination work", "expect_path_contains": "api/pagination.py", "expect_scope": "code"}
{"query": "rate limit config", "expect_path_contains": "config/limits.yaml", "expect_scope": "code"}
```

Aim for 20–50 cases mixing identifier lookups and paraphrased queries. Save as any `.jsonl`.

### 2. Run your retriever

```bash
python -m hitgate.run \
    --retriever mypkg.myretriever:retrieve \
    --dataset   my_golden.jsonl \
    --label     baseline-v1
```

Outputs `hitgate/baseline-v1.json` with Hit@1/3/5/MRR + per-case breakdown.

### 3. Freeze the baseline

```bash
cp hitgate/baseline-v1.json hitgate/baseline.myproject.json
```

Edit `_note` to record conditions: corpus, model, date.

### 4. Gate future runs

```bash
BASELINE_FILE=hitgate/baseline.myproject.json \
python -m hitgate.run --retriever mypkg.myretriever:retrieve --dataset my_golden.jsonl --label ci

bash hitgate/check.sh hitgate/ci.json hitgate/baseline.myproject.json
# Exits 1 if any metric regresses >5pp
```

**Drop-in CI:** [`examples/retrieval-gate.yml`](examples/retrieval-gate.yml)

### Diff two runs case-by-case

```bash
python -m hitgate.diff hitgate/baseline-v1.json hitgate/ci.json
```

---

## Architecture & Performance

### Self-Indexed Demo (Reproducible)

| Metric | Value |
|---|---|
| **Hit@5** (code scope, pure hybrid) | **0.99** |
| Hit@1 | 0.636 |
| MRR | 0.784 |
| Corpus | this repo, self-indexed · 99 cases |

63 of 99 hit at rank 1; misses kept on purpose (no quiet dropping). Why Hit@5 is the gate: as the corpus grows, borderline cases drift rank. Hit@5 tolerates that noise; Hit@1 is for strict ranking.

### External Corpus Benchmarks (Zero Tuning)

| Corpus | Language | n | Hit@5 | Hit@1 | MRR |
|---|---|---|---|---|---|
| FastAPI v0.115 | Python | 25 | **1.0** | 0.64 | 0.79 |
| forge-space / mcp-gateway | TypeScript | 20 | **1.0** | 0.70 | 0.821 |
| portfolio / src | React/TS | 15 | **1.0** | 0.60 | 0.778 |
| ai-dev-toolkit / packages/core | Python + TS | 20 | **1.0** | 0.85 | 0.925 |
| homelab / homelab_manager | Python | 20 | 0.950 | 0.85 | 0.900 |
| Lucky / packages/backend | TypeScript | 21 | 0.905 | 0.71 | 0.810 |
| Criativaria / web-app | Next.js/TS | 27 | 0.741 | 0.59 | 0.660 |

**Finding:** corpus module clarity predicts Hit@1 better than language or size. Clean functional boundaries → 0.85. Same-layer UI components → 0.59. Same tokenizer, zero corpus-specific tuning.

**Selection bias:** FastAPI is third-party; six of seven are the author's own repos. See [docs/SWEEP.md](./docs/SWEEP.md) for a broader 63-repo sample.

Full methodology and miss taxonomy: [docs/METHODOLOGY.md](./docs/METHODOLOGY.md)

---

## Use Cases

### AI Assistant Memory
Gate retrieval quality in RAG-backed chatbots or assistants. Detect when corpus updates or embedding model swaps regress search. Deployed version of this exact use case: [docs/two-channel-fastapi.md](./docs/two-channel-fastapi.md) (auto-mined Hit@5=1.0 vs hand-labeled=0.92).

### Document / Knowledge Base Search
Keep search quality stable as your docs grow. No user click data? Gate on retrievability. Ecosystem wrappers for LangChain / LlamaIndex: [adapters/README.md](./adapters/README.md).

### Code Search
Find code references and definitions. The hybrid retriever knows `camelCase` — useful for codebases with identifier-heavy queries. Same gate works for private codebases.

---

## Extending

Core indexes code + docs + commits, nothing else. Tool-specific sources (assistant transcripts, code-graphs, other memory stores) plug in as optional adapters — [adapters/README.md](./adapters/README.md).

---

## What to Adopt (and What to Skip)

**Adopt:** The harness (`hitgate/`) — label-free regression gating and the `--retriever` interface. Plug in your own retriever.

**Skip:** 
- Not a framework or hosted service (no plugin marketplace, no SaaS)
- Not state-of-the-art retrieval research (pragmatic, single-user, knows its ceiling)
- Not a maintained product (solo operator's personal tool; best-effort, no SLA)

Deliberately omitted: `CONTRIBUTING`, issue templates, badge walls. [DECISIONS.md](./DECISIONS.md) records what's left out on purpose and when it might reopen.

---

## Next Steps

- **[Quick Start](#quick-start-10-seconds)** — run in 10 seconds
- **[METHODOLOGY.md](./docs/METHODOLOGY.md)** — how the measurements work and their limits  
- **[COMPARISONS.md](./docs/COMPARISONS.md)** — vs RAGAS, DeepEval, Braintrust, and hand-labeling  
- **[ROADMAP.md](./ROADMAP.md)** — candidate experiments (no commitments)  
- **[DECISIONS.md](./DECISIONS.md)** — what's out of scope and why  
- **[CONTEXT.md](./CONTEXT.md)** — full vocabulary and decision history  

---

## License

MIT — see [LICENSE](./LICENSE).
