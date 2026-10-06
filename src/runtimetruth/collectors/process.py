"""Live Linux process evidence from procfs."""

from __future__ import annotations

import os
from pathlib import Path

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.model import EvidenceRecord, EvidenceSource


def _read_process_link(path: Path, *, pid: int, name: str) -> str:
    try:
        return os.readlink(path)
    except FileNotFoundError as exc:
        raise CollectionError(
            f"process {pid} disappeared while reading {name} from procfs"
        ) from exc
    except PermissionError as exc:
        raise CollectionError(
            f"permission denied while reading process {pid} {name} from procfs"
        ) from exc
    except OSError as exc:
        raise CollectionError(
            f"could not read process {pid} {name} from procfs: {exc.strerror}"
        ) from exc


def collect_linux_process(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
) -> EvidenceRecord:
    """Collect identity-safe facts for one live Linux process."""
    if pid <= 0:
        raise CollectionError(f"invalid process id: {pid}")

    process_root = proc_root / str(pid)
    cwd = _read_process_link(process_root / "cwd", pid=pid, name="cwd")
    executable = _read_process_link(process_root / "exe", pid=pid, name="executable")

    return EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(
            collector="procfs",
            method="/proc/<pid>/{cwd,exe}",
        ),
        data={
            "pid": pid,
            "cwd": cwd,
            "executable": executable,
        },
    )
