# RuntimeTruth v0.2.0

RuntimeTruth v0.2.0 turns the original runtime-drift CLI into a small, explicit trust pipeline for reviewed AI-agent baselines.

## Highlights

- canonical baseline identity with RFC 8785 + SHA-256
- signed baseline statements using in-toto Statement v1 and Sigstore/Cosign
- exact OIDC signer identity and issuer verification
- fail-closed trust verification before current-runtime collection
- persisted schema-v1 TOML policy files for repeated runtime selectors
- policy composition with direct `--protect` flags
- machine-readable identity/baseline/runtime verification reports
- PyPI distribution through GitHub OIDC Trusted Publishing

## Trust flow

```text
reviewed baseline
      ↓
RFC 8785 canonicalization
      ↓
SHA-256 digest
      ↓
canonical in-toto statement
      ↓
Sigstore/Cosign signature
      ↓
verify exact signer identity + issuer
      ↓
verify baseline binding
      ↓
policy + current runtime
      ↓
PASS / DRIFT / ERROR
```

The policy layer cannot weaken the attestation layer: signature, identity and baseline-binding failures stop verification before runtime policy evaluation.

## Install

```bash
pipx install runtimetruth
```

or:

```bash
uv tool install runtimetruth
```

Standard virtual-environment installs are also supported:

```bash
python -m pip install runtimetruth
```

## Boundary

RuntimeTruth still does not claim that a PASS means an agent is secure, safe or compliant. It proves only the evidence and invariants it explicitly collected and compared.

Broader organizational approval semantics, fleet management and additional agent adapters remain intentionally deferred until external usage justifies them.
