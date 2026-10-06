# Roadmap

The roadmap is intentionally validation-driven. A phase should prove its data model on real runtimes before the next layer is added.

## Current checkpoint

Phases 0–3 are validated, and the first Phase 4 verification primitives are working on real Codex snapshots and live collection.

The current implementation can:

- collect systemd, procfs and Git identity evidence
- collect Codex runtime/version and canonical resolved configuration
- resolve effective model/provider, approval and sandbox state through an ephemeral Codex thread
- record Codex-reported instruction source paths and live SHA-256 fingerprints without storing instruction plaintext
- inspect thread-scoped MCP runtime status and bounded tool-catalog fingerprints without calling MCP tools
- semantically diff snapshots
- verify snapshot-vs-snapshot baselines with stable PASS / DRIFT / ERROR exit codes
- collect a live Codex runtime and verify it directly against a baseline

Generic infrastructure expansion and additional agent adapters remain intentionally paused while the verification model is hardened.

## Phase 0 — Bootstrap

- project skeleton, packaging and CI
- vision and architecture notes
- define real regression fixtures from existing agent infrastructure
- decide the minimum safe data-collection rules

**Status:** validated.

**Exit:** repository is reproducible and the first real runtime target is documented.

## Phase 1 — Snapshot

- versioned snapshot schema
- local process identity collector
- Git/code identity collector
- systemd unit/runtime collector
- JSON output and fixture tests
- compose service, process and repository evidence

**Status:** validated on real Linux/systemd workloads.

**Exit:** `runtimetruth inspect` can produce a stable evidence-backed snapshot for a real Linux agent worker.

## Phase 2 — Semantic diff

- compare two schema-v1 snapshots
- categorize service, process and code changes
- distinguish unavailable data from unchanged data
- human-readable semantic diff

**Status:** validated against a real service restart, code change, Codex instruction-source change, and instruction fingerprint drift.

**Exit:** real runtime changes can be identified without manually comparing raw snapshot JSON.

## Phase 3 — Agent-aware validation

Initial runtime: **Codex**.

Implemented and validated:

- installed Codex runtime/version identity
- canonical workspace configuration through Codex app-server
- effective model/provider, approval policy and sandbox state materialized for an ephemeral thread
- instruction source paths reported by Codex
- live SHA-256 fingerprints of those instruction files without plaintext capture
- thread-scoped MCP server/runtime status
- bounded MCP tool-name inventory and deterministic full-catalog fingerprints
- explicit resolved/live provenance boundaries
- semantic diff support for Codex evidence

The real validation demonstrated a material distinction between workspace configuration and effective thread state: fields left unresolved at config level were materialized when Codex created a thread.

**Status:** validated on Codex 0.156.1 in a real local environment.

**Exit:** achieved. The Codex slice exposes effective runtime state that otherwise requires correlating separate configuration, filesystem and runtime sources.

**Guardrail:** do not add Claude Code, Gemini CLI, Cursor, Kubernetes or broad infrastructure collectors merely to expand surface area. Add another adapter only when it tests a concrete product need.

## Phase 4 — Verification

Implemented:

- caller-selected baseline snapshots
- snapshot-vs-snapshot verification
- live Codex collection against a baseline
- CI-friendly exit codes: `0` PASS, `2` DRIFT, `1` ERROR
- semantic drift output using the existing diff engine
- repeatable evidence-kind and exact-field protected invariants
- versioned machine-readable PASS/DRIFT reports

Next candidates, only when justified by a concrete workflow:

- a persisted local invariant/policy file if repeated CLI selectors become cumbersome
- high-signal policy violations that remain grounded in explicit evidence
- additional machine-readable formats only when a concrete integration requires them

**Current trust boundary:** a baseline is a file selected by the caller. It is not yet signed, centrally approved, or tamper-evident.

**Exit:** RuntimeTruth can gate a deployment or runtime check on explicit, evidence-backed invariants.

## Phase 5 — Attestation

- canonical snapshot hashing
- integrate established signing/attestation primitives rather than inventing a new trust stack
- portable verification
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
