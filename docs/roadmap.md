# Roadmap

The roadmap is intentionally validation-driven. A phase should prove its data model on real runtimes before the next layer is added.

## Phase 0 — Bootstrap

- project skeleton, packaging and CI
- vision and architecture notes
- define real regression fixtures from existing agent infrastructure
- decide the minimum safe data-collection rules

**Exit:** repository is reproducible and the first real runtime target is documented.

## Phase 1 — Snapshot

- versioned snapshot schema
- local process/host collector
- Git/code identity collector
- environment metadata with secret-safe handling
- systemd unit/runtime collector
- JSON output and fixture tests

**Exit:** `runtimetruth inspect` can produce a stable evidence-backed snapshot for a real Linux agent worker.

## Phase 2 — Semantic diff

- compare two snapshots
- categorize code, runtime, instructions, tooling, permissions and environment changes
- distinguish unavailable data from unchanged data
- human-readable and JSON diff output

**Exit:** a real configuration/runtime change can be identified without manually comparing raw files.

## Phase 3 — Agent-aware adapters

- detect supported agent runtimes
- Codex adapter
- Claude Code adapter
- MCP/tool inventory and schema fingerprints
- model/provider declaration and resolution where observable

**Exit:** snapshots explain agent-specific state, not merely Linux process state.

## Phase 4 — Verification

- local policy format
- approved baselines
- CI-friendly exit codes
- SARIF or equivalent machine-readable reporting
- high-signal policy violations

**Exit:** RuntimeTruth can gate a deployment or CI job on known runtime invariants.

## Phase 5 — Attestation

- canonical snapshot hashing
- signed local attestations
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
