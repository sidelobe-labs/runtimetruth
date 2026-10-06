import json
import subprocess
from pathlib import Path

import pytest
import rfc8785

from runtimetruth.attestation import (
    ATTESTATION_SCHEMA_VERSION,
    CANONICALIZATION,
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    SUBJECT_NAME,
    AttestationError,
    build_statement,
    canonical_snapshot_bytes,
    create_signed_attestation,
    load_statement,
    sign_statement,
    snapshot_sha256,
    statement_bytes,
    validate_statement,
    verify_statement_signature,
)
from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target


def _snapshot(*, head: str = "a" * 40) -> Snapshot:
    return Snapshot(
        schema_version=1,
        captured_at="2026-10-06T12:00:00Z",
        target=Target(kind="git.repository", identifier="/srv/agent"),
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="git.repository",
                source=EvidenceSource(
                    collector="git",
                    method="git rev-parse/status",
                ),
                data={
                    "branch": "main",
                    "head_commit": head,
                    "dirty": False,
                },
            ),
        ),
    )


def test_canonical_snapshot_bytes_use_rfc8785() -> None:
    snapshot = _snapshot()

    assert canonical_snapshot_bytes(snapshot) == rfc8785.dumps(snapshot.to_dict())


def test_canonical_digest_is_independent_of_json_whitespace_and_object_key_order() -> None:
    snapshot = _snapshot()
    decoded = snapshot.to_dict()

    payload = json.dumps(
        {
            "evidence": decoded["evidence"],
            "target": decoded["target"],
            "captured_at": decoded["captured_at"],
            "schema_version": decoded["schema_version"],
        },
        indent=4,
    )
    reparsed = Snapshot.from_json(payload)

    assert snapshot_sha256(reparsed) == snapshot_sha256(snapshot)


def test_canonical_digest_changes_when_baseline_changes() -> None:
    assert snapshot_sha256(_snapshot()) != snapshot_sha256(_snapshot(head="b" * 40))


def test_statement_is_minimal_in_toto_v1_binding() -> None:
    snapshot = _snapshot()
    digest = snapshot_sha256(snapshot)

    assert build_statement(snapshot) == {
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
            "snapshot_schema_version": 1,
            "canonicalization": CANONICALIZATION,
        },
    }
    assert statement_bytes(snapshot) == rfc8785.dumps(build_statement(snapshot))


def test_validate_statement_accepts_exact_baseline_binding() -> None:
    snapshot = _snapshot()

    assert validate_statement(build_statement(snapshot), snapshot) == snapshot_sha256(snapshot)


def test_validate_statement_rejects_different_baseline_digest() -> None:
    statement = build_statement(_snapshot())

    with pytest.raises(AttestationError, match="does not match"):
        validate_statement(statement, _snapshot(head="b" * 40))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda statement: statement.update({"extra": True}),
        lambda statement: statement["predicate"].update({"extra": True}),
        lambda statement: statement.update({"_type": "https://example.invalid/Statement/v1"}),
        lambda statement: statement.update({"predicateType": "https://example.invalid/predicate"}),
        lambda statement: statement["subject"][0].update({"name": "other"}),
        lambda statement: statement["subject"][0]["digest"].update({"sha512": "00"}),
        lambda statement: statement["predicate"].update({"canonicalization": "custom"}),
    ],
)
def test_validate_statement_rejects_schema_or_trust_mutations(mutation) -> None:
    snapshot = _snapshot()
    statement = build_statement(snapshot)
    mutation(statement)

    with pytest.raises(AttestationError):
        validate_statement(statement, snapshot)


def test_load_statement_rejects_duplicate_json_keys(tmp_path) -> None:
    path = tmp_path / "attestation.json"
    path.write_text(
        '{"_type":"a","_type":"b","subject":[],"predicateType":"x","predicate":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AttestationError, match="duplicate JSON object key"):
        load_statement(str(path))


def test_sign_statement_invokes_cosign_keyless_bundle(monkeypatch, tmp_path) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"
    statement.write_bytes(statement_bytes(_snapshot()))
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        bundle.write_text('{"bundle":"test"}', encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    sign_statement(str(statement), str(bundle))

    assert calls == [
        [
            "/usr/bin/cosign",
            "sign-blob",
            str(statement),
            "--bundle",
            str(bundle),
            "--yes",
        ]
    ]


def test_sign_statement_removes_partial_bundle_on_failure(monkeypatch, tmp_path) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"
    statement.write_bytes(statement_bytes(_snapshot()))

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        bundle.write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="signing failed",
        )

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    with pytest.raises(AttestationError, match="sign-blob failed"):
        sign_statement(str(statement), str(bundle))

    assert not bundle.exists()


def test_create_signed_attestation_cleans_statement_when_signing_fails(
    monkeypatch,
    tmp_path,
) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"

    def fail_sign(*args, **kwargs):
        raise AttestationError("no signer")

    monkeypatch.setattr("runtimetruth.attestation.sign_statement", fail_sign)

    with pytest.raises(AttestationError, match="no signer"):
        create_signed_attestation(
            _snapshot(),
            statement_path=str(statement),
            bundle_path=str(bundle),
        )

    assert not statement.exists()
    assert not bundle.exists()


def test_verify_statement_signature_requires_exact_identity(monkeypatch, tmp_path) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"
    statement.write_bytes(statement_bytes(_snapshot()))
    bundle.write_text('{"bundle":"test"}', encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    verify_statement_signature(
        str(statement),
        str(bundle),
        certificate_identity="https://github.com/sidelobe-labs/runtimetruth/.github/workflows/attest.yml@refs/heads/main",
        certificate_oidc_issuer="https://token.actions.githubusercontent.com",
    )

    assert calls == [
        [
            "/usr/bin/cosign",
            "verify-blob",
            str(statement),
            "--bundle",
            str(bundle),
            "--certificate-identity",
            "https://github.com/sidelobe-labs/runtimetruth/.github/workflows/attest.yml@refs/heads/main",
            "--certificate-oidc-issuer",
            "https://token.actions.githubusercontent.com",
        ]
    ]


def test_verify_statement_signature_propagates_cosign_failure(monkeypatch, tmp_path) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"
    statement.write_bytes(statement_bytes(_snapshot()))
    bundle.write_text('{"bundle":"test"}', encoding="utf-8")

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )
    monkeypatch.setattr(
        "runtimetruth.attestation.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="identity mismatch",
        ),
    )

    with pytest.raises(AttestationError, match="identity mismatch"):
        verify_statement_signature(
            str(statement),
            str(bundle),
            certificate_identity="expected",
            certificate_oidc_issuer="https://issuer.example",
        )


def test_cosign_missing_is_error(monkeypatch, tmp_path) -> None:
    statement = tmp_path / "statement.json"
    bundle = tmp_path / "bundle.sigstore.json"
    statement.write_bytes(statement_bytes(_snapshot()))

    monkeypatch.setattr("runtimetruth.attestation.shutil.which", lambda command: None)

    with pytest.raises(AttestationError, match="executable not found"):
        sign_statement(str(statement), str(bundle))
