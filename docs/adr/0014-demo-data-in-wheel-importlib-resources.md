# ADR-0014: Demo data in wheel via importlib.resources

## Context
ADR-0007 decided to ship the harness code-only and keep golden/baseline data repo-only, citing "wheel-size/versioning friction." However, this created a critical bug (#2 in audit): `pip install hitgate[hybrid]` fails because `run.py` expects the data files to be present in the installed package directory, which they are not.

## Decision
Ship demo data in the wheel via `importlib.resources`, keep private baselines repo-only, fix output path to `Path.cwd()`, and add a PyPI-install smoke test to CI.

## Consequences
- Demo data (~84KB) is now included in the wheel.
- `run.py` uses `importlib.resources.files("hitgate")` to locate data.
- `hitgate-run` output is written to `Path.cwd()` by default.
- PyPI-install smoke test ensures this doesn't regress.
- ADR-0007's "data stays repo-only" clause is partially superseded.
