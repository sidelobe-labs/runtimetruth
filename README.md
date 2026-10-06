# RuntimeTruth

**Verify what your AI agent is actually running.**

RuntimeTruth is an open-source runtime verification and drift-detection tool for AI agents. It compares evidence from declared, resolved, and live runtime state so teams can identify changes in effective models, instructions, tools, MCP servers, permissions, runtime versions, and execution environment.

> Status: pre-release. The local CLI, schema-v1 snapshots, Codex runtime inspection, semantic diff, selective baseline verification and machine-readable verification reports have been validated against real local runtimes.

## Why

AI agents have more mutable runtime state than ordinary applications:

- model and provider routing
- system and project instructions
- tools and MCP schemas
- skills and plugins
- sandbox and network permissions
- executable/runtime versions
- environment and process identity
- repository/code state

A deployment can therefore look unchanged while the effective agent runtime has drifted.

RuntimeTruth currently focuses on two questions:

1. **What runtime state can be established with explicit evidence?**
2. **What changed since a known baseline?**

Policy evaluation and portable attestation remain later phases.

## Origin

RuntimeTruth grew out of operating self-hosted workers and noticing that source code and deployment configuration were not enough to answer a simple question: **what is actually running right now?**

The project is built from evidence outward. It started with systemd, procfs, and Git identity, then used the same model to inspect agent-specific Codex state.

[Read the origin story](docs/origin.md).

## Installation

RuntimeTruth is not yet published to PyPI. For the pre-release repository:

```bash
git clone https://github.com/sidelobe-labs/runtimetruth.git
cd runtimetruth
python -m venv .venv
source .venv/bin/activate
python -m pip install .
runtimetruth --version
```

For CI, pin the source revision rather than following a moving branch. See [CI integration](docs/ci.md).

## Quick start

Capture effective Codex runtime state:

```bash
runtimetruth inspect codex . --resolve-thread --pretty > baseline.json
```

Verify the current runtime against that baseline:

```bash
runtimetruth verify baseline.json --codex . --resolve-thread
```

Protect only selected runtime invariants when strict snapshot equality is too broad:

```bash
runtimetruth verify baseline.json --codex . --resolve-thread \
  --protect codex.thread.model \
  --protect codex.instructions
```

Add `--json` for a versioned machine-readable PASS/DRIFT report.

## Current CLI

Inspect a local target:

```console
runtimetruth inspect systemd <unit>
runtimetruth inspect git <path>
runtimetruth inspect codex <cwd>
runtimetruth inspect codex <cwd> --resolve-thread
runtimetruth inspect codex <cwd> --resolve-mcp
```

Compare two snapshots:

```console
runtimetruth diff <before.json> <after.json>
```

Verify a current snapshot against a baseline:

```console
runtimetruth verify <baseline.json> <current.json>
```

Or collect the current Codex runtime and verify it directly:

```console
runtimetruth verify <baseline.json> --codex <cwd> --resolve-thread
runtimetruth verify <baseline.json> --codex <cwd> --resolve-mcp
```

Verification uses stable process exit codes:

- `0` — runtime matches the baseline
- `2` — semantic runtime drift detected
- `1` — collection, input, or comparison error

Selective runtime invariants can be protected explicitly:

```console
runtimetruth verify baseline.json --codex <cwd> --resolve-thread \
  --protect codex.thread.model \
  --protect codex.instructions
```

For automation, add `--json` to emit a versioned structured PASS/DRIFT report without changing the exit-code contract.

`--resolve-thread` creates an ephemeral Codex thread without starting a turn. `--resolve-mcp` additionally probes thread-scoped MCP runtime state and may contact configured MCP servers or refresh authentication; it does not call MCP tools.

## Evidence currently collected

The intentionally narrow implementation includes:

- systemd unit/runtime state
- procfs process identity
- Git repository identity
- Codex executable/version
- Codex canonical resolved workspace configuration
- effective state materialized for an ephemeral Codex thread
- Codex-reported instruction source paths
- SHA-256 fingerprints of those instruction source files without storing their plaintext
- thread-scoped MCP server status and bounded tool-catalog fingerprints

Each evidence record keeps its provenance and is classified as declared, resolved, or live where the source supports that claim.

## Project boundary

RuntimeTruth is not intended to become a generic process monitor, LLM trace backend, MCP proxy/firewall, GitOps controller, or hosted observability dashboard.

The current focus is to make baseline verification useful and trustworthy before adding policy syntax, attestation, additional agent adapters, or cloud features.

See:

- [Origin](docs/origin.md)
- [Vision](docs/vision.md)
- [Landscape and positioning](docs/landscape.md)
- [Roadmap](docs/roadmap.md)
- [Architecture](docs/architecture.md)
- [CI integration](docs/ci.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

## License

MIT.
