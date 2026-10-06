# RuntimeTruth v0.1.0

RuntimeTruth v0.1.0 is the first public pre-release milestone for the Sidelobe open-source runtime verification project.

## What it does

RuntimeTruth captures evidence about an AI agent runtime, compares that evidence semantically, and verifies selected runtime invariants against a caller-controlled baseline.

The first agent-aware vertical slice targets Codex and can establish evidence about:

- installed Codex runtime/version
- canonical resolved workspace configuration
- effective model/provider state materialized for a new ephemeral thread
- approval and sandbox/network settings
- instruction-source paths and file fingerprints
- thread-scoped MCP runtime status and tool-catalog fingerprints

## Typical workflow

Capture a baseline:

```bash
runtimetruth inspect codex . --resolve-thread --pretty > baseline.json
```

Verify the live runtime:

```bash
runtimetruth verify baseline.json --codex . --resolve-thread
```

Protect only high-value runtime invariants:

```bash
runtimetruth verify baseline.json --codex . --resolve-thread \
  --protect codex.thread.model \
  --protect codex.thread.approval_policy \
  --protect codex.thread.sandbox \
  --protect codex.instructions
```

Emit a machine-readable report:

```bash
runtimetruth verify baseline.json --codex . --resolve-thread --json
```

Exit codes are stable for CI:

- `0` — PASS
- `2` — DRIFT
- `1` — ERROR

## Why this exists

Agent runtime identity is more than source code. Effective model routing, project instructions, sandbox policy and MCP capability surface can change independently.

RuntimeTruth separates:

- **declared** state
- **resolved** state
- **live** evidence

and keeps provenance explicit instead of silently inferring unavailable facts.

## Important boundaries

v0.1.0 is pre-release software.

A PASS means the selected evidence matched the selected baseline. It does not certify that an agent is secure, compliant or safe.

RuntimeTruth is currently local-first OSS:

- no account
- no RuntimeTruth telemetry
- no hosted control plane
- no paid support plan
- no SLA

See [Trust model](https://github.com/sidelobe-labs/runtimetruth/blob/v0.1.0/docs/trust-model.md), [Data handling](https://github.com/sidelobe-labs/runtimetruth/blob/v0.1.0/docs/data-handling.md), [Security](https://github.com/sidelobe-labs/runtimetruth/blob/v0.1.0/SECURITY.md) and [Support](https://github.com/sidelobe-labs/runtimetruth/blob/v0.1.0/SUPPORT.md) before using RuntimeTruth as a CI gate.
