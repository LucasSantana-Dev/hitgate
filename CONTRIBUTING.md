# Contributing

## Eval baselines and cross-platform drift

Baselines for the eval gate are **frozen on the CI platform (Ubuntu/Linux)** to ensure consistent gating regardless of developer platform.

### Why: Cross-platform float variance

Floating-point operations differ between macOS and Linux. The reranker and embedding models produce ~2 percentage points of drift in Hit@K metrics:
- Local (macOS): Hit@1 = 0.707
- CI (Ubuntu): Hit@1 = 0.646

This is **expected and not a regression**. It reflects platform-specific numerical precision, not a code change.

### Re-freezing baselines

Baselines live in:
- `hitgate/baseline.example.json` — rerank-off gate (hard gate, blocks CI)
- `hitgate/baseline.auto-rerank.json` — auto-rerank gate (advisory gate)

If you need to re-freeze after a meaningful eval change:

#### Option 1: GitHub workflow (recommended)

```bash
gh workflow run regenerate-baseline.yml --repo=LucasSantana-Dev/evidence-first-rag
```

Then download the `regenerated-baselines` artifact from the workflow run and commit:
```bash
cp regenerated-baselines/ci.json hitgate/baseline.example.json
cp regenerated-baselines/auto-rerank-ci.json hitgate/baseline.auto-rerank.json
git add hitgate/baseline.*.json && git commit -m "ci(eval): re-freeze baselines from regenerate-baseline workflow"
```

#### Option 2: Local script on Linux

```bash
bash scripts/regenerate-baseline.sh
```

This automatically freezes both baselines in place. On non-Linux platforms, the script prints guidance and exits; use Option 1 instead.

#### Option 3: Emergency override on any platform

```bash
FORCE=1 bash scripts/regenerate-baseline.sh
```

Only use this if you cannot access the workflow. Expect ~2pp drift vs CI if running on macOS.

### What the gates measure

- **`hitgate/check.sh ci`** (hard gate): Runs eval with reranking OFF. Fails if any metric (aggregate Hit@1/3/5, per-intent Hit@5) drifts >5pp from baseline.
- **`hitgate/check.sh auto-rerank-ci`** (advisory): Runs eval with auto-reranking ON. Advisory because reranker cross-encoder ordering varies per platform.

See `docs/adr/0005-auto-rerank-calibration.md` for eval design details.
