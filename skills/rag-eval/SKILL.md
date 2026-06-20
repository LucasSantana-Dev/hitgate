# /rag-eval

Run the retrieval regression gate against the current repo state and report whether a recent change helped, hurt, or held steady.

## When to invoke

- User runs `/rag-eval` or `/rag-eval <label>`
- User has changed files under `ragcore/`, `eval/`, or retrieval config and is about to commit or push
- User asks "did this change affect retrieval quality?" or "is it safe to ship?"

## Steps

### 1 — Determine the label

Use the argument if provided, otherwise use `rolling`.

### 2 — Run the gate

```bash
bash eval/check.sh <label>
```

Set env vars if configured for a non-default corpus or retriever (see `README.md` in this skill folder):

```bash
RAG_SOURCE_ROOTS="..." RAG_EVAL_DATASET="..." RAG_EVAL_BASELINE="..." EVAL_EXTRA_FLAGS="..." \
  bash eval/check.sh <label>
```

If the command exits non-zero AND no baseline file exists at the configured path, skip to the **No baseline** branch below.

### 3 — Read the structured verdict

```bash
cat eval/<label>.verdict.json
```

### 4 — Report in plain language

**Pass** (`verdict: "pass"`):
> Gate passed. Hit@5 held [base → current]. MRR [base → current]. [Note any improvement in Hit@1 or MRR if `improvements` list is non-empty.]

**Improvement** (`verdict: "improvement"`, `refreeze_recommended: true`):
> Gate passed and Hit@5 improved [base → current, +Xpp]. The frozen baseline is now stale in the positive direction — consider re-freezing:
> ```bash
> cp eval/<label>.json eval/baseline.example.json
> ```

**Regression** (`verdict: "regression"`):
> Regression: [for each item in `regressions`, state scope + metric + delta in pp]. Next: run the eval in verbose mode to see which cases are now missing:
> ```bash
> python eval/run.py --verbose --label <label>
> ```
> Then inspect the MISS rows for the affected intent class.

**No baseline found** (baseline path does not exist):
> No baseline at [path]. To create one:
> ```bash
> python eval/run.py --label baseline-v1
> cp eval/baseline-v1.json eval/baseline.example.json
> ```
> Then re-run `/rag-eval` to compare against it.

### 5 — Surface failing cases on regression

Read `eval/<label>.json` → `per_case`. Filter to entries where `hit_rank` is null and `intent` matches the regressed class. Show up to 3 as:

```
MISS  intent:indexing  "how does the chunker handle AST symbols"  → expected: chunkers.py
```

This saves the developer from opening the JSON file manually.

## Portability

See `README.md` in this skill folder to adapt for your own retriever, corpus, and baseline.
