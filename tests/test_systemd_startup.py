from pathlib import Path

import pytest

from runtimetruth.cli import main
from runtimetruth.collectors.errors import CollectionError
from runtimetruth.collectors.systemd import collect_systemd_unit


@pytest.fixture(params=["permission", "format"])
def broken_systemctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request) -> None:
    executable = tmp_path / "systemctl"
    executable.write_text("invalid executable\n", encoding="utf-8")
    executable.chmod(0o644 if request.param == "permission" else 0o755)
    monkeypatch.setenv("PATH", str(tmp_path))


def test_systemctl_start_failure_is_a_collection_error(broken_systemctl) -> None:
    with pytest.raises(CollectionError, match="could not start systemctl"):
        collect_systemd_unit("agent.service")


def test_systemctl_start_failure_uses_cli_error_output(broken_systemctl, capsys) -> None:
    assert main(["inspect", "systemd", "agent.service"]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("runtimetruth: error: could not start systemctl:")
