# Contributing to RuntimeTruth

RuntimeTruth is intentionally validation-driven. Changes should strengthen a concrete runtime-verification workflow rather than broaden the project surface speculatively.

## Before opening a pull request

For non-trivial changes, open or reference an issue that states:

- the runtime-verification problem being solved
- the evidence source involved
- what RuntimeTruth can establish directly versus what would be inferred
- the security/privacy boundary
- how the behavior can be validated against a real or faithful fixture runtime

Small documentation and maintenance fixes do not need a design issue.

## Development setup

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

ruff check .
ruff format --check .
pytest
python -m build
```

## Change guidelines

Prefer small, reviewable slices.

- keep evidence provenance explicit
- do not silently infer unavailable runtime state
- use allowlists when collecting data near secrets or prompts
- do not add runtime dependencies without a concrete need
- preserve deterministic snapshot/report output
- add fixture-backed tests for new evidence or comparison behavior
- validate agent-specific behavior against the real runtime when practical
- reuse existing diff/verification paths rather than creating parallel semantics

For Codex probes, avoid starting model turns unless a feature explicitly requires and documents that behavior. MCP inspection must not call tools unless a future feature makes that side effect explicit.

## Pull requests

A pull request should explain:

- what changed
- the evidence/trust boundary
- deliberate non-goals
- automated test coverage
- any real-runtime validation performed

The project normally uses squash merges so one feature lands on `main` as one coherent commit.

## Security

Do not open a public issue containing vulnerability details or secrets. Follow [SECURITY.md](SECURITY.md).
