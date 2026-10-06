# RuntimeTruth

**Verify what your AI agent is actually running.**

_An open-source Sidelobe project._

[Project case study](https://sidelobe.dev/open-source/runtimetruth/) · [Engineering case study](https://artur.panek.tech/work/runtimetruth/) · [Engineering note](https://artur.panek.tech/notes/ai-agent-config-vs-runtime/) · [v0.1.0 release](https://github.com/sidelobe-labs/runtimetruth/releases/tag/v0.1.0)

RuntimeTruth is an open-source runtime verification and drift-detection tool for AI agents. It compares evidence from declared, resolved, and live runtime state so teams can identify changes in effective models, instructions, tools, MCP servers, permissions, runtime versions, and execution environment.

> Status: [v0.1.0](https://github.com/sidelobe-labs/runtimetruth/releases/tag/v0.1.0) public pre-release. The local CLI, schema-v1 snapshots, Codex runtime inspection, semantic diff, selective baseline verification and machine-readable verification reports have been validated against real local runtimes.

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

Broader policy evaluation and organizational provenance remain later phases. The current policy file is intentionally narrower: it persists only the evidence selectors that should gate verification.

## Project model

RuntimeTruth is currently distributed as free, local-first open-source software. There is no RuntimeTruth hosted control plane, account system, telemetry service, paid support plan or SLA.

A verification result is deliberately narrow: **PASS means the selected evidence matched the selected baseline.** It does not mean the agent is secure, compliant, safe, or correctly configured in ways RuntimeTruth did not inspect.

See the [trust model](docs/trust-model.md), [data handling](docs/data-handling.md), [support policy](SUPPORT.md), and [MIT License](LICENSE) for the current project boundary.

## Origin

RuntimeTruth grew out of operating self-hosted workers and noticing that source code and deployment configuration were not enough to answer a simple question: **what is actually running right now?**

The project is built from evidence outward. It started with systemd, procfs, and Git identity, then used the same model to inspect agent-specific Codex state.

[Read the origin story](docs/origin.md).

## Installation

RuntimeTruth is not yet published to PyPI. For the v0.1.0 pre-release repository:

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

Bind a reviewed baseline to an identity-backed Sigstore attestation:

```bash
runtimetruth digest baseline.json

runtimetruth attest baseline.json \
  --statement baseline.intoto.json \
  --bundle baseline.sigstore.json

runtimetruth verify-attestation \
  baseline.json \
  --statement baseline.intoto.json \
  --bundle baseline.sigstore.json \
  --certificate-identity "EXPECTED_IDENTITY" \
  --certificate-oidc-issuer "EXPECTED_ISSUER" \
  --codex . \
  --resolve-thread
```

Attestation uses RFC 8785 canonical JSON, SHA-256, in-toto Statement v1 and Sigstore Cosign rather than a RuntimeTruth-specific signature scheme. See [signed baseline attestations](docs/attestation.md).

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

Selective runtime invariants can be protected explicitly, or persisted in a small schema-v1 TOML policy:

```console
runtimetruth verify baseline.json --codex <cwd> --resolve-thread \
  --protect codex.thread.model \
  --protect codex.instructions

runtimetruth verify baseline.json --codex <cwd> --resolve-thread \
  --policy .runtimetruth/policy.toml
```

For automation, add `--json` to emit a versioned structured PASS/DRIFT report without changing the exit-code contract.

Canonical baseline identity and signed verification are separate commands:

```console
runtimetruth digest <baseline.json>

runtimetruth attest <baseline.json> \
  --statement <baseline.intoto.json> \
  --bundle <baseline.sigstore.json>

runtimetruth verify-attestation <baseline.json> [current.json] \
  --statement <baseline.intoto.json> \
  --bundle <baseline.sigstore.json> \
  --certificate-identity <expected-identity> \
  --certificate-oidc-issuer <expected-issuer>
```

`verify-attestation` can also use `--codex <cwd>`, `--resolve-thread`, `--resolve-mcp`, repeatable `--protect`, and `--json`.

Creating or verifying identity-backed attestations requires a recent [Sigstore Cosign](https://docs.sigstore.dev/cosign/system_config/installation/) executable. Normal inspect/diff/verify commands do not require Cosign.

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

The current focus is to make baseline verification useful and trustworthy before expanding into broader policy semantics, additional agent adapters, organizational provenance, or cloud features.

See:

- [Origin](docs/origin.md)
- [Vision](docs/vision.md)
- [Landscape and positioning](docs/landscape.md)
- [Roadmap](docs/roadmap.md)
- [Architecture](docs/architecture.md)
- [CI integration](docs/ci.md)
- [Signed baseline attestations](docs/attestation.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Trust model](docs/trust-model.md)
- [Data handling](docs/data-handling.md)
- [Support](SUPPORT.md)

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
