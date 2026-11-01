from pathlib import Path

import pytest

from runtimetruth import cli
from runtimetruth.attestation import AttestationError

_BASELINE = str(Path(__file__).parent / "fixtures" / "snapshots" / "before.json")
_SIGNED_OPTIONS = [
    "--statement",
    "baseline.intoto.json",
    "--bundle",
    "baseline.sigstore.json",
    "--certificate-identity",
    "signer@example.com",
    "--certificate-oidc-issuer",
    "https://issuer.example",
]


@pytest.mark.parametrize("content", [b"\xff", b'{"truncated":"\xc3'])
@pytest.mark.parametrize("command", ["verify", "diff", "digest"])
def test_invalid_utf8_snapshot_is_a_cli_error(tmp_path, capsys, content, command):
    path = tmp_path / "invalid.json"
    path.write_bytes(content)
    args = [command, str(path)]
    if command != "digest":
        args.append(_BASELINE)

    assert cli.main(args) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "must be UTF-8 JSON" in captured.err


@pytest.mark.parametrize("signed", [False, True])
def test_invalid_utf8_policy_is_a_cli_error(tmp_path, monkeypatch, capsys, signed):
    path = tmp_path / "invalid.toml"
    path.write_bytes(b'version = 1\nprotect = ["\xff"]\n')
    calls = []

    def verify_trust(*args, **kwargs):
        calls.append("trust")
        return "f" * 64

    monkeypatch.setattr(cli, "verify_signed_attestation", verify_trust)
    args = ["verify-attestation" if signed else "verify", _BASELINE, _BASELINE]
    if signed:
        args.extend(_SIGNED_OPTIONS)
    args.extend(["--policy", str(path), "--json"])

    assert cli.main(args) == 1
    assert calls == (["trust"] if signed else [])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "must be UTF-8 TOML" in captured.err


@pytest.mark.parametrize("invalid_baseline", [False, True])
def test_signed_snapshot_decode_errors_respect_trust_order(
    tmp_path,
    monkeypatch,
    capsys,
    invalid_baseline,
):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff")
    calls = []

    def verify_trust(*args, **kwargs):
        calls.append("trust")
        return "f" * 64

    monkeypatch.setattr(cli, "verify_signed_attestation", verify_trust)
    baseline, current = (str(path), _BASELINE) if invalid_baseline else (_BASELINE, str(path))
    assert cli.main(["verify-attestation", baseline, current, *_SIGNED_OPTIONS, "--json"]) == 1

    assert calls == ([] if invalid_baseline else ["trust"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "must be UTF-8 JSON" in captured.err


def test_invalid_utf8_policy_cannot_precede_failed_baseline_authentication(
    tmp_path,
    monkeypatch,
    capsys,
):
    path = tmp_path / "invalid.toml"
    path.write_bytes(b"\xff")

    def fail_trust(*args, **kwargs):
        raise AttestationError("identity mismatch")

    monkeypatch.setattr(cli, "verify_signed_attestation", fail_trust)
    assert (
        cli.main(
            [
                "verify-attestation",
                _BASELINE,
                _BASELINE,
                *_SIGNED_OPTIONS,
                "--policy",
                str(path),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "identity mismatch" in captured.err
    assert "UTF-8" not in captured.err
