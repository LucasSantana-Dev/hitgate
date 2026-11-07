# hitgate-context (Rust)

A single static binary of the hitgate context gate (`hitgate/context.py`): a label-free
retrieval regression gate for agent context such as `~/.claude/skills` and memory notes.
It mines a golden set from skill triggers and note descriptions, ranks with an in-memory
BM25, and gates the run against a frozen baseline. No Python at runtime, so it fits a git
pre-commit hook.

The Python implementation stays the reference. This crate matches it output for output:
same frontmatter subset, same tokenizer and stop words, same BM25 constants and tie-break,
same root-anchored paths, same JSON shapes (`context.<label>.json`,
`context.<label>.verdict.json`), same exit codes. A baseline written by one gates a run of
the other; `tests/test_context_rs.py` at the repository root checks that both ways.

Caveat (ADR-0012): a hit proves the phrase still reaches its own document under a lexical
proxy retriever, not that the document is good.

## Build

```bash
cd rust/hitgate-context
cargo build --release
./target/release/hitgate-context ~/.claude
```

Static Linux binary (no libc dependency, runs on any x86_64 Linux):

```bash
rustup target add x86_64-unknown-linux-musl
cargo build --release --target x86_64-unknown-linux-musl
ls -la target/x86_64-unknown-linux-musl/release/hitgate-context
```

Windows and macOS release builds are already self-contained (only system libraries).

## Usage

```
hitgate-context ROOT [--label LABEL] [--baseline FILE] [--tol PP] [--top N] [--out DIR] [--show N]
```

Freeze a baseline, then gate later runs against it:

```bash
hitgate-context ~/.claude --label baseline --out ~/.claude
hitgate-context ~/.claude --baseline ~/.claude/context.baseline.json
```

Exit codes: 0 pass or improvement, 1 regression (including newly unreachable cases),
2 bad root, no cases, unusable baseline or bad arguments.

## Pre-commit hook

`hooks/pre-commit` runs the binary against a frozen baseline and blocks the commit on exit 1.
A missing binary or baseline, or any exit 2, warns and lets the commit through so a
misconfigured gate never locks the repository.

```bash
cp rust/hitgate-context/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Environment knobs: `HITGATE_CONTEXT_BIN`, `HITGATE_CONTEXT_ROOT` (default `./.claude` if
present, else `~/.claude`), `HITGATE_CONTEXT_BASELINE` (default `$ROOT/context.baseline.json`),
`HITGATE_CONTEXT_TOL` (default 5).

## Tests

```bash
cargo test                                   # unit and integration tests (ports of tests/test_context.py)
pip install -e ../.. pytest
python -m pytest ../../tests/test_context_rs.py -q   # Python vs Rust cross-check, skipped when the binary is absent
```

## Deviations from the Python command

- `--retriever` (loading a Python retriever module) is not supported; the binary prints an
  error and exits 2. The stdlib BM25 is always used.
- Two stdout footer lines are reworded without the em-dash used by `hitgate/compare.py`
  (`Regressed: ...` and the re-freeze hint). JSON output is unaffected.
- JSON files are written as UTF-8 without `\uXXXX` escapes for non-ASCII characters, where
  Python's `json.dumps` escapes them. The parsed documents are identical.
