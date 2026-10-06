# Landscape and positioning

RuntimeTruth sits next to several established categories rather than replacing any one of them.

The project stays narrow: **verify the effective runtime state of an AI agent and preserve evidence of how that state was established.**

## Adjacent tools

| Category | Examples | What they already do well | RuntimeTruth boundary |
| --- | --- | --- | --- |
| Runtime / process observability | [Tetragon](https://tetragon.io/docs/use-cases/process-lifecycle/) | Observe process execution, lifecycle and low-level runtime metadata; support runtime enforcement | RuntimeTruth consumes a small amount of process evidence, not general eBPF security telemetry |
| GitOps desired-vs-live reconciliation | [Argo CD](https://argo-cd.readthedocs.io/en/latest/user-guide/diff-strategies/) | Compare desired and live Kubernetes state and identify out-of-sync resources | RuntimeTruth applies a related idea to agent runtime state, including a distinct resolved layer between declaration and live observation |
| Agent tracing and evaluation | [Phoenix](https://arize.com/docs/phoenix/tracing) | Trace LLM calls, retrievals, tool executions and agent runs; evaluate behaviour | RuntimeTruth is about runtime identity and effective configuration, not request-level execution traces or output quality |
| Endpoint AI / MCP inventory | [GitGuardian](https://docs.gitguardian.com/endpoint-protection/agent-and-mcp-inventory) | Discover installed AI agents, configured MCP servers and accessible tools/data on endpoints | RuntimeTruth binds agent-specific configuration evidence to a particular inspected runtime rather than becoming a fleet inventory product |
| MCP contract testing | [mcpward](https://github.com/TsvetanG2/mcpward) | Black-box contract testing for MCP servers: schema/description drift, protocol checks, security heuristics, behavioural tests, latency budgets and CI reporting | RuntimeTruth does not test whether an MCP server contract is safe or backwards-compatible. It records the MCP capability surface visible to a particular inspected agent as one component of that agent's effective runtime identity |
| MCP drift and enforcement | [MCPTrust](https://github.com/mcptrust/mcptrust) | Lock MCP capabilities, detect drift, pin artifacts and enforce policy through a runtime proxy | RuntimeTruth records MCP/tool state as evidence but does not proxy, firewall or enforce MCP traffic |
| Build provenance and attestations | [SLSA](https://slsa.dev/spec/v1.2/provenance), [Sigstore](https://docs.sigstore.dev/cosign/verifying/attestation/) | Describe artifact provenance and provide signing / attestation primitives | RuntimeTruth should reuse established attestation primitives where possible rather than invent a new signing ecosystem |

This landscape will change. The purpose of this document is to keep project boundaries explicit, not to claim that RuntimeTruth is the only tool operating in these areas.

## Differentiation hypothesis

The useful unit in RuntimeTruth is not a process, repository, trace, MCP server or deployment manifest by itself.

It is the relationship between three views of one agent runtime:

1. **Declared** — what configuration says should be used.
2. **Resolved** — what the agent/provider/router actually resolves that configuration into.
3. **Live** — what can be established from the running environment.

The project is useful when it can connect those layers with explicit provenance and then detect drift against a known baseline.

The validated Codex slice now supports evidence such as:

```text
Codex workspace
  |
  +-- installed runtime/version                  LIVE
  +-- canonical workspace config                RESOLVED
  +-- effective thread model/provider           RESOLVED
  +-- approval + sandbox/network state          RESOLVED
  +-- instruction source paths                  RESOLVED
  +-- instruction source fingerprints           LIVE
  +-- MCP runtime status + catalog fingerprint  LIVE
  |
  v
evidence-backed snapshot
  |
  +-- semantic diff
  +-- baseline verification
```

One real validation showed why the resolved layer matters: workspace-level Codex configuration left model/provider fields unset while an ephemeral thread materialized the effective model/provider and other runtime settings.

## What RuntimeTruth is not

RuntimeTruth should not become:

- a generic Linux process monitor
- an eBPF runtime-security platform
- an LLM tracing or evaluation backend
- an endpoint AI inventory product
- an MCP proxy or firewall
- a GitOps deployment controller
- a replacement for SLSA, in-toto or Sigstore
- a dashboard-first observability product

Those are established problem spaces with mature tools.

## Current validation boundary

The Codex vertical slice has answered the original stop-condition question positively: RuntimeTruth can expose effective state that otherwise requires correlating multiple configuration, filesystem and runtime sources.

That does **not** automatically justify broad adapter expansion.

The next product question is verification: which runtime changes should fail a gate, which changes should be allowed, and what minimal policy/invariant representation is needed to express that without obscuring the underlying evidence.

Until a concrete workflow requires it, the project should avoid adding:

- additional agent adapters solely for coverage
- generic container/Kubernetes collectors
- policy engines with speculative abstractions
- hosted dashboards or fleet management
- custom signing infrastructure

The evidence model should continue to be tested through small, real operational workflows.

## MCPWard boundary

MCPWard and RuntimeTruth can reasonably appear in the same CI pipeline because they verify different objects.

MCPWard asks whether an MCP server's contract changed or violates its configured checks. RuntimeTruth asks whether the inspected agent's effective runtime identity still matches the baseline selected for that agent.

For example, an `AGENTS.md` instruction change or a different effective model can be RuntimeTruth drift while the MCP server contract remains completely unchanged. Conversely, MCPWard can classify a breaking input-schema or tool-description change in detail; RuntimeTruth deliberately does not duplicate that contract-testing logic.

RuntimeTruth's `codex.mcp` evidence should therefore remain an agent-runtime identity signal, not grow into a second MCP contract-testing product.
