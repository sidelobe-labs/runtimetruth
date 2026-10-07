# Changelog

All notable user-facing changes to RuntimeTruth are documented here.

RuntimeTruth is pre-release software. Snapshot and report schemas are versioned independently from the package version, and compatibility guarantees may evolve before a stable 1.0 release.

## [Unreleased]

## [0.2.1] - 2026-10-07

RuntimeTruth v0.2.1 is a release-hygiene patch with no runtime semantics changes.

### Fixed

- README documentation and license links now use portable absolute repository URLs so the package description remains navigable when rendered on PyPI or other external surfaces

### Changed

- package CI and the release workflow now run `twine check --strict` against built distributions before smoke testing or publication
- release metadata tests keep the package version, CLI version, README public-alpha version, release link, changelog entry and release-notes file in sync
- README Markdown targets are regression-tested to prevent repository-relative links from leaking into package-index rendering again


## [0.2.0] - 2026-10-06

RuntimeTruth v0.2.0 adds an explicit trust chain for reviewed baselines, persisted runtime policy selectors, and the first normal PyPI distribution path.

### Added

- RFC 8785 canonical baseline serialization and SHA-256 digest output via `runtimetruth digest`
- identity-backed baseline attestations using canonical in-toto Statement v1 and Sigstore Cosign
- `runtimetruth attest` for canonical statement + keyless Sigstore bundle generation
- `runtimetruth verify-attestation` for exact signer identity, baseline digest and runtime verification
- machine-readable identity/baseline/runtime verification reports via `--json`
- explicit schema-v1 TOML verification policies for persisted runtime selectors
- policy support for both plain and signed-baseline runtime verification
- PyPI release automation through GitHub OIDC Trusted Publishing

### Security

- signed-attestation verification fails closed before current-runtime collection when signer identity or baseline binding cannot be verified
- snapshot and attestation JSON parsing rejects duplicate object keys
- RuntimeTruth validates the exact canonical in-toto statement after Cosign verifies its signature and signer identity
- runtime policy selection is evaluated only after signed-baseline trust verification succeeds
- the PyPI release job uses short-lived OIDC credentials instead of a long-lived package token

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
- PASS is not a security or compliance certification
- RuntimeTruth does not classify MCP contract compatibility; MCP server contract testing is intentionally outside the product boundary
