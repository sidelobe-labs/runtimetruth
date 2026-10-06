# CI integration

RuntimeTruth's verification command is designed to work as a normal CI gate. It does not require a GitHub-specific wrapper.

## Exit-code contract

```text
0  PASS   compared runtime state matches the selected baseline/invariants
2  DRIFT  semantic runtime drift was detected
1  ERROR  collection, input or comparison failed
```

A CI runner can therefore use `runtimetruth verify` directly and let the process exit code gate the job.

## Installation before the first tagged release

RuntimeTruth is not yet published to PyPI. Until tagged releases exist, install from a pinned Git commit after the repository is public:

```bash
python -m pip install \
  "git+https://github.com/sidelobe-labs/runtimetruth.git@<PINNED_COMMIT>"
```

Do not install from an unpinned moving branch in a production gate. Once tagged releases exist, prefer a tagged or packaged release.

## Strict baseline gate

If the repository contains an approved RuntimeTruth snapshot:

```bash
runtimetruth verify .runtimetruth/baseline.json current.json
```

Any semantic drift in supported evidence fails with exit code `2`.

## Live Codex gate

RuntimeTruth can collect the current Codex runtime in memory and compare it directly:

```bash
runtimetruth verify \
  .runtimetruth/baseline.json \
  --codex "$GITHUB_WORKSPACE" \
  --resolve-thread
```

`--resolve-thread` creates an ephemeral thread but does not start a turn or model request.

If MCP runtime state is part of the baseline, use `--resolve-mcp`. That probe is deliberately explicit because Codex may contact configured MCP servers or refresh authentication while resolving MCP status. RuntimeTruth does not call MCP tools.

## Selective invariants

Strict baseline equality is the default. Use repeatable `--protect` selectors when only specific agent-runtime invariants should gate the job:

```bash
runtimetruth verify \
  .runtimetruth/baseline.json \
  --codex "$GITHUB_WORKSPACE" \
  --resolve-thread \
  --protect codex.thread.model \
  --protect codex.thread.model_provider \
  --protect codex.thread.approval_policy \
  --protect codex.thread.sandbox \
  --protect codex.instructions
```

A selector can protect an entire evidence kind, such as `codex.instructions`, or one exact scalar field, such as `codex.thread.model`.

Unknown selectors are errors rather than silent passes.

## Machine-readable report

Add `--json` to emit a versioned PASS/DRIFT report while preserving the same process exit code:

```bash
set +e
runtimetruth verify \
  .runtimetruth/baseline.json \
  --codex "$GITHUB_WORKSPACE" \
  --resolve-thread \
  --protect codex.thread.model \
  --protect codex.instructions \
  --json > runtimetruth-report.json
status=$?
set -e

cat runtimetruth-report.json
exit "$status"
```

The report contains the target, protected selectors and structured semantic changes. Missing values remain distinct from JSON `null`.

## GitHub Actions example

The following intentionally uses the CLI directly rather than a Marketplace Action that does not yet exist:

```yaml
name: RuntimeTruth

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-runtime:
    runs-on: self-hosted

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install RuntimeTruth
        run: |
          python -m pip install \
            "git+https://github.com/sidelobe-labs/runtimetruth.git@<PINNED_COMMIT>"

      - name: Verify effective Codex runtime
        run: |
          runtimetruth verify \
            .runtimetruth/baseline.json \
            --codex "$GITHUB_WORKSPACE" \
            --resolve-thread \
            --protect codex.thread.model \
            --protect codex.thread.model_provider \
            --protect codex.thread.approval_policy \
            --protect codex.thread.sandbox \
            --protect codex.instructions
```

Use a runner that actually contains the runtime being verified. A GitHub-hosted runner cannot prove the state of an agent running on some other host.

## Baseline handling

A baseline is currently only a snapshot file selected by the caller. RuntimeTruth does not yet claim that it is signed, centrally approved or tamper-evident.

Treat baseline updates like dependency-lockfile changes:

1. capture a new snapshot deliberately,
2. review the semantic diff,
3. commit the new baseline only when the runtime change is intended.

Automatic re-baselining in the same job that performs verification would defeat the purpose of the gate.
