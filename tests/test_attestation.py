import json
import subprocess

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
    verify_signed_attestation,
    verify_statement_signature,
    write_statement,
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


def test_statement_is_minimal_and_canonical() -> None:
    snapshot = _snapshot()

    statement = build_statement(snapshot)

    assert statement == {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": SUBJECT_NAME,
                "digest": {"sha256": snapshot_sha256(snapshot)},
            }
        ],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "attestation_schema_version": ATTESTATION_SCHEMA_VERSION,
            "snapshot_schema_version": 1,
            "canonicalization": CANONICALIZATION,
        },
    }
    assert statement_bytes(snapshot) == rfc8785.dumps(statement)


def test_write_and_load_statement_round_trip(tmp_path) -> None:
    snapshot = _snapshot()
    statement_path = tmp_path / "baseline.intoto.json"

    digest = write_statement(snapshot, str(statement_path))

    assert digest == snapshot_sha256(snapshot)
    assert statement_path.read_bytes() == statement_bytes(snapshot)
    assert load_statement(str(statement_path)) == build_statement(snapshot)


def test_write_statement_refuses_overwrite(tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    statement_path.write_text("existing", encoding="utf-8")

    with pytest.raises(AttestationError, match="refusing to overwrite"):
        write_statement(_snapshot(), str(statement_path))


def test_load_statement_rejects_noncanonical_json(tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    statement_path.write_text(
        json.dumps(build_statement(_snapshot()), indent=2),
        encoding="utf-8",
    )

    with pytest.raises(AttestationError, match="not RFC 8785 canonical JSON"):
        load_statement(str(statement_path))


def test_load_statement_rejects_duplicate_json_keys(tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    statement_path.write_text(
        '{"_type":"a","_type":"b","subject":[],"predicateType":"x","predicate":{}}',
        encoding="utf-8",
    )

    with pytest.raises(AttestationError, match="duplicate JSON object key"):
        load_statement(str(statement_path))


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


def test_sign_statement_uses_cosign_sign_blob(monkeypatch, tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"
    statement_path.write_bytes(statement_bytes(_snapshot()))
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        bundle_path.write_text('{"test":true}', encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    sign_statement(str(statement_path), str(bundle_path))

    assert calls == [
        [
            "/usr/bin/cosign",
            "sign-blob",
            str(statement_path),
            "--bundle",
            str(bundle_path),
            "--yes",
        ]
    ]
    assert bundle_path.is_file()


def test_create_signed_attestation_writes_statement_and_bundle(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = _snapshot()
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        assert args[0:2] == ["/usr/bin/cosign", "sign-blob"]
        assert statement_path.read_bytes() == statement_bytes(snapshot)
        bundle_path.write_text('{"test":true}', encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    digest = create_signed_attestation(
        snapshot,
        statement_path=str(statement_path),
        bundle_path=str(bundle_path),
    )

    assert digest == snapshot_sha256(snapshot)
    assert statement_path.read_bytes() == statement_bytes(snapshot)
    assert bundle_path.is_file()


def test_create_signed_attestation_removes_partial_outputs_on_failure(
    monkeypatch,
    tmp_path,
) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        bundle_path.write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="signing failed",
        )

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    with pytest.raises(AttestationError, match="sign-blob failed"):
        create_signed_attestation(
            _snapshot(),
            statement_path=str(statement_path),
            bundle_path=str(bundle_path),
        )

    assert not statement_path.exists()
    assert not bundle_path.exists()


def test_verify_statement_signature_pins_identity(monkeypatch, tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"
    statement_path.write_bytes(statement_bytes(_snapshot()))
    bundle_path.write_text('{"test":true}', encoding="utf-8")
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
        str(statement_path),
        str(bundle_path),
        certificate_identity=(
            "https://github.com/sidelobe-labs/runtimetruth/"
            ".github/workflows/attest.yml@refs/heads/main"
        ),
        certificate_oidc_issuer="https://token.actions.githubusercontent.com",
    )

    assert calls[0][0:3] == [
        "/usr/bin/cosign",
        "verify-blob",
        str(statement_path),
    ]
    assert calls[0][calls[0].index("--bundle") + 1] == str(bundle_path)
    assert calls[0][calls[0].index("--certificate-identity") + 1].startswith(
        "https://github.com/sidelobe-labs/runtimetruth/"
    )
    assert calls[0][calls[0].index("--certificate-oidc-issuer") + 1] == (
        "https://token.actions.githubusercontent.com"
    )


def test_verify_signed_attestation_checks_signature_before_baseline(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = _snapshot()
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"
    statement_path.write_bytes(statement_bytes(snapshot))
    bundle_path.write_text('{"test":true}', encoding="utf-8")
    events: list[str] = []

    monkeypatch.setattr(
        "runtimetruth.attestation.verify_statement_signature",
        lambda *args, **kwargs: events.append("signature"),
    )
    original_load = load_statement

    def observed_load(path):
        events.append("statement")
        return original_load(path)

    monkeypatch.setattr("runtimetruth.attestation.load_statement", observed_load)

    digest = verify_signed_attestation(
        snapshot,
        statement_path=str(statement_path),
        bundle_path=str(bundle_path),
        certificate_identity="expected",
        certificate_oidc_issuer="https://issuer.example",
    )

    assert digest == snapshot_sha256(snapshot)
    assert events == ["signature", "statement"]


def test_verify_signed_attestation_fails_closed_on_identity_error(
    monkeypatch,
    tmp_path,
) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"
    statement_path.write_bytes(statement_bytes(_snapshot()))
    bundle_path.write_text('{"test":true}', encoding="utf-8")

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
        verify_signed_attestation(
            _snapshot(),
            statement_path=str(statement_path),
            bundle_path=str(bundle_path),
            certificate_identity="expected",
            certificate_oidc_issuer="https://issuer.example",
        )


def test_cosign_missing_is_error(monkeypatch, tmp_path) -> None:
    statement_path = tmp_path / "baseline.intoto.json"
    bundle_path = tmp_path / "baseline.sigstore.json"
    statement_path.write_bytes(statement_bytes(_snapshot()))

    monkeypatch.setattr("runtimetruth.attestation.shutil.which", lambda command: None)

    with pytest.raises(AttestationError, match="executable not found"):
        sign_statement(str(statement_path), str(bundle_path))
