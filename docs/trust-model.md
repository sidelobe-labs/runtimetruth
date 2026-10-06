# Trust model

RuntimeTruth is an evidence-backed comparison tool. Its output is only as strong as the evidence it collected and the baseline selected by the caller.

## Verification outcomes

### PASS

`PASS` means every evidence item selected for verification matched the selected baseline under RuntimeTruth's implemented comparison semantics.

It does **not** mean:

- the agent is secure
- the agent is compliant with a law, standard or organizational policy
- the agent will behave safely or correctly
- every runtime input was inspected
- the selected baseline is trustworthy
- the observed files or configuration necessarily equal the exact bytes later consumed by a model

### DRIFT

`DRIFT` means RuntimeTruth found a semantic difference in evidence selected for verification.

Drift is not automatically malicious or unsafe. It can represent an intended runtime update. RuntimeTruth reports the difference so the caller can decide whether to accept it and, if appropriate, deliberately update the baseline.

### ERROR

`ERROR` means verification did not complete faithfully. Examples include unreadable snapshots, incompatible targets, unsupported evidence, provenance changes that schema v1 cannot compare, invalid selectors or runtime collection failures.

An error must not be treated as a PASS.

## Evidence planes

RuntimeTruth keeps three evidence concepts separate:

- **declared** — what configuration or deployment inputs state
- **resolved** — what the inspected runtime's own resolution path materializes
- **live** — what RuntimeTruth can observe directly from the environment at collection time

The collector must not silently upgrade an inferred value into a stronger evidence plane.

## Baseline boundary

Normal `verify` still treats the baseline as a file selected by the caller.

For workflows that need stronger provenance, RuntimeTruth also supports an optional signed-baseline attestation path:

```text
baseline
  -> RFC 8785 canonical SHA-256 digest
  -> canonical in-toto Statement v1
  -> Sigstore keyless signature over exact statement bytes
  -> exact signer identity verification
  -> baseline digest binding
  -> runtime comparison
```

`verify-attestation` fails unless Cosign verifies the exact signed statement bytes against the Sigstore bundle, expected certificate identity and OIDC issuer, and RuntimeTruth confirms that the signed in-toto subject digest matches the supplied canonical baseline.

This improves baseline integrity and signer provenance, but RuntimeTruth still does **not** establish:

- whether that signer was organizationally authorized to approve the baseline
- whether the baseline itself is secure or compliant
- whether the signing identity was compromised
- whether the baseline came from a particular deployment unless the surrounding workflow establishes that fact
- whether uncollected runtime state matches the signer's intent

An unsigned baseline can still be replaced by an attacker who controls the verification inputs. A signed baseline can still be malicious or incorrect if the trusted signer approved the wrong state. Treat signer identity configuration and baseline review as security-sensitive inputs.

See [signed baseline attestations](attestation.md).

## Codex thread boundary

When `--resolve-thread` is used, RuntimeTruth starts a new ephemeral Codex thread to observe settings materialized for that thread. It does not inspect an already-running user's thread and does not start a model turn.

Evidence from that probe should therefore be described as effective state materialized for a newly created ephemeral thread in the inspected workspace.

## Instruction fingerprint boundary

RuntimeTruth fingerprints the bytes it can read from paths reported by Codex as instruction sources.

That proves which bytes RuntimeTruth observed at those reported paths at snapshot time. It does not cryptographically prove that the model consumed those exact bytes in a later request.

Instruction plaintext is not serialized by the fingerprint collector.

## MCP boundary

RuntimeTruth records thread-scoped MCP runtime status and a bounded representation/fingerprint of the tool catalog visible through Codex.

This is evidence about the inspected agent's effective capability surface. It is **not** an MCP server contract-safety or backwards-compatibility test.

Tools such as [MCPWard](https://github.com/TsvetanG2/mcpward) are better suited to detailed MCP contract testing, schema drift classification, protocol checks and server-focused security heuristics.

RuntimeTruth's MCP status probe does not call MCP tools. The probe may cause Codex to contact configured MCP servers or refresh authentication, so it remains explicit opt-in behavior.

## Security boundary

RuntimeTruth intentionally avoids broad secret collection.

Current collectors use allowlists, hashes and status metadata where possible. A future collector that needs stronger access must document its side effects and data boundary explicitly before it can be treated as equivalent evidence.
