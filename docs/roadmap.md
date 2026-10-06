# Roadmap

The roadmap is intentionally validation-driven. A phase should prove its data model on real runtimes before the next layer is added.

## Current checkpoint

RuntimeTruth v0.1.0 is public. Phases 0–4 are validated end to end on real Codex runtimes, including live verification, selective protected invariants, machine-readable reports and CI-friendly exit semantics.

The current implementation can:

- collect systemd, procfs and Git identity evidence
- collect Codex runtime/version and canonical resolved configuration
- resolve effective model/provider, approval and sandbox state through an ephemeral Codex thread
- record Codex-reported instruction source paths and live SHA-256 fingerprints without storing instruction plaintext
- inspect thread-scoped MCP runtime status and bounded tool-catalog fingerprints without calling MCP tools
- semantically diff snapshots
- verify snapshot-vs-snapshot baselines with stable PASS / DRIFT / ERROR exit codes
- collect a live Codex runtime and verify it directly against a baseline

Generic infrastructure expansion and additional agent adapters remain intentionally paused. The immediate post-v0.1.0 priority is distribution and external validation rather than surface-area growth.

## Immediate post-v0.1.0 priorities

### 1. Distribution and install friction

Ship the existing CLI through normal Python distribution channels before adding new runtime features.

Candidates:

- publish RuntimeTruth to PyPI using trusted publishing rather than a long-lived API token
- document `pipx`, `uv tool` and standard `pip` installation paths
- smoke-test the published wheel from a clean environment
- keep source-pinned installation documented for CI workflows that require an exact commit

**Exit:** a new user can install the released CLI without cloning the repository.

### 2. External validation

Use the public v0.1.x line to learn which workflows real users actually need.

Signals to collect:

- successful installs on machines we do not control
- baseline verification in real CI or operational workflows
- which invariants users protect repeatedly
- where snapshot evidence is still ambiguous or too noisy
- repeated requests for another agent runtime

**Guardrail:** do not add Claude Code, Gemini CLI, Cursor or another adapter only to make the compatibility list longer.

### 3. CI ergonomics

Only after source/PyPI installation is proven in real workflows, reduce recurring setup friction.

Possible next step:

- a minimal GitHub Action or reusable workflow that invokes the same CLI and preserves the existing `0 / 2 / 1` exit contract

The Action must remain a thin integration layer, not a second verification engine.

### 4. Verification hardening

Only add policy syntax when repeated CLI selectors become a real usability problem.

Candidates:

- persisted local invariant file
- clearer allowed-drift rules with the same explicit evidence semantics
- additional structured output only for concrete integrations

**Exit:** repeated production verification remains readable without weakening evidence or error semantics.

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

**Status:** validated and released in v0.1.0.

**Exit:** achieved. RuntimeTruth can gate a deployment or runtime check on explicit, evidence-backed invariants.

## Phase 5 — Attestation

Start only after the v0.1.x verification workflow has external users and the baseline trust boundary becomes a demonstrated limitation.

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
