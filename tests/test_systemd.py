import subprocess
from pathlib import Path

import pytest

from runtimetruth.collectors import systemd

_FIXTURE = Path(__file__).parent / "fixtures" / "systemd" / "agent-worker.show"


def _fixture_text() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_parser_keeps_allowlisted_evidence_only() -> None:
    parsed = systemd.parse_systemctl_show(_fixture_text())

    assert parsed["unit_id"] == "sidelobe-agent.service"
    assert parsed["active_state"] == "active"
    assert parsed["main_pid"] == 4242
    assert parsed["restart_count"] == 1
    assert parsed["dynamic_user"] is False
    assert "environment" not in parsed
    assert all("SHOULD_NOT_BE_COLLECTED" not in str(value) for value in parsed.values())


def test_collector_requests_only_safe_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_command: list[str] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 5.0
        return subprocess.CompletedProcess(command, 0, stdout=_fixture_text(), stderr="")

    monkeypatch.setattr(systemd.subprocess, "run", fake_run)

    evidence = systemd.collect_systemd_unit("sidelobe-agent.service")

    property_argument = next(arg for arg in observed_command if arg.startswith("--property="))
    assert "Environment" not in property_argument
    assert "ExecStart" not in property_argument
    assert evidence.plane == "live"
    assert evidence.kind == "systemd.unit"
    assert evidence.source.collector == "systemd"


@pytest.mark.parametrize(
    "unit",
    [
        "",
        "-not-a-unit",
        "agent service",
        "../../agent.service",
    ],
)
def test_unit_validation_rejects_ambiguous_inputs(unit: str) -> None:
    with pytest.raises(ValueError):
        systemd.validate_systemd_unit_name(unit)


def test_collector_reports_nonzero_systemctl_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 4, stdout="", stderr="not found")

    monkeypatch.setattr(systemd.subprocess, "run", fake_run)

    with pytest.raises(systemd.CollectionError, match="exit status 4"):
        systemd.collect_systemd_unit("missing.service")
