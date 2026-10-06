# Roadmap

The roadmap is intentionally validation-driven. A phase should prove its data model on real runtimes before the next layer is added.

## Current checkpoint

The local core has now been validated on real Linux/systemd workloads:

- systemd service evidence
- procfs process identity
- Git repository identity
- composed service -> process -> repository inspection
- semantic snapshot diff validated against a real restart and code change

Generic infrastructure expansion is intentionally paused here. The next question is whether the same evidence model becomes genuinely useful for **agent-specific effective state**.

## Phase 0 — Bootstrap

- project skeleton, packaging and CI
- vision and architecture notes
- define real regression fixtures from existing agent infrastructure
- decide the minimum safe data-collection rules

**Exit:** repository is reproducible and the first real runtime target is documented.

## Phase 1 — Snapshot

- versioned snapshot schema
- local process identity collector
- Git/code identity collector
- systemd unit/runtime collector
- JSON output and fixture tests
- compose service, process and repository evidence

**Exit:** `runtimetruth inspect` can produce a stable evidence-backed snapshot for a real Linux agent worker.

## Phase 2 — Semantic diff

- compare two schema-v1 snapshots
- categorize service, process and code changes
- distinguish unavailable data from unchanged data
- human-readable semantic diff

**Exit:** a real runtime restart and code change can be identified without manually comparing raw snapshot JSON.

## Phase 3 — Agent-aware validation

Start with one runtime: **Codex**.

- identify the supported Codex runtime/version
- locate relevant declared configuration without collecting secrets
- identify instruction sources with provenance
- inventory configured tools and MCP servers as evidence, not enforcement
- observe model/provider resolution where it can be established reliably
- record sandbox/network permission state where observable
- classify each fact as declared, resolved, live or unavailable
- validate the adapter against a real local Codex runtime

Do **not** add Claude Code, Gemini CLI, Cursor or broad container/Kubernetes support until this slice proves the model.

**Exit:** one Codex snapshot demonstrates effective runtime state that would otherwise require manually correlating multiple independent configuration/runtime sources.

**Stop condition:** if the Codex slice is only a repackaging of existing inventory, tracing or process data, reconsider the product model before adding adapters.

## Phase 4 — Verification

Only after the agent-aware model is useful:

- local policy format
- approved baselines
- CI-friendly exit codes
- high-signal policy violations
- machine-readable reporting where a concrete integration requires it

**Exit:** RuntimeTruth can gate a deployment or runtime check on explicit, evidence-backed invariants.

## Phase 5 — Attestation

- canonical snapshot hashing
- integrate established signing/attestation primitives rather than inventing a new trust stack
- verification command
- provenance and schema migration rules

**Exit:** an agent runtime can produce a portable, independently verifiable statement of observed state.

## Phase 6 — Product validation

Only after external OSS users exist:

- optional hosted history
- fleet view
- drift alerts
- organization policies
- GitHub/GitLab integrations

Commercial features should be driven by actual team requests rather than built speculatively.

## Candidate commercial layer

Possible paid capabilities:

- fleet-wide runtime history and search
- centralized policy/baseline management
- Slack/email/webhook alerts
- audit trails and retention
- RBAC, SSO/SAML/SCIM
- enterprise runtime integrations
- managed control plane or BYOC/on-prem options
- support and SLA

## Validation signals before building cloud

Aim for:

- external users running the CLI on real agents
- multiple teams using verify/diff in CI or operations
- repeated requests for central history, alerts or policy management

The first cloud feature should answer a demonstrated request, not create a new category of work.
