# RuntimeTruth v0.2.2

This is a packaging and documentation update. Runtime collection, comparison, policy and attestation behaviour are unchanged.

## Changed

- The PyPI summary now describes the supported Codex adapter instead of suggesting general AI-agent coverage.
- The published PyPI description matches the current repository README, including the explicit limits of the verification result.
- Releases can be published automatically when the package version changes on `main`; versioned metadata and packaging checks run before publication.

## Install

```bash
pipx install runtimetruth==0.2.2
```

A virtual-environment install is also supported with `python -m pip install runtimetruth==0.2.2`.

## Scope

RuntimeTruth currently supports Codex and limited local system/process/Git inspection. A PASS only means the selected observations match the selected baseline. It is not a certification of agent behaviour, model safety or baseline trust.
