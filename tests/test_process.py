import os
from pathlib import Path

import pytest

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.collectors.process import collect_linux_process


def test_collector_reads_cwd_and_executable_from_procfs(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    process_root = proc_root / "4242"
    process_root.mkdir(parents=True)

    cwd = tmp_path / "work"
    cwd.mkdir()
    executable = tmp_path / "python"
    executable.write_text("", encoding="utf-8")

    os.symlink(cwd, process_root / "cwd")
    os.symlink(executable, process_root / "exe")

    evidence = collect_linux_process(4242, proc_root=proc_root)

    assert evidence.plane == "live"
    assert evidence.kind == "linux.process"
    assert evidence.source.collector == "procfs"
    assert evidence.data == {
        "pid": 4242,
        "cwd": str(cwd),
        "executable": str(executable),
    }


def test_collector_reports_process_disappearance(tmp_path: Path) -> None:
    with pytest.raises(CollectionError, match="disappeared"):
        collect_linux_process(4242, proc_root=tmp_path / "proc")
