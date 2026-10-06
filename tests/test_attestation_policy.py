import json
from pathlib import Path

from runtimetruth.cli import main

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def test_attestation_policy_controls_only_runtime_gate(monkeypatch, tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")
    policy = tmp_path / "policy.toml"
    policy.write_text('version = 1\nprotect = ["git.repository.branch"]\n', encoding="utf-8")
    calls: list[str] = []

    def verify_trust(*args, **kwargs):
        calls.append("trust")
        return "f" * 64

    monkeypatch.setattr("runtimetruth.cli.verify_signed_attestation", verify_trust)

    assert main([
        "verify-attestation", baseline, current,
        "--statement", "baseline.intoto.json",
        "--bundle", "baseline.sigstore.json",
        "--certificate-identity", "signer@example.com",
        "--certificate-oidc-issuer", "https://accounts.example.com",
        "--policy", str(policy),
    ]) == 0

    assert calls == ["trust"]
    assert capsys.readouterr().out.endswith("RUNTIME: PASS\n")


def test_attestation_policy_and_cli_protect_are_additive(monkeypatch, tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")
    policy = tmp_path / "policy.toml"
    policy.write_text('version = 1\nprotect = ["git.repository.branch"]\n', encoding="utf-8")
    monkeypatch.setattr(
        "runtimetruth.cli.verify_signed_attestation",
        lambda *args, **kwargs: "f" * 64,
    )

    assert main([
        "verify-attestation", baseline, current,
        "--statement", "baseline.intoto.json",
        "--bundle", "baseline.sigstore.json",
        "--certificate-identity", "signer@example.com",
        "--certificate-oidc-issuer", "https://accounts.example.com",
        "--policy", str(policy),
        "--protect", "git.repository.head_commit",
        "--json",
    ]) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["protected"] == [
        "git.repository.branch",
        "git.repository.head_commit",
    ]


def test_attestation_trust_failure_precedes_invalid_policy(monkeypatch, tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    policy = tmp_path / "policy.toml"
    policy.write_text("version = 1\nprotect = []\n", encoding="utf-8")

    def fail_identity(*args, **kwargs):
        from runtimetruth.attestation import AttestationError
        raise AttestationError("identity mismatch")

    monkeypatch.setattr("runtimetruth.cli.verify_signed_attestation", fail_identity)

    assert main([
        "verify-attestation", baseline, baseline,
        "--statement", "baseline.intoto.json",
        "--bundle", "baseline.sigstore.json",
        "--certificate-identity", "expected",
        "--certificate-oidc-issuer", "https://issuer.example",
        "--policy", str(policy),
    ]) == 1

    captured = capsys.readouterr()
    assert "identity mismatch" in captured.err
    assert "non-empty array" not in captured.err
