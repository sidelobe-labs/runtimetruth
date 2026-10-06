# Architecture

RuntimeTruth is a local CLI built around small collectors, explicit evidence provenance and a versioned snapshot schema.

## Current flow

```text
target
  |
  v
collector / runtime adapter
  |
  +--> process/runtime evidence
  +--> code/repository evidence
  +--> agent configuration evidence
  +--> instruction-source evidence
  +--> tool/MCP evidence
  +--> permission/sandbox evidence
  |
  v
normalized schema-v1 snapshot
  |
  +--> inspect
  +--> semantic diff
  +--> baseline verify
  |
  v
PASS / DRIFT / ERROR
```

Portable attestation and policy evaluation remain later layers.

## Core modules

### Snapshot schema

A versioned, serializable representation of runtime evidence. Each evidence record retains its collection source and evidence plane so consumers can distinguish declared, resolved and live facts.

Schema v1 deliberately keeps evidence data scalar. Structured values that must be preserved are currently serialized deterministically rather than silently expanding the schema.

### Collectors

Collectors gather narrow facts and avoid broad host inventory.

Current collectors cover:

- systemd unit/runtime state
- procfs process identity
- Git repository identity
- Codex runtime and app-server state
- live instruction-file fingerprints

Collection follows an allowlist model. Sensitive values such as environment secrets, auth tokens, instruction plaintext and MCP command configuration are not serialized.

### Runtime adapters

The first agent-aware adapter is Codex.

It uses Codex's own app-server interfaces for canonical config resolution and optional ephemeral-thread probes rather than reimplementing Codex configuration precedence. The adapter can establish:

- installed runtime identity/version
- resolved workspace configuration
- effective thread model/provider, approval and sandbox state
- instruction source paths
- thread-scoped MCP runtime/tool state

Thread resolution is opt-in. MCP resolution is separately explicit because it may contact configured MCP servers or refresh authentication.

Additional agent adapters are intentionally deferred until they answer a concrete validation or user need.

### Diff engine

The schema-v1 diff engine compares supported evidence semantically rather than performing a raw JSON diff. Capture timestamps are ignored, missing values remain distinct from null values, and provenance changes are rejected rather than silently compared.

Supported sections currently include service, process, code, Codex runtime/config/thread, instruction fingerprints and Codex MCP state.

### Verification

Verification reuses the same semantic diff engine.

```text
baseline snapshot
       |
       +------ compare ------ current snapshot

baseline snapshot
       |
       +------ compare ------ freshly collected Codex runtime
```

The initial contract is deliberately simple:

- exit `0`: PASS
- exit `2`: DRIFT
- exit `1`: ERROR

Normal baseline verification still accepts a caller-selected snapshot directly.

For stronger provenance, the signed-attestation path canonicalizes the complete baseline with RFC 8785, hashes it with SHA-256, binds that digest into a canonical in-toto Statement v1, and uses Sigstore Cosign to sign those exact statement bytes.

Verification checks exact signer identity + OIDC issuer and the signed subject digest before the existing semantic runtime comparison runs. This proves baseline integrity relative to the expected signing identity; it does not establish organizational approval or baseline safety.

### Policy

A policy/invariant layer is future work. It should be added only after concrete verification workflows show which kinds of drift need to be tolerated or forbidden.

### Attestation

The first attestation vertical slice uses:

- RFC 8785 JSON Canonicalization Scheme
- SHA-256 baseline digest
- canonical in-toto Statement v1
- Sigstore Cosign keyless `sign-blob`
- explicit statement + verification bundle artifacts
- exact OIDC signer identity verification

RuntimeTruth creates no private-key format and implements no custom signature algorithm.

The signed statement authenticates a canonical baseline digest, while the Sigstore bundle carries signature/certificate/transparency verification material. Runtime verification still reuses the normal schema-v1 semantic diff engine after identity and digest checks succeed.

Future attestation work may add portable provenance or approval semantics, but should continue to reuse established signing/attestation standards rather than expanding the cryptographic surface area.

## Security boundaries

RuntimeTruth may encounter sensitive environment variables, prompts, paths and tool configuration.

The current collection model prefers metadata, status and hashes:

- instruction source paths may be recorded; instruction plaintext is not
- MCP tool names may be retained for small catalogs; full tool definitions are fingerprinted but not serialized
- large MCP catalogs retain counts/status/fingerprints rather than dumping every tool name
- raw MCP configuration, environment values, tokens, resource contents and tool schemas are not serialized

Evidence labels are intentionally conservative. For example, a fingerprint proves only the bytes RuntimeTruth observed at a Codex-reported path at snapshot time; it does not prove the exact prompt bytes consumed by a model.

## Non-goals

- hosted dashboard
- LLM-generated diagnosis
- enterprise RBAC/SSO
- automatic remediation
- broad Kubernetes support
- generic application observability
- MCP proxy/firewall or tool enforcement
