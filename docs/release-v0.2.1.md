# RuntimeTruth v0.2.1

RuntimeTruth v0.2.1 is a release-hygiene patch. It does not change runtime collection, diff, policy or attestation semantics.

## Fixed

- package-description documentation links are portable when the README is rendered outside GitHub
- the License badge now links to the canonical repository license instead of a repository-relative target

## Release hardening

- built wheel and source distributions must pass `twine check --strict` in CI
- the tag-triggered release workflow performs the same metadata validation before publication
- regression tests keep package and CLI versions aligned
- regression tests require the README public-alpha version and release link to match the package version
- regression tests require the matching changelog entry and release-notes file to exist
- README Markdown link targets are checked for package-index portability

## Runtime boundary

There are no runtime-behaviour changes in v0.2.1. The RuntimeTruth trust model, snapshot semantics, policy evaluation, attestation verification and PASS / DRIFT / ERROR contract remain the same as v0.2.0.

## Install

```bash
pipx install --force runtimetruth==0.2.1
```

or:

```bash
uv tool install --force runtimetruth==0.2.1
```

Standard virtual-environment installs remain supported:

```bash
python -m pip install runtimetruth==0.2.1
```
