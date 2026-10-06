# Signed baseline attestation

RuntimeTruth can bind an approved baseline snapshot to a signer identity before using that baseline to verify a current runtime.

The trust flow is deliberately explicit:

```text
baseline snapshot
   ↓ RFC 8785 canonicalization
canonical SHA-256 digest
   ↓ in-toto Statement v1
canonical attestation statement
   ↓ Sigstore / cosign keyless signature
Sigstore bundle
   ↓ verify signer identity + baseline digest
trusted baseline
   ↓ compare current runtime
PASS / DRIFT / ERROR
```

RuntimeTruth does not implement custom cryptography. It uses RFC 8785 for JSON canonicalization, SHA-256 for baseline identity, in-toto Statement v1 for the signed claim, and Sigstore Cosign for identity-backed signing and verification.

## Requirements

- RuntimeTruth
- a recent `cosign` executable available on `PATH`
- an OIDC identity that Sigstore can use for keyless signing

For GitHub Actions, keyless signing normally requires:

```yaml
permissions:
  contents: read
  id-token: write
```

A GitHub Actions signer identity is typically shaped like:

```text
https://github.com/OWNER/REPOSITORY/.github/workflows/WORKFLOW@refs/heads/BRANCH
```

with issuer:

```text
https://token.actions.githubusercontent.com
```

## 1. Capture and review a baseline

```bash
runtimetruth inspect codex . --resolve-thread --pretty > baseline.json
```

## 2. Compute the canonical baseline digest

```bash
runtimetruth digest baseline.json
```

Example:

```text
sha256:7fd9...
```

The digest is computed from the parsed schema-v1 snapshot serialized with RFC 8785 JSON Canonicalization Scheme. JSON whitespace and object-key ordering therefore do not affect the digest.

Duplicate JSON object keys are rejected before canonicalization.

## 3. Create a signed attestation

```bash
runtimetruth attest baseline.json \
  --statement baseline.intoto.json \
  --bundle baseline.sigstore.json
```

RuntimeTruth:

1. parses the baseline snapshot,
2. computes its RFC 8785 canonical SHA-256 digest,
3. builds a minimal in-toto Statement v1 whose single subject is that digest,
4. serializes the statement itself with RFC 8785,
5. asks `cosign sign-blob` to sign those exact statement bytes,
6. stores Sigstore verification material in the requested bundle.

The signed statement predicate type is:

```text
https://sidelobe.dev/runtimetruth/attestation/v1
```

The predicate contains only:

- RuntimeTruth attestation schema version
- RuntimeTruth snapshot schema version
- canonicalization identifier (`RFC8785`)

The baseline contents are not duplicated into the statement predicate.

RuntimeTruth refuses to overwrite an existing statement or bundle.

## 4. Verify identity and runtime

Snapshot-to-snapshot:

```bash
runtimetruth verify-attestation \
  baseline.json \
  current.json \
  --statement baseline.intoto.json \
  --bundle baseline.sigstore.json \
  --certificate-identity "EXPECTED_IDENTITY" \
  --certificate-oidc-issuer "EXPECTED_ISSUER"
```

Live Codex:

```bash
runtimetruth verify-attestation \
  baseline.json \
  --statement baseline.intoto.json \
  --bundle baseline.sigstore.json \
  --certificate-identity "EXPECTED_IDENTITY" \
  --certificate-oidc-issuer "EXPECTED_ISSUER" \
  --codex . \
  --resolve-thread
```

Verification fails closed.

RuntimeTruth first asks `cosign verify-blob` to verify the exact statement bytes against:

- the Sigstore bundle
- the exact expected certificate identity
- the exact expected OIDC issuer
- the Sigstore trust and transparency material supported by the installed Cosign version

Only after Cosign succeeds, RuntimeTruth independently requires:

- canonical RFC 8785 statement bytes
- in-toto Statement v1
- exactly one RuntimeTruth baseline subject
- SHA-256 subject digest equals the canonical baseline digest
- RuntimeTruth predicate type
- RuntimeTruth attestation schema version
- snapshot schema version
- canonicalization identifier
- no unexpected root or predicate fields

Only after those checks does RuntimeTruth load or collect the current runtime and run the normal semantic comparison.

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

That does **not** weaken the signed baseline binding: the complete baseline snapshot is canonicalized and its digest is bound to the signed statement.

Selectors only control which semantic runtime differences fail the runtime gate after the baseline itself has been authenticated.

## Trust boundary

A successful attestation verification means:

1. Cosign verified that the exact statement bytes were signed by the expected OIDC identity under the expected issuer.
2. RuntimeTruth verified that the signed in-toto subject binds to the canonical SHA-256 digest of the supplied baseline.
3. The RuntimeTruth predicate matches the supported attestation schema.
4. The current runtime matched the selected baseline invariants if the command returned PASS.

It does **not** establish that:

- the signer was organizationally authorized to approve the baseline
- the baseline represents a secure or compliant configuration
- the runtime contains no uncollected state
- the agent will behave safely
- the signing identity itself was not compromised
- a protected subset covers every security-relevant property

Those higher-level decisions remain outside the current RuntimeTruth trust model.

## Files that must travel together

A portable attested baseline consists of:

```text
baseline.json
baseline.intoto.json
baseline.sigstore.json
```

The baseline is the state to compare against. The in-toto statement binds its canonical digest. The Sigstore bundle proves who signed the statement.

## Why RFC 8785

Cryptographic hashes need an invariant representation. RuntimeTruth uses the standardized JSON Canonicalization Scheme defined by RFC 8785 rather than treating whitespace or JSON object-key order as meaningful baseline changes.

The implementation uses the `rfc8785` Python package for this security-sensitive serialization step rather than maintaining a project-specific canonicalizer.

## Why Sigstore

Sigstore keyless signing binds an ephemeral signing key to an OIDC identity using short-lived certificates and transparency infrastructure.

RuntimeTruth deliberately relies on Cosign for this layer rather than inventing a private-key storage scheme or signature format.
