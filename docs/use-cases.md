# Use cases, extension points, and what to adopt

## AI assistant memory

Gate retrieval quality in RAG-backed chatbots or assistants. Detect when corpus updates or embedding
model swaps regress search. A deployed example of this exact use case:
[two-channel-fastapi.md](two-channel-fastapi.md) (auto-mined Hit@5 1.0 against hand-labeled 0.92).

Want the retrieval engine, an MCP server and agent-recall hooks, not just the eval gate? See
[shelfmark](https://github.com/LucasSantana-Dev/shelfmark): same hybrid-retrieval lineage, packaged
for agent memory instead of regression testing.

## Document and knowledge base search

Keep search quality stable as your docs grow. No user click data? Gate on retrievability. Wrappers
for LangChain and LlamaIndex: [hitgate/adapters/README.md](../hitgate/adapters/README.md). Track runs
in Langfuse: [langfuse-guide.md](langfuse-guide.md).

## Code search

Find code references and definitions. The hybrid retriever understands `camelCase`, which helps
codebases with identifier-heavy queries. The same gate works for private codebases.

## Extending

The core indexes code, docs and commits, nothing else. Tool-specific sources (assistant transcripts,
code graphs, other memory stores) plug in as optional adapters:
[hitgate/adapters/README.md](../hitgate/adapters/README.md).

## What to adopt, and what to skip

Adopt the harness (`hitgate/`): label-free regression gating and the `--retriever` interface. Plug
in your own retriever.

Skip, on purpose:

- A framework or hosted service. There is no plugin marketplace and no SaaS.
- State-of-the-art retrieval research. The retriever is pragmatic and knows its ceiling.
- A maintained product. This is a solo operator's tool, best effort, no SLA.

Deliberately omitted: badge walls and issue templates. [DECISIONS.md](../DECISIONS.md) records what
is left out on purpose and when it might reopen.

## Related documents

- [ROADMAP.md](../ROADMAP.md): candidate experiments, no commitments
- [DECISIONS.md](../DECISIONS.md): what is out of scope and why
- [CONTEXT.md](../CONTEXT.md): vocabulary and decision history
