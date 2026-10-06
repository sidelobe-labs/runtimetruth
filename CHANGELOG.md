# Changelog

All notable user-facing changes to RuntimeTruth are documented here.

RuntimeTruth is pre-release software. Snapshot and report schemas are versioned independently from the package version, and compatibility guarantees may evolve before a stable 1.0 release.

## [0.1.0] - 2026-10-06

First public pre-release.

### Added

- versioned schema-v1 runtime snapshots with explicit evidence provenance
- local systemd unit/runtime inspection
- procfs process identity inspection
- Git repository identity inspection
- composed systemd -> process -> repository evidence
- semantic snapshot diff with missing-vs-null preservation
- Codex runtime/version inspection
- Codex canonical resolved workspace configuration through app-server
- optional ephemeral-thread resolution for effective model/provider, approval and sandbox state
- Codex-reported instruction source inventory
- SHA-256 fingerprints of instruction source files without storing plaintext
- opt-in thread-scoped Codex MCP runtime inventory without MCP tool execution
- bounded MCP tool-name snapshots plus deterministic full-catalog fingerprints
- strict baseline verification with stable PASS / DRIFT / ERROR exit codes
- live Codex verification against a baseline without an intermediate current-snapshot file
- repeatable `--protect` selectors for agent-runtime invariants
- versioned machine-readable verification reports via `--json`
- CI integration guidance for pinned source installs and self-hosted runtime verification
- trust model, data-handling, support and security documentation

### Security and privacy

- allowlist-based collection near sensitive runtime data
- no RuntimeTruth telemetry or hosted control plane
- no instruction plaintext, environment values, auth tokens, MCP resource contents or tool schemas serialized by current collectors
- explicit side-effect boundary for MCP runtime status probing

### Known boundaries

- Codex thread resolution observes a newly-created ephemeral thread, not an existing user's active thread
- baseline files are caller-selected and are not signed or tamper-evident
- PASS is not a security or compliance certification
- RuntimeTruth does not classify MCP contract compatibility; MCP server contract testing is intentionally outside the product boundary
- no PyPI package or hosted service is included in this milestone
