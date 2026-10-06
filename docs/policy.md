# Verification policy

RuntimeTruth supports a deliberately small persisted verification policy for workflows that would otherwise repeat the same `--protect` selectors on every invocation.

The policy is not a general authorization or compliance language. It stores only the evidence selectors that should gate verification.

## Schema v1

```toml
version = 1

protect = [
  "codex.thread.model",
  "codex.thread.model_provider",
  "codex.thread.approval_policy",
  "codex.thread.sandbox",
  "codex.instructions",
]
```

Only the top-level keys `version` and `protect` are accepted.

- `version` must be integer `1`
- `protect` must be a non-empty array of string selectors
- duplicate selectors are removed while preserving their first occurrence
- surrounding selector whitespace is ignored
- unknown keys, malformed TOML, wrong types and unsupported versions are errors

## Usage

Pass the policy explicitly:

```bash
runtimetruth verify \
  .runtimetruth/baseline.json \
  --codex . \
  --resolve-thread \
  --policy .runtimetruth/policy.toml
```

RuntimeTruth does not auto-discover a policy file.

Selectors passed directly on the CLI extend the persisted list:

```bash
runtimetruth verify \
  .runtimetruth/baseline.json \
  --codex . \
  --resolve-thread \
  --policy .runtimetruth/policy.toml \
  --protect codex.mcp
```

The final selector list is de-duplicated and is reported through the existing `protected` field in `--json` output.

## Selector semantics

Policy selectors use the same validation path as `--protect`.

A selector can name:

- a supported evidence kind, such as `codex.instructions`
- one exact scalar field, such as `codex.thread.model`

An unknown selector, unavailable evidence kind or field that does not exist in the compared snapshots is an error rather than a silent pass.

## Deliberate boundaries

The policy file does **not** contain:

- the baseline path
- a baseline hash or approval identity
- allow/deny expressions
- numeric risk scores
- arbitrary conditions
- automatic baseline updates
- policy inheritance or auto-discovery

The baseline remains an explicit caller-selected input:

```text
baseline snapshot + explicit policy + current runtime -> PASS / DRIFT / ERROR
```

The policy controls only the semantic runtime gate. It does not select, approve, sign, or authenticate a baseline.

When used with `verify-attestation`, RuntimeTruth verifies the signed statement, exact signer identity, issuer, and canonical baseline binding before it loads the policy or collects/loads the current runtime. The policy can therefore narrow runtime drift checks, but it cannot weaken or bypass attestation verification.
