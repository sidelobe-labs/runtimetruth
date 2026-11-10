import os
import stat
from pathlib import Path

import pytest

from runtimetruth.cli import main
from runtimetruth.collectors.codex import collect_codex_runtime
from runtimetruth.collectors.errors import CollectionError

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


@pytest.mark.parametrize("executable", [False, True], ids=["permission", "interpreter"])
def test_codex_version_startup_failure_is_a_collection_error(
    tmp_path: Path, executable: bool
) -> None:
    binary = tmp_path / "codex"
    binary.write_text("#!/runtimetruth-missing-interpreter\n", encoding="utf-8")
    if executable:
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CollectionError, match="could not start codex --version"):
        collect_codex_runtime(str(tmp_path), codex_binary=str(binary))


@pytest.mark.parametrize("command", ["inspect", "verify"])
def test_codex_closed_stdin_returns_cli_error_and_stops_process(
    tmp_path: Path, monkeypatch, capsys, command: str
) -> None:
    binary = tmp_path / "codex"
    pid_path = tmp_path / "pid"
    binary.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys
import time

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.test")
    raise SystemExit(0)

with open({str(pid_path)!r}, "w", encoding="utf-8") as handle:
    handle.write(str(os.getpid()))

message = json.loads(sys.stdin.readline())
os.close(sys.stdin.fileno())
print(json.dumps({{"id": message["id"], "result": {{}}}}), flush=True)
time.sleep(60)
""",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])

    arguments = (
        ["inspect", "codex", str(tmp_path)]
        if command == "inspect"
        else ["verify", str(_FIXTURES / "before.json"), "--codex", str(tmp_path), "--json"]
    )
    assert main(arguments) == 1

    captured = capsys.readouterr()
    assert not captured.out
    assert "could not write to codex app-server" in captured.err
    assert "Traceback" not in captured.err
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text(encoding="utf-8")), 0)
