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
- **Adapter-based.** Codex, Claude Code, custom agents, systemd and containers should plug into a common model.
- **Explain drift, do not hide it behind a score.** Severity and confidence may supplement evidence, never replace it.
- **Stable snapshot schema first.** The data model is more important than a dashboard.

## Initial user

A developer or small platform team running AI coding/internal agents as long-lived Linux workers and needing to prove which configuration is actually effective.

## Longer-term product

The OSS CLI can become the collector/verifier for an optional commercial control plane offering fleet history, policy management, alerts, organization-wide attestations, RBAC, SSO and enterprise integrations.
