# Vision

## Problem

AI-agent deployments have runtime state that is easy to change without an obvious source-code change: model routing, prompts and project instructions, MCP servers and tool schemas, skills, permissions, sandbox policy, runtime versions, environment, and repository state.

Traditional configuration management tells us what should be deployed. RuntimeTruth focuses on what is actually effective in the live agent runtime.

## Product thesis

RuntimeTruth should make three states explicit:

1. **Declared** — what configuration and deployment manifests say should be used.
2. **Resolved** — what provider/router/config resolution produces.
3. **Live** — what the running process can be shown to be using.

Drift between these states should be observable, explainable, machine-readable, and suitable for CI or policy enforcement.

The product boundary is **agent runtime verification**, not generic runtime security or observability. Process, repository, MCP and configuration collectors are evidence sources; they are not the product by themselves.

## Core questions

- What agent runtime is live?
- Which runtime inputs can materially affect its behaviour?
- What changed since a known-good snapshot?
- Does the live runtime satisfy an approved policy?
- Can the runtime state be attested and independently inspected?

## Design principles

- **Evidence before inference.** Report observed facts separately from assumptions.
- **Deterministic core.** Runtime verification must not require an LLM.
- **Local-first.** Useful OSS functionality must work without a cloud account.
- **Secrets stay secrets.** Fingerprint sensitive values; do not collect plaintext unnecessarily.
- **Adapter-based, not adapter-driven.** Add an adapter only when it proves a useful runtime fact that the common model can represent.
- **Explain drift, do not hide it behind a score.** Severity and confidence may supplement evidence, never replace it.
- **Stable snapshot schema first.** The data model is more important than a dashboard.
- **Reuse established primitives.** Do not rebuild tracing, eBPF monitoring, MCP enforcement or software-supply-chain signing when existing tools already solve those problems.

## Scope boundary

RuntimeTruth is intended to correlate effective agent state across declared, resolved and live evidence.

It is not intended to become a general process monitor, agent tracing platform, MCP firewall, endpoint inventory system, GitOps controller or replacement for software provenance standards.

See [Landscape and positioning](landscape.md) for the adjacent tool categories and the current differentiation hypothesis.

## Initial user

A developer or small platform team running AI coding/internal agents as long-lived Linux workers and needing to prove which configuration is actually effective.

## Longer-term product

The OSS CLI can become the collector/verifier for an optional commercial control plane offering fleet history, policy management, alerts, organization-wide attestations, RBAC, SSO and enterprise integrations.

That layer should only follow evidence that teams need central history or policy management; it should not drive the local data model prematurely.
