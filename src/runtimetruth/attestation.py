"""Canonical baseline hashing and Sigstore-backed attestation support."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import rfc8785

from runtimetruth.model import Snapshot

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://sidelobe.dev/runtimetruth/attestation/v1"
ATTESTATION_SCHEMA_VERSION = 1
CANONICALIZATION = "RFC8785"
_DSSE_PAYLOAD_TYPE = "application/vnd.in-toto+json"


class AttestationError(RuntimeError):
    """Raised when an attestation cannot be created or verified safely."""


def canonical_snapshot_bytes(snapshot: Snapshot) -> bytes:
    """Serialize one snapshot with RFC 8785 JSON Canonicalization Scheme."""
    try:
        return rfc8785.dumps(snapshot.to_dict())
    except rfc8785.CanonicalizationError as exc:
        raise AttestationError(f"snapshot cannot be canonicalized with RFC 8785: {exc}") from exc


def snapshot_sha256(snapshot: Snapshot) -> str:
    """Return the SHA-256 digest of the RFC 8785 canonical snapshot."""
    return hashlib.sha256(canonical_snapshot_bytes(snapshot)).hexdigest()


def build_statement(snapshot: Snapshot) -> dict[str, object]:
    """Build the exact in-toto Statement v1 that binds one canonical baseline."""
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": "runtimetruth-baseline",
                "digest": {
                    "sha256": snapshot_sha256(snapshot),
                },
            }
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "attestation_schema_version": ATTESTATION_SCHEMA_VERSION,
            "snapshot_schema_version": snapshot.schema_version,
            "canonicalization": CANONICALIZATION,
        },
    }


def statement_bytes(snapshot: Snapshot) -> bytes:
    """Return RFC 8785 canonical bytes for the RuntimeTruth in-toto statement."""
    try:
        return rfc8785.dumps(build_statement(snapshot))
    except rfc8785.CanonicalizationError as exc:
        raise AttestationError(f"statement cannot be canonicalized with RFC 8785: {exc}") from exc


def _write(path: Path, payload: bytes) -> None:
    try:
        path.write_bytes(payload)
    except OSError as exc:
        raise AttestationError(f"could not write temporary attestation input: {exc}") from exc


def _resolve_cosign(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise AttestationError(
            f"cosign executable not found: {command!r}; install Sigstore cosign first"
        )
    return resolved


def _cosign_error(action: str, result: subprocess.CompletedProcess[str]) -> AttestationError:
    detail = (result.stderr or result.stdout or "").strip()
    if detail:
        detail = detail.splitlines()[-1]
        return AttestationError(
            f"cosign {action} failed with exit code {result.returncode}: {detail}"
        )
    return AttestationError(f"cosign {action} failed with exit code {result.returncode}")


def create_signed_attestation(
    baseline: Snapshot,
    *,
    bundle_path: str,
    cosign: str = "cosign",
) -> str:
    """Create a keyless DSSE/in-toto Sigstore attestation for one canonical baseline."""
    bundle = Path(bundle_path)
    if bundle.exists():
        raise AttestationError(f"refusing to overwrite existing file: {bundle_path!r}")

    executable = _resolve_cosign(cosign)

    with tempfile.TemporaryDirectory(prefix="runtimetruth-attest-") as directory:
        root = Path(directory)
        canonical = root / "runtimetruth-baseline.json"
        statement = root / "statement.json"
        _write(canonical, canonical_snapshot_bytes(baseline))
        _write(statement, statement_bytes(baseline))

        result = subprocess.run(
            [
                executable,
                "attest-blob",
                "--statement",
                str(statement),
                "--bundle",
                str(bundle),
                "--yes",
                str(canonical),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        bundle.unlink(missing_ok=True)
        raise _cosign_error("attest-blob", result)

    try:
        if bundle.stat().st_size == 0:
            raise AttestationError(f"cosign produced an empty bundle: {bundle_path!r}")
    except FileNotFoundError as exc:
        raise AttestationError(f"cosign did not produce bundle: {bundle_path!r}") from exc

    return snapshot_sha256(baseline)


def verify_signed_attestation(
    baseline: Snapshot,
    bundle_path: str,
    *,
    certificate_identity: str,
    certificate_oidc_issuer: str,
    cosign: str = "cosign",
) -> str:
    """Verify signer identity, in-toto subject digest, and RuntimeTruth predicate."""
    bundle = Path(bundle_path)
    if not bundle.is_file():
        raise AttestationError(f"Sigstore bundle does not exist: {bundle_path!r}")
    if not certificate_identity:
        raise AttestationError("certificate identity must not be empty")
    if not certificate_oidc_issuer:
        raise AttestationError("certificate OIDC issuer must not be empty")

    executable = _resolve_cosign(cosign)

    with tempfile.TemporaryDirectory(prefix="runtimetruth-verify-") as directory:
        canonical = Path(directory) / "runtimetruth-baseline.json"
        _write(canonical, canonical_snapshot_bytes(baseline))

        result = subprocess.run(
            [
                executable,
                "verify-blob-attestation",
                "--bundle",
                str(bundle),
                "--certificate-identity",
                certificate_identity,
                "--certificate-oidc-issuer",
                certificate_oidc_issuer,
                "--type",
                PREDICATE_TYPE,
                str(canonical),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        raise _cosign_error("verify-blob-attestation", result)

    statement = load_bundle_statement(bundle_path)
    return validate_statement(statement, baseline)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AttestationError(f"duplicate JSON object key in attestation: {key!r}")
        result[key] = value
    return result


def _decode_json(payload: bytes, *, field: str) -> object:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AttestationError(f"{field} must be UTF-8 JSON") from exc

    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise AttestationError(f"invalid {field} JSON: {exc.msg}") from exc


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AttestationError(f"{field} must be an object")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise AttestationError(f"{field} must be a string")
    return value


def load_bundle_statement(bundle_path: str) -> dict[str, object]:
    """Extract the signed in-toto statement from a Sigstore DSSE bundle."""
    try:
        bundle_bytes = Path(bundle_path).read_bytes()
    except OSError as exc:
        raise AttestationError(f"could not read Sigstore bundle {bundle_path!r}: {exc}") from exc

    bundle = _object(_decode_json(bundle_bytes, field="Sigstore bundle"), field="Sigstore bundle")
    envelope = _object(bundle.get("dsseEnvelope"), field="Sigstore bundle.dsseEnvelope")

    payload_type = _string(
        envelope.get("payloadType"),
        field="Sigstore bundle.dsseEnvelope.payloadType",
    )
    if payload_type != _DSSE_PAYLOAD_TYPE:
        raise AttestationError(f"unsupported DSSE payload type: {payload_type!r}")

    encoded = _string(
        envelope.get("payload"),
        field="Sigstore bundle.dsseEnvelope.payload",
    )
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise AttestationError("Sigstore DSSE payload is not valid base64") from exc

    return _object(_decode_json(payload, field="in-toto statement"), field="in-toto statement")


def validate_statement(statement: dict[str, object], baseline: Snapshot) -> str:
    """Validate the signed RuntimeTruth statement against the supplied baseline."""
    expected_root_keys = {"_type", "subject", "predicateType", "predicate"}
    if set(statement) != expected_root_keys:
        raise AttestationError("attestation root fields do not match RuntimeTruth schema v1")

    if statement.get("_type") != STATEMENT_TYPE:
        raise AttestationError(f"unsupported in-toto statement type: {statement.get('_type')!r}")

    if statement.get("predicateType") != PREDICATE_TYPE:
        raise AttestationError(
            f"unsupported RuntimeTruth predicate type: {statement.get('predicateType')!r}"
        )

    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1:
        raise AttestationError("attestation subject must contain exactly one baseline")

    subject = _object(subjects[0], field="subject[0]")
    if set(subject) != {"name", "digest"}:
        raise AttestationError("attestation subject fields do not match RuntimeTruth schema v1")

    digest = _object(subject.get("digest"), field="subject[0].digest")
    if set(digest) != {"sha256"}:
        raise AttestationError("attestation subject digest must contain only sha256")
    attested_digest = _string(digest.get("sha256"), field="subject[0].digest.sha256")

    expected_digest = snapshot_sha256(baseline)
    if attested_digest != expected_digest:
        raise AttestationError(
            "attested baseline digest does not match the supplied canonical baseline"
        )

    predicate = _object(statement.get("predicate"), field="predicate")
    expected_predicate_keys = {
        "attestation_schema_version",
        "snapshot_schema_version",
        "canonicalization",
    }
    if set(predicate) != expected_predicate_keys:
        raise AttestationError("attestation predicate fields do not match RuntimeTruth schema v1")
    if predicate.get("attestation_schema_version") != ATTESTATION_SCHEMA_VERSION:
        raise AttestationError(
            f"unsupported attestation schema version: "
            f"{predicate.get('attestation_schema_version')!r}"
        )
    if predicate.get("snapshot_schema_version") != baseline.schema_version:
        raise AttestationError("attestation snapshot schema version does not match baseline")
    if predicate.get("canonicalization") != CANONICALIZATION:
        raise AttestationError(
            f"unsupported attestation canonicalization: {predicate.get('canonicalization')!r}"
        )

    return expected_digest
