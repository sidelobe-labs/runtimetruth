from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from runtimetruth import cli
from runtimetruth.attestation import AttestationError
from runtimetruth.cli import main
from runtimetruth.diff import load_snapshot

_FIXTURE = Path(__file__).parent / "fixtures" / "snapshots" / "before.json"
_NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW.astimezone(tz)

    monkeypatch.setattr(cli, "datetime", Clock)


@pytest.fixture(params=["verify", "verify-attestation"])
def verification(request, monkeypatch):
    if request.param == "verify":
        return ["verify"]
    monkeypatch.setattr(cli, "verify_signed_attestation", lambda *args, **kwargs: "f" * 64)
    return [
        "verify-attestation",
        "--statement",
        "baseline.intoto.json",
        "--bundle",
        "baseline.sigstore.json",
        "--certificate-identity",
        "signer@example.com",
        "--certificate-oidc-issuer",
        "https://issuer.example",
    ]


def write_current(tmp_path, timestamp):
    snapshot = replace(load_snapshot(str(_FIXTURE)), captured_at=timestamp)
    path = tmp_path / "current.json"
    path.write_text(snapshot.to_json(), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-11-01T12:00:00Z",
        "2026-11-01T11:59:00Z",
        "2026-11-01T13:59:00+02:00",
        "2026-11-01T06:29:00-05:30",
    ],
)
def test_fresh_current_can_match_historical_baseline(verification, timestamp, tmp_path, capsys):
    current = write_current(tmp_path, timestamp)
    assert main([*verification, str(_FIXTURE), current, "--max-age", "60"]) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize(
    ("timestamp", "error"),
    [
        ("2026-11-01T11:58:59.999999Z", "older than"),
        ("2025-11-01T12:00:00Z", "older than"),
        ("2026-11-01T12:00:00.000001Z", "in the future"),
        ("2027-11-01T12:00:00Z", "in the future"),
    ],
)
def test_unusable_current_cannot_pass(
    verification, timestamp, error, json_output, tmp_path, capsys
):
    current = write_current(tmp_path, timestamp)
    args = [*verification, str(_FIXTURE), current, "--max-age", "60", "--protect", "git.repository"]
    if json_output:
        args.append("--json")
    assert main(args) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert error in output.err


def test_default_still_allows_historical_comparison(verification, capsys):
    assert main([*verification, str(_FIXTURE), str(_FIXTURE)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_age_limit_keeps_microsecond_precision_for_old_observations(verification, tmp_path, capsys):
    oldest = datetime(1, 1, 1, 0, 0, 0, 1, tzinfo=UTC)
    current = write_current(tmp_path, oldest.isoformat())
    # An age ending in .999999 must remain older than its whole-second floor.
    duration = _NOW - oldest
    whole_seconds = duration.days * 86400 + duration.seconds
    assert main([*verification, str(_FIXTURE), current, "--max-age", str(whole_seconds)]) == 1
    assert "older than" in capsys.readouterr().err


def test_large_age_limit_does_not_overflow(verification, capsys):
    assert main([*verification, str(_FIXTURE), str(_FIXTURE), "--max-age", str(10**30)]) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.parametrize("timestamp", ["invalid", "2026-11-01T12:00:00"])
def test_invalid_current_timestamp_is_error(verification, timestamp, tmp_path, capsys):
    current = write_current(tmp_path, timestamp)
    assert main([*verification, str(_FIXTURE), current, "--max-age", "60"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "timezone-aware ISO 8601" in output.err


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "1.5"])
def test_max_age_requires_positive_whole_seconds(verification, value, capsys):
    with pytest.raises(SystemExit) as exc:
        main([*verification, str(_FIXTURE), str(_FIXTURE), "--max-age", value])
    assert exc.value.code == 2
    assert "positive integer" in capsys.readouterr().err


def test_signed_trust_failure_precedes_current_collection(monkeypatch, capsys):
    def fail_trust(*args, **kwargs):
        raise AttestationError("identity mismatch")

    def unexpected_capture(*args, **kwargs):
        pytest.fail("must authenticate the baseline before collecting current evidence")

    monkeypatch.setattr(cli, "verify_signed_attestation", fail_trust)
    monkeypatch.setattr(cli, "_capture_codex_snapshot", unexpected_capture)
    assert (
        main(
            [
                "verify-attestation",
                str(_FIXTURE),
                "--codex",
                ".",
                "--max-age",
                "60",
                "--statement",
                "baseline.intoto.json",
                "--bundle",
                "baseline.sigstore.json",
                "--certificate-identity",
                "signer@example.com",
                "--certificate-oidc-issuer",
                "https://issuer.example",
            ]
        )
        == 1
    )
    assert "identity mismatch" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("timestamp", "exit_code"),
    [
        ("2026-11-01T12:00:00Z", 0),
        ("2026-11-01T11:58:00Z", 1),
    ],
)
def test_live_capture_uses_same_age_gate(verification, timestamp, exit_code, monkeypatch, capsys):
    current = replace(load_snapshot(str(_FIXTURE)), captured_at=timestamp)
    monkeypatch.setattr(cli, "_capture_codex_snapshot", lambda *args, **kwargs: current)
    assert main([*verification, str(_FIXTURE), "--codex", ".", "--max-age", "60"]) == exit_code
    if exit_code:
        assert capsys.readouterr().out == ""
