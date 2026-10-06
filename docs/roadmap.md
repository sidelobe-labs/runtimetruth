# Roadmap

The roadmap is intentionally validation-driven. A phase should prove its data model on real runtimes before the next layer is added.

## Current checkpoint

RuntimeTruth v0.2.0 is the current release milestone. Phases 0–5 now have a validated vertical slice: runtime inspection, semantic verification, persisted selectors, canonical baseline identity and identity-backed signed-baseline verification.

The current implementation can:

- collect systemd, procfs and Git identity evidence
- collect Codex runtime/version and canonical resolved configuration
- resolve effective model/provider, approval and sandbox state through an ephemeral Codex thread
- record Codex-reported instruction source paths and live SHA-256 fingerprints without storing instruction plaintext
- inspect thread-scoped MCP runtime status and bounded tool-catalog fingerprints without calling MCP tools
- semantically diff snapshots
- verify snapshot-vs-snapshot baselines with stable PASS / DRIFT / ERROR exit codes
- collect a live Codex runtime and verify it directly against a baseline
- persist repeated runtime selectors in an explicit schema-v1 TOML policy
- canonicalize and hash a reviewed baseline with RFC 8785 + SHA-256
- bind that digest to a canonical in-toto statement signed with Sigstore/Cosign
- verify exact signer identity and baseline binding before runtime policy evaluation

Generic infrastructure expansion and additional agent adapters remain intentionally paused. The immediate priority is PyPI distribution and external validation rather than surface-area growth.

## Immediate post-v0.2.0 priorities

### 1. Distribution and install friction

Ship the existing CLI through normal Python distribution channels before adding new runtime features.

Implemented for v0.2.0:

- GitHub OIDC Trusted Publishing workflow with no long-lived PyPI token
- documented `pipx`, `uv tool` and standard `pip` installation paths
- package build and clean-wheel smoke testing in CI
- source-pinned installation retained for unreleased CI validation

**Status:** shipped. RuntimeTruth v0.2.0 is published on PyPI through GitHub OIDC Trusted Publishing.

**Exit:** achieved. A new user can install the released CLI without cloning the repository.

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

The first persisted policy slice is implemented: an explicit TOML file stores only protected runtime selectors and composes with direct `--protect` flags.

Next changes should be justified by real workflows rather than growing a policy DSL.

**Exit:** repeated production verification remains readable without weakening evidence, attestation, or error semantics.

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

Implemented since v0.1.0:

- explicit schema-v1 TOML policy files for repeated protected selectors
- additive CLI `--protect` selectors with deterministic de-duplication
- policy support in both plain and signed-baseline verification

**Current trust boundary:** plain verification still trusts a caller-selected baseline. The attestation path can authenticate a canonical baseline digest against an exact expected signing identity; organizational approval semantics remain outside RuntimeTruth.

**Status:** validated and released in v0.1.0.

**Exit:** achieved. RuntimeTruth can gate a deployment or runtime check on explicit, evidence-backed invariants.

## Phase 5 — Attestation

The first vertical slice is implemented around the baseline trust boundary:

- RFC 8785 canonical snapshot hashing
- SHA-256 baseline identity
- in-toto Statement v1 predicate
- canonical in-toto Statement v1 signed through Sigstore/Cosign keyless `sign-blob`
- exact OIDC signer identity verification
- signed subject digest verification before runtime comparison

Still deferred until justified by external workflows:

- organizational approval/authority semantics
- portable provenance beyond one signed baseline
- schema migration rules for signed attestations
- richer attestation policy or multi-party approval

**Status:** first identity + baseline integrity slice implemented; broader provenance remains experimental.

**Exit:** partially achieved. A baseline can now be bound to a verifiable signing identity before RuntimeTruth compares the current runtime.

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
