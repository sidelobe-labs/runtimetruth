import base64
import json
import subprocess

import pytest
import rfc8785

from runtimetruth.attestation import (
    ATTESTATION_SCHEMA_VERSION,
    CANONICALIZATION,
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    AttestationError,
    build_statement,
    canonical_snapshot_bytes,
    create_signed_attestation,
    load_bundle_statement,
    snapshot_sha256,
    statement_bytes,
    validate_statement,
    verify_signed_attestation,
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


def _statement(snapshot: Snapshot) -> dict[str, object]:
    return build_statement(snapshot)


def _write_bundle(path, statement: dict[str, object]) -> None:
    payload = json.dumps(statement, separators=(",", ":"), sort_keys=True).encode()
    path.write_text(
        json.dumps(
            {
                "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                "dsseEnvelope": {
                    "payload": base64.b64encode(payload).decode(),
                    "payloadType": "application/vnd.in-toto+json",
                    "signatures": [{"sig": "test"}],
                },
                "verificationMaterial": {},
            }
        ),
        encoding="utf-8",
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
    assert statement["_type"] == STATEMENT_TYPE
    assert statement["predicateType"] == PREDICATE_TYPE
    assert statement["subject"] == [
        {
            "name": "runtimetruth-baseline",
            "digest": {"sha256": snapshot_sha256(snapshot)},
        }
    ]
    assert statement["predicate"] == {
        "attestation_schema_version": ATTESTATION_SCHEMA_VERSION,
        "snapshot_schema_version": 1,
        "canonicalization": CANONICALIZATION,
    }
    assert statement_bytes(snapshot) == rfc8785.dumps(statement)


def test_validate_statement_accepts_exact_baseline_binding() -> None:
    snapshot = _snapshot()

    assert validate_statement(_statement(snapshot), snapshot) == snapshot_sha256(snapshot)


def test_validate_statement_rejects_different_baseline_digest() -> None:
    statement = _statement(_snapshot())

    with pytest.raises(AttestationError, match="does not match"):
        validate_statement(statement, _snapshot(head="b" * 40))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda statement: statement.update({"extra": True}),
        lambda statement: statement["predicate"].update({"extra": True}),
        lambda statement: statement.update({"_type": "https://example.invalid/Statement/v1"}),
        lambda statement: statement.update({"predicateType": "https://example.invalid/predicate"}),
        lambda statement: statement["subject"][0]["digest"].update({"sha512": "00"}),
        lambda statement: statement["predicate"].update({"canonicalization": "custom"}),
    ],
)
def test_validate_statement_rejects_schema_or_trust_mutations(mutation) -> None:
    snapshot = _snapshot()
    statement = _statement(snapshot)
    mutation(statement)

    with pytest.raises(AttestationError):
        validate_statement(statement, snapshot)


def test_load_bundle_statement_decodes_dsse_payload(tmp_path) -> None:
    bundle = tmp_path / "bundle.sigstore.json"
    statement = _statement(_snapshot())
    _write_bundle(bundle, statement)

    assert load_bundle_statement(str(bundle)) == statement


def test_load_bundle_statement_rejects_duplicate_json_keys(tmp_path) -> None:
    bundle = tmp_path / "bundle.sigstore.json"
    bundle.write_text(
        '{"dsseEnvelope":{"payload":"e30=","payload":"e30=","payloadType":"application/vnd.in-toto+json"}}',
        encoding="utf-8",
    )

    with pytest.raises(AttestationError, match="duplicate JSON object key"):
        load_bundle_statement(str(bundle))


def test_load_bundle_statement_rejects_wrong_payload_type(tmp_path) -> None:
    bundle = tmp_path / "bundle.sigstore.json"
    bundle.write_text(
        json.dumps(
            {
                "dsseEnvelope": {
                    "payload": base64.b64encode(b"{}").decode(),
                    "payloadType": "application/json",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AttestationError, match="payload type"):
        load_bundle_statement(str(bundle))


def test_create_signed_attestation_uses_native_cosign_attest_blob(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = _snapshot()
    bundle = tmp_path / "bundle.sigstore.json"
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        canonical_path = args[-1]
        statement_path = args[args.index("--statement") + 1]

        assert open(canonical_path, "rb").read() == canonical_snapshot_bytes(snapshot)
        assert open(statement_path, "rb").read() == statement_bytes(snapshot)

        _write_bundle(bundle, _statement(snapshot))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    digest = create_signed_attestation(
        snapshot,
        bundle_path=str(bundle),
    )

    assert digest == snapshot_sha256(snapshot)
    assert calls[0][0:2] == ["/usr/bin/cosign", "attest-blob"]
    assert calls[0][calls[0].index("--statement") + 1].endswith("statement.json")
    assert calls[0][calls[0].index("--bundle") + 1] == str(bundle)
    assert "--yes" in calls[0]


def test_create_signed_attestation_removes_partial_bundle_on_failure(
    monkeypatch,
    tmp_path,
) -> None:
    bundle = tmp_path / "bundle.sigstore.json"

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
            stderr="attestation failed",
        )

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    with pytest.raises(AttestationError, match="attest-blob failed"):
        create_signed_attestation(_snapshot(), bundle_path=str(bundle))

    assert not bundle.exists()


def test_verify_signed_attestation_checks_identity_digest_and_predicate(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = _snapshot()
    bundle = tmp_path / "bundle.sigstore.json"
    _write_bundle(bundle, _statement(snapshot))
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "runtimetruth.attestation._resolve_cosign",
        lambda command: "/usr/bin/cosign",
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        canonical_path = args[-1]
        assert open(canonical_path, "rb").read() == canonical_snapshot_bytes(snapshot)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("runtimetruth.attestation.subprocess.run", fake_run)

    digest = verify_signed_attestation(
        snapshot,
        str(bundle),
        certificate_identity=(
            "https://github.com/sidelobe-labs/runtimetruth/"
            ".github/workflows/attest.yml@refs/heads/main"
        ),
        certificate_oidc_issuer="https://token.actions.githubusercontent.com",
    )

    assert digest == snapshot_sha256(snapshot)
    assert calls[0][0:2] == ["/usr/bin/cosign", "verify-blob-attestation"]
    assert calls[0][calls[0].index("--type") + 1] == PREDICATE_TYPE
    assert calls[0][calls[0].index("--certificate-identity") + 1].startswith(
        "https://github.com/sidelobe-labs/runtimetruth/"
    )
    assert calls[0][calls[0].index("--certificate-oidc-issuer") + 1] == (
        "https://token.actions.githubusercontent.com"
    )


def test_verify_signed_attestation_fails_closed_on_identity_error(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot = _snapshot()
    bundle = tmp_path / "bundle.sigstore.json"
    _write_bundle(bundle, _statement(snapshot))

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
            snapshot,
            str(bundle),
            certificate_identity="expected",
            certificate_oidc_issuer="https://issuer.example",
        )


def test_cosign_missing_is_error(monkeypatch, tmp_path) -> None:
    bundle = tmp_path / "bundle.sigstore.json"
    monkeypatch.setattr("runtimetruth.attestation.shutil.which", lambda command: None)

    with pytest.raises(AttestationError, match="executable not found"):
        create_signed_attestation(_snapshot(), bundle_path=str(bundle))
