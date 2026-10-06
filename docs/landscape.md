# Landscape and positioning

RuntimeTruth sits next to several established categories rather than replacing any one of them.

The project should stay narrow: **verify the effective runtime state of an AI agent and preserve evidence of how that state was established.**

## Adjacent tools

| Category | Examples | What they already do well | RuntimeTruth boundary |
| --- | --- | --- | --- |
| Runtime / process observability | [Tetragon](https://tetragon.io/docs/use-cases/process-lifecycle/) | Observe process execution, lifecycle and low-level runtime metadata; support runtime enforcement | RuntimeTruth should consume a small amount of process evidence, not become a general eBPF security monitor |
| GitOps desired-vs-live reconciliation | [Argo CD](https://argo-cd.readthedocs.io/en/latest/user-guide/diff-strategies/) | Compare desired and live Kubernetes state and identify out-of-sync resources | RuntimeTruth applies a related idea to agent runtime state, including a distinct resolved layer between declaration and live observation |
| Agent tracing and evaluation | [Phoenix](https://arize.com/docs/phoenix/tracing) | Trace LLM calls, retrievals, tool executions and agent runs; evaluate behaviour | RuntimeTruth is about runtime identity and effective configuration, not request-level execution traces or output quality |
| Endpoint AI / MCP inventory | [GitGuardian](https://docs.gitguardian.com/endpoint-protection/agent-and-mcp-inventory) | Discover installed AI agents, configured MCP servers and accessible tools/data on endpoints | RuntimeTruth should bind agent-specific configuration evidence to an observed live runtime rather than become a fleet inventory product |
| MCP drift and enforcement | [MCPTrust](https://github.com/mcptrust/mcptrust) | Lock MCP capabilities, detect drift, pin artifacts and enforce policy through a runtime proxy | RuntimeTruth may record MCP/tool state as evidence, but should not build an MCP firewall or duplicate lockfile enforcement |
| Build provenance and attestations | [SLSA](https://slsa.dev/spec/v1.2/provenance), [Sigstore](https://docs.sigstore.dev/cosign/verifying/attestation/) | Describe artifact provenance and provide signing / attestation primitives | RuntimeTruth should reuse established attestation primitives where possible rather than invent a new signing ecosystem |

This landscape will change. The purpose of this document is to keep project boundaries explicit, not to claim that RuntimeTruth is the only tool operating in these areas.

## Differentiation hypothesis

The useful unit in RuntimeTruth is not a process, repository, trace, MCP server or deployment manifest by itself.

It is the relationship between three views of one agent runtime:

1. **Declared** — what configuration says should be used.
2. **Resolved** — what the agent/provider/router actually resolves that configuration into.
3. **Live** — what can be established from the running environment.

The project is interesting only if it can connect those layers with explicit provenance.

A future snapshot should be able to support statements such as:

```text
agent process
  |
  +-- executable / runtime version
  +-- code identity
  +-- effective model/provider
  +-- instruction sources
  +-- exposed tools and MCP servers
  +-- sandbox / permission state
  |
  v
evidence-backed runtime snapshot
```

Each field should make clear whether it was declared, resolved, observed live, or unavailable.

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

## Near-term validation

The next validation target is one agent runtime, not a broad adapter catalogue.

The first agent-aware adapter should target **Codex** and attempt to connect the low-level evidence already implemented with agent-specific state such as:

- runtime/version identity
- model/provider declaration and, where observable, effective resolution
- instruction sources and their provenance
- configured tools and MCP servers
- sandbox/network permission state that can be established without inference

The adapter should remain useful without an LLM and should avoid collecting secret values.

## Stop condition

Before adding Claude Code, Gemini CLI, Cursor, Kubernetes or additional infrastructure collectors, the Codex slice should demonstrate a clear answer to this question:

> **Does RuntimeTruth reveal an effective live agent state that would otherwise require manually correlating several independent tools or configuration sources?**

If the answer is no, the model should be reconsidered before the adapter surface grows.
