# How hitgate compares

**Short version:** hitgate gates **retrieval *ranking*, label-free**. Most tools it gets
compared to evaluate the generated **answer** — and need an LLM judge, labeled data, or
both. Different layer of the RAG stack; usually **complementary**, not competing.

> Treat this as a map of *layers*, not a scoreboard. The other tools are mature and
> well-funded; the point here is *which job each does*, so you pick the right one (often
> more than one). Capabilities evolve — check each tool's current docs before deciding.

## The one-line rule

- Evaluating whether the **LLM's answer** is good (faithful, relevant, grounded)?
  → an **answer-eval** tool (RAGAS, DeepEval, TruLens, promptfoo, Braintrust…).
- Evaluating whether your **retriever** surfaces the right chunks — **with no labels**,
  gated in CI like a test? → **hitgate**.
- Doing both? Run an answer-eval tool *and* hitgate. They sit at different layers.

## At a glance

| Tool | Evaluates | Typically needs | Reach for it when |
|---|---|---|---|
| **hitgate** | Retrieval **ranking** (Hit@K / MRR) | **nothing** — goldens are mined from your corpus | You changed the retriever/index/chunking and want a CI gate that says *helped or hurt*, with no labels and no users to A/B against |
| **RAGAS** | RAG **answers** + context precision/recall | LLM judge; context metrics need ground-truth contexts | You want faithfulness / answer-relevancy scoring on generated answers |
| **DeepEval** | LLM outputs (pytest-style) | LLM-as-judge metrics, often criteria/labels | You want unit-test-shaped assertions over LLM answer quality |
| **TruLens** | Outputs via feedback functions | Feedback functions, often LLM-judged | You want app-level eval + observability/tracing |
| **promptfoo** | Prompt/model outputs | Assertions, frequently LLM-graded | You're comparing prompts/models on output assertions |
| **Braintrust** | Eval + observability platform | Labeled/golden sets or an LLM judge; ships CI actions | You want a hosted eval+logging platform across the stack |
| **EvalView** | Agent **tool-call trajectories** (snapshot/diff) | nothing for its deterministic tier | You're gating an *agent's* behavior (tools, sequence, cost), not retrieval |

## Why "label-free" is the actual wedge

"Retriever-agnostic" is table stakes and "label-free" is claimed loosely across the space.
The specific gap hitgate fills: **corpus-aware retrieval-*ranking* regression-gating on your
own corpus, without ground-truth labels.** RAGAS `context_precision`/`recall` and similar
retrieval metrics need labeled relevant contexts; BEIR/MTEB need labeled qrels and are fixed
academic corpora, not "run it on *your* repo." hitgate mines its golden query→chunk pairs from
distinctive terms already in your corpus, so it needs no annotation budget and no traffic.

## What hitgate deliberately does NOT do

- **It does not judge answer quality.** No faithfulness, no relevancy, no groundedness. If you
  need that, use an answer-eval tool above — hitgate measures the layer *underneath* the answer.
- **It does not claim human-judged relevance.** Because the goldens are label-free,
  `label-free goldens measure retrievability/regression, not human-judged relevance` — treat the
  numbers as a self-consistency / **regression** signal, gate on **deltas**, not absolutes.
  (Same caveat the CLI and the result JSON now print; see
  [docs/METHODOLOGY.md](METHODOLOGY.md) and [DECISIONS.md](../DECISIONS.md).)
- **It is not a hosted platform.** No dashboard, no SaaS, no telemetry — a CLI + a CI gate.

## hitgate ⟂ EvalView (a comp, not a competitor)

[EvalView](https://github.com/hidai25/eval-view) is "pytest for agents": it snapshots an
agent's **tool-call trajectory** and gates CI on drift. hitgate gates **retrieval ranking**.
They live at different layers — an agent stack could run *both* (hitgate on the retrieval step,
EvalView on the agent's tool use). We borrow craft from it (a CI gate that's deterministic and
free), not its scope.
