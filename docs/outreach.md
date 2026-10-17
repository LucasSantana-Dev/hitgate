# Outreach drafts

Status: drafts only. Nothing here has been posted, and no PR has been opened in a third-party
repository. Review each target's contribution rules again on the day you submit, because they change.

## 1. Awesome-RAG list entry

Target: [Danielskry/Awesome-RAG](https://github.com/Danielskry/Awesome-RAG), the most-starred
"awesome RAG" list at the time of writing (about 1.4k stars). Its README has a
"Metrics & Evaluation" section with a "Tools" sub-list, and a Contributing section that asks for
a fork and a branch. Entries there follow this shape: `- **[Name](url)**: one-line description.`

Line ready for the PR, placed in "Metrics & Evaluation > Tools":

```markdown
- **[hitgate](https://github.com/LucasSantana-Dev/hitgate)**: Label-free retrieval regression gate for RAG. Measures Hit@K and MRR on your own corpus with no golden labels or LLM judge, and fails CI when ranking regresses. Includes a BM25 + dense + RRF reference retriever.
```

PR title: `Add hitgate to Metrics & Evaluation tools`

PR body:

```markdown
Adds hitgate, an open-source (MIT) harness that gates retrieval ranking quality in CI.

- Fits "Metrics & Evaluation > Tools": it evaluates the retrieval step, complementing the
  answer-level tools already listed (Ragas, LangSmith).
- Label-free: golden cases are mined from the corpus, so there is no annotation cost.
- Published on PyPI (`pip install hitgate`), with the methodology and its limits documented.
```

Checks before submitting:

- Confirm the section name and the entry format against the current README.
- Check that hitgate is not already listed, and that the list still accepts tools in this section.
- Keep the description to one line. Do not claim absolute quality numbers: the self-indexed
  results are optimistic by design, and the README says so.

Fallback targets if the first declines or is inactive: `awesome-rag/awesome-rag` (about 460 stars,
papers and systems) and `Yigtwxx/awesome-rag-production` (about 280 stars, production tooling).
Check each list's scope before adapting the line.

## 2. Docs PR outline: hitgate as an evaluation gate

Goal: a short how-to page showing how to gate a LangChain or LlamaIndex retriever in CI with
hitgate, using the adapters that already exist in this repo
(`hitgate/adapters/langchain_retriever.py`, `hitgate/adapters/llamaindex_retriever.py`).

### Choosing the target

| | LangChain | LlamaIndex |
|---|---|---|
| Docs repo | `langchain-ai/docs` (Mintlify, pages under `src/oss/python/integrations/`) | `run-llama/llama_index` (docs under `docs/src/content/`) |
| Contribution rules seen | `AGENTS.md`: never fabricate examples, test code examples, update `src/docs.json` for new pages | `CONTRIBUTING.md`: new integration packages are no longer accepted in the main repo, they must live in their own repo |
| Fit | A how-to page under integrations or evaluation | Docs fixes and examples are welcome, but an integration package is not |
| Recommendation | Primary target | Secondary, as an example or community link only |

Open an issue or discussion first and ask whether a third-party evaluation page is wanted. Do not
send an unsolicited page to a maintainer's repo.

### Outline

Title: `Gate your retriever in CI with hitgate`

1. **Problem.** You changed a splitter, an embedding model or a reranker. Did retrieval get better
   or worse? You have no labels and no traffic to A/B.
2. **What hitgate measures.** Hit@K and MRR on golden cases mined from your own corpus, compared
   with a frozen baseline. One paragraph, plus the honest limit: it detects regressions, it does not
   certify absolute quality.
3. **Install.** `pip install hitgate` (no core dependencies), plus your retriever's own packages.
4. **Wrap your retriever.** Show `to_harness(retriever, path_key="source")` from the adapter, and
   the callable contract `(query, top, scope) -> [{"path": ...}]`. This code must be copied from the
   adapter's tested example, not retyped.
5. **Create and freeze.** `hitgate-init`, review the cases, `hitgate-run --retriever ...`, commit the
   baseline.
6. **Gate it.** `hitgate-compare ci.json baseline.json`, and a GitHub Actions snippet based on
   `examples/retrieval-gate.yml`.
7. **Read a failure.** The terminal capture in `docs/demo.gif`, then `hitgate-diff` to see which
   cases moved.
8. **Limits.** Where it sits next to answer-level tools. Link `docs/COMPARISONS.md` and
   `docs/METHODOLOGY.md`.

### Before opening anything

- Run every snippet against the current LangChain or LlamaIndex release and record the versions.
- Do not include benchmark numbers from private corpora. Use the public numbers in
  `docs/benchmarks.md` and re-run them on the day.
- Keep the page free of marketing language. State what the tool does not do.
- Disclose that the author maintains hitgate.

## 3. Sequence

1. Merge this docs PR so the README, demo and benchmarks are the reference the links point to.
2. Submit the Awesome-RAG PR (low effort, low risk).
3. Open a discussion in the LangChain docs repo. Wait for a reply before writing the page.
4. Only then draft the page, using the outline above.
