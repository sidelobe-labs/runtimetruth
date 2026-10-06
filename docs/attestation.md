# Signed baseline attestations

RuntimeTruth can bind a baseline snapshot to an identity-backed Sigstore attestation before using that baseline to verify a current runtime.

The trust flow is intentionally explicit:

```text
baseline snapshot
   ↓ RFC 8785 JSON Canonicalization Scheme
canonical SHA-256 digest
   ↓ in-toto Statement v1
RuntimeTruth predicate
   ↓ DSSE + Sigstore keyless signing
Sigstore bundle
   ↓ exact signer identity verification
verified baseline
   ↓ RuntimeTruth semantic comparison
current runtime -> PASS / DRIFT / ERROR
```

RuntimeTruth does not implement its own signature algorithm, key format, certificate authority or transparency log. It delegates signing and identity verification to Sigstore Cosign.

## Requirements

- RuntimeTruth
- a recent `cosign` executable available on `PATH`
- an OIDC identity that Sigstore can use for keyless signing

For GitHub Actions, the signing job needs:

```yaml
permissions:
  contents: read
  id-token: write
```

A GitHub Actions signing identity is typically:

```text
https://github.com/OWNER/REPOSITORY/.github/workflows/WORKFLOW@refs/heads/BRANCH
```

with OIDC issuer:

```text
https://token.actions.githubusercontent.com
```

## 1. Capture a baseline

```bash
runtimetruth inspect codex . --resolve-thread --pretty > baseline.json
```

## 2. Review the canonical digest

```bash
runtimetruth digest baseline.json
```

Example:

```text
sha256:7fd9...
```

The digest is computed from RFC 8785 canonical JSON rather than the original file bytes. Pretty-printed and compact representations of the same supported snapshot therefore produce the same digest.

Array order remains part of the snapshot data and is not reordered by canonicalization.

## 3. Create a signed attestation

```bash
runtimetruth attest baseline.json \
  --bundle baseline.sigstore.json
```

RuntimeTruth:

1. parses the baseline using the supported snapshot schema,
2. writes the RFC 8785 canonical snapshot into a temporary file,
3. creates a small RuntimeTruth predicate,
4. asks `cosign attest-blob` to produce a DSSE-wrapped in-toto Statement v1,
5. stores the signed material in the requested Sigstore bundle,
6. removes temporary canonicalization inputs.

The predicate type is:

```text
https://sidelobe.dev/runtimetruth/attestation/v1
```

The predicate contains only:

- RuntimeTruth attestation schema version
- RuntimeTruth snapshot schema version
- canonicalization identifier (`RFC8785`)

The baseline contents are not duplicated into the predicate. The in-toto subject binds the attestation to the SHA-256 digest of the canonical baseline.

RuntimeTruth refuses to overwrite an existing bundle.

## 4. Verify identity and runtime

Snapshot-to-snapshot:

```bash
runtimetruth verify-attestation \
  baseline.json \
  current.json \
  --bundle baseline.sigstore.json \
  --certificate-identity "EXPECTED_IDENTITY" \
  --certificate-oidc-issuer "EXPECTED_ISSUER"
```

Live Codex:

```bash
runtimetruth verify-attestation \
  baseline.json \
  --bundle baseline.sigstore.json \
  --certificate-identity "EXPECTED_IDENTITY" \
  --certificate-oidc-issuer "EXPECTED_ISSUER" \
  --codex . \
  --resolve-thread
```

Verification fails closed.

RuntimeTruth first asks `cosign verify-blob-attestation` to verify:

- the Sigstore bundle
- Fulcio certificate chain and transparency-log evidence supported by Cosign
- the exact expected certificate identity
- the exact expected OIDC issuer
- the in-toto subject digest against the RFC 8785 canonical baseline
- the expected RuntimeTruth predicate type

After Cosign succeeds, RuntimeTruth independently decodes the signed DSSE payload and checks:

- in-toto Statement v1
- exactly one subject
- SHA-256 subject digest equals the canonical baseline digest
- RuntimeTruth predicate type
- RuntimeTruth attestation schema version
- snapshot schema version
- canonicalization identifier
- no unexpected root or predicate fields

Only after those checks does RuntimeTruth collect/load the current runtime and run the normal semantic comparison.

## Output

A successful human-readable verification is:

```text
IDENTITY: VERIFIED
  certificate_identity: ...
  oidc_issuer: ...
BASELINE: VERIFIED
  sha256: ...
RUNTIME: PASS
```

If signer identity and baseline binding are valid but runtime state differs:

```text
IDENTITY: VERIFIED
BASELINE: VERIFIED
RUNTIME: DRIFT
...
```

Exit codes remain:

```text
0  identity valid + baseline valid + runtime matches
2  identity valid + baseline valid + semantic runtime drift
1  signing, identity, attestation, baseline, collection or comparison error
```

Add `--json` to `verify-attestation` for a machine-readable trust/runtime report.

## Selective verification

`verify-attestation` supports the same repeatable `--protect` selectors as normal verification.

That does **not** weaken the signed baseline binding: the complete baseline snapshot is still canonicalized, hashed and bound to the signed attestation.

Selectors only control which semantic runtime differences fail the runtime gate after the baseline itself has been authenticated.

## Trust boundary

A successful attestation verification means:

1. Cosign verified that the DSSE attestation was signed by the exact expected OIDC identity under the exact expected issuer.
2. The signed in-toto subject binds to the canonical SHA-256 digest of the supplied baseline.
3. The RuntimeTruth predicate matches the supported attestation schema.
4. The current runtime matched the selected baseline invariants if the command returned PASS.

It does **not** establish that:

- the signer was organizationally authorized to approve the baseline
- the baseline represents a secure or compliant configuration
- the runtime contains no uncollected state
- the agent will behave safely
- the signing identity itself was not compromised
- a protected subset covers every security-relevant property

Those higher-level decisions remain outside RuntimeTruth v0.1.x.

## Why RFC 8785

Cryptographic hashes need an invariant representation. RuntimeTruth uses the standardized JSON Canonicalization Scheme defined by RFC 8785 rather than treating whitespace or JSON object key order as meaningful baseline changes.

The implementation uses the `rfc8785` Python package for this security-sensitive serialization step instead of maintaining a project-specific canonicalizer.

## Why Sigstore

Sigstore keyless signing binds an ephemeral signing key to an OIDC identity using short-lived certificates and records signing events in transparency infrastructure.

RuntimeTruth deliberately relies on Cosign for this layer rather than inventing a private-key storage scheme or signature format.
