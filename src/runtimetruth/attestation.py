"""Canonical baseline hashing and Sigstore-backed attestation support."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import rfc8785

from runtimetruth.model import Snapshot

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://sidelobe.dev/runtimetruth/attestation/v1"
SUBJECT_NAME = "runtimetruth-baseline"
ATTESTATION_SCHEMA_VERSION = 1
CANONICALIZATION = "RFC8785"


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
    """Build the minimal in-toto Statement v1 that binds one baseline digest."""
    digest = snapshot_sha256(snapshot)
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": SUBJECT_NAME,
                "digest": {
                    "sha256": digest,
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
    """Return canonical RFC 8785 bytes for the RuntimeTruth in-toto statement."""
    try:
        return rfc8785.dumps(build_statement(snapshot))
    except rfc8785.CanonicalizationError as exc:
        raise AttestationError(f"attestation cannot be canonicalized with RFC 8785: {exc}") from exc


def _write_new(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise AttestationError(f"refusing to overwrite existing file: {str(path)!r}") from exc
    except OSError as exc:
        raise AttestationError(f"could not write {str(path)!r}: {exc.strerror}") from exc


def write_statement(snapshot: Snapshot, path: str) -> str:
    """Write one immutable canonical attestation statement and return its digest."""
    statement_path = Path(path)
    _write_new(statement_path, statement_bytes(snapshot))
    return snapshot_sha256(snapshot)


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


def sign_statement(
    statement_path: str,
    bundle_path: str,
    *,
    cosign: str = "cosign",
) -> None:
    """Keylessly sign one statement with cosign and write a Sigstore bundle."""
    statement = Path(statement_path)
    bundle = Path(bundle_path)

    if not statement.is_file():
        raise AttestationError(f"attestation statement does not exist: {statement_path!r}")
    if bundle.exists():
        raise AttestationError(f"refusing to overwrite existing file: {bundle_path!r}")

    executable = _resolve_cosign(cosign)
    result = subprocess.run(
        [
            executable,
            "sign-blob",
            str(statement),
            "--bundle",
            str(bundle),
            "--yes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        bundle.unlink(missing_ok=True)
        raise _cosign_error("sign-blob", result)

    try:
        if bundle.stat().st_size == 0:
            raise AttestationError(f"cosign produced an empty bundle: {bundle_path!r}")
    except FileNotFoundError as exc:
        raise AttestationError(f"cosign did not produce bundle: {bundle_path!r}") from exc


def create_signed_attestation(
    baseline: Snapshot,
    *,
    statement_path: str,
    bundle_path: str,
    cosign: str = "cosign",
) -> str:
    """Create a canonical statement, keylessly sign it, and return the baseline digest."""
    statement = Path(statement_path)
    bundle = Path(bundle_path)

    if statement.exists():
        raise AttestationError(f"refusing to overwrite existing file: {statement_path!r}")
    if bundle.exists():
        raise AttestationError(f"refusing to overwrite existing file: {bundle_path!r}")

    try:
        digest = write_statement(baseline, statement_path)
        sign_statement(statement_path, bundle_path, cosign=cosign)
    except Exception:
        statement.unlink(missing_ok=True)
        bundle.unlink(missing_ok=True)
        raise

    return digest


def verify_statement_signature(
    statement_path: str,
    bundle_path: str,
    *,
    certificate_identity: str,
    certificate_oidc_issuer: str,
    cosign: str = "cosign",
) -> None:
    """Verify a Sigstore bundle against one exact expected signing identity."""
    statement = Path(statement_path)
    bundle = Path(bundle_path)

    if not statement.is_file():
        raise AttestationError(f"attestation statement does not exist: {statement_path!r}")
    if not bundle.is_file():
        raise AttestationError(f"Sigstore bundle does not exist: {bundle_path!r}")
    if not certificate_identity:
        raise AttestationError("certificate identity must not be empty")
    if not certificate_oidc_issuer:
        raise AttestationError("certificate OIDC issuer must not be empty")

    executable = _resolve_cosign(cosign)
    result = subprocess.run(
        [
            executable,
            "verify-blob",
            str(statement),
            "--bundle",
            str(bundle),
            "--certificate-identity",
            certificate_identity,
            "--certificate-oidc-issuer",
            certificate_oidc_issuer,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise _cosign_error("verify-blob", result)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AttestationError(f"duplicate JSON object key in attestation: {key!r}")
        result[key] = value
    return result


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AttestationError(f"{field} must be an object")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise AttestationError(f"{field} must be a string")
    return value


def load_statement(path: str) -> dict[str, object]:
    """Load an attestation statement while rejecting duplicate JSON keys."""
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AttestationError(f"could not read attestation {path!r}: {exc.strerror}") from exc

    try:
        decoded = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise AttestationError(f"invalid attestation JSON {path!r}: {exc.msg}") from exc

    return _object(decoded, field="attestation")


def validate_statement(statement: dict[str, object], baseline: Snapshot) -> str:
    """Validate a signed RuntimeTruth statement against the supplied baseline."""
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
    if subject.get("name") != SUBJECT_NAME:
        raise AttestationError(f"unexpected attestation subject name: {subject.get('name')!r}")

    digest = _object(subject.get("digest"), field="subject[0].digest")
    if set(digest) != {"sha256"}:
        raise AttestationError("attestation subject digest must contain only sha256")
    attested_digest = _string(digest.get("sha256"), field="subject[0].digest.sha256")

    expected_digest = snapshot_sha256(baseline)
    if attested_digest != expected_digest:
        raise AttestationError(
            "attested baseline digest does not match the supplied baseline snapshot"
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
