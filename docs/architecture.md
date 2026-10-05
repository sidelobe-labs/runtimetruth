# Architecture

RuntimeTruth begins as a local CLI with a small adapter layer and a versioned snapshot schema.

## Proposed flow

```text
target
  |
  v
runtime adapter
  |
  +--> process/runtime evidence
  +--> code/repository evidence
  +--> agent configuration evidence
  +--> tool/MCP evidence
  +--> permission/environment evidence
  |
  v
normalized snapshot
  |
  +--> inspect
  +--> diff
  +--> verify
  +--> attest
```

## Core modules

### Snapshot schema

A versioned, serializable representation of runtime evidence. It should retain provenance for each field so a consumer can distinguish observed, resolved, declared, and unavailable data.

### Collectors

Small components that gather facts such as process identity, executable hashes, environment metadata, Git state, loaded configuration and permission probes.

### Runtime adapters

Adapters translate runtime-specific concepts into the common schema. Initial target: local Linux/systemd. Candidate later adapters include Docker, Kubernetes, Codex, Claude Code, Gemini CLI and custom agent workers.

### Diff engine

Produces semantic changes between snapshots. It should understand categories rather than merely diffing JSON.

### Policy verifier

Evaluates snapshots against explicit local policy. Policy design comes after the snapshot format is stable.

### Attestation

Produces a portable statement of observed runtime state. Signing and remote verification are later milestones and should not be designed prematurely.

## Security boundaries

RuntimeTruth may encounter sensitive environment variables, prompts, paths and tool configuration. The default collection model should prefer metadata and hashes. Plaintext capture must be deliberate and visible.

## Non-goals for the first milestone

- hosted dashboard
- LLM-generated diagnosis
- enterprise RBAC/SSO
- automatic remediation
- broad Kubernetes support
- generic application observability
