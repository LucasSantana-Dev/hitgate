# A worked example: auditing an eval set for contamination

[DECISIONS.md](../DECISIONS.md) states the discipline in one rule — *measure →
challenge → decide → record the trigger that would reopen it* — and names the
contamination audit as the decision everything else depends on. This page makes that
one loop concrete and hands you the script to run it yourself
([`hitgate/audit_contamination.py`](../hitgate/audit_contamination.py)).

The point isn't the contamination finding. It's that "is my benchmark honest?" is a
question you can *answer mechanically* instead of assuming.

## Measure

The retrieval eval reported a Hit@5. Taken at face value, it said "the system finds
the right file 5-of-N times." But a number is only as honest as the cases behind it,
so the first measurement wasn't of the retriever — it was of the **eval set**: for
each golden case, *is the expected answer even in the indexed corpus?*

A case whose answer isn't in the corpus is **un-winnable**. It can only ever miss. A
cluster of them doesn't measure retrieval quality — it subtracts a constant, and that
constant looks exactly like a quality floor you can't get above.

## Challenge

The adversarial question: *if I removed the cases the system literally cannot win,
would the number change enough to have been lying?*

To answer it you don't need judgment — you need set membership. For each case, check
whether any indexed chunk's path matches the expected path. Three outcomes:

- **ok** — the answer is indexed within the case's declared scope.
- **scope-mismatch** — the answer is indexed, but only *outside* the declared scope
  (a softer problem: the case or the scope label is wrong, but it isn't un-winnable).
- **CONTAMINATED** — the answer isn't in the corpus at all. Un-winnable.

That is the entire logic of [`hitgate/audit_contamination.py`](../hitgate/audit_contamination.py).

## Decide

On this project's original (internal) eval, removing the un-winnable cases moved the
baseline by **~8 percentage points** (see [DECISIONS.md](../DECISIONS.md) §1). The
decision that came out of it is a standing rule, not a one-off fix:

> A benchmark you haven't audited for contamination is worse than no benchmark —
> it attaches a number to false confidence.

The honesty shows up in the public demo too: the cases the system *loses* are left in
on purpose. Those are winnable-but-lost (real misses worth keeping), which is the
opposite of contaminated (un-winnable, worth removing). The audit is how you tell the
difference instead of guessing.

## Record the reopen trigger

The audit isn't a thing you did once; it's a gate you re-run. Reopen it when:

- you add or remove cases from an eval set, or
- the corpus changes shape (files move/rename, an ingester changes what gets indexed), or
- you're about to trust a number from an eval set you didn't audit.

## Run it on your own eval set

```bash
# Index a corpus, then audit any eval set with the same schema as hitgate/golden.demo.jsonl
RAG_SOURCE_ROOTS="$PWD" python -m ragcore.build
RAG_SOURCE_ROOTS="$PWD" python -m hitgate.audit_contamination                       # audits hitgate/golden.demo.jsonl
RAG_SOURCE_ROOTS="$PWD" python -m hitgate.audit_contamination --dataset your_eval.jsonl
```

Exit code is the contract: **0** if every case's answer is in the corpus, **1** if any
case is un-winnable — so you can wire it into a build the same way as the eval gate.

## What it does and doesn't prove

- It proves the expected answer **is in the corpus** — the necessary condition for a
  case to be winnable. It does **not** prove the answer is *correct* or that the
  retriever *ranks* it well; that's what the eval (`hitgate/run.py`) measures.
- **scope-mismatch** is a warning, not a failure — it usually means a mislabeled scope,
  not a poisoned benchmark, so the gate doesn't fail on it.
- It checks path membership, so its precision is only as good as your
  `expect_path_contains` substrings. Vague substrings (`.py`) will over-match; an
  empty substring would match *every* path, so the audit rejects empty/whitespace-only
  `expect_path_contains` as a malformed case rather than silently passing it.
