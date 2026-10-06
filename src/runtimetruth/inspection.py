"""Composition of independent runtime evidence collectors."""

from __future__ import annotations

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.collectors.git import NotRepositoryError, collect_git_repository
from runtimetruth.collectors.process import collect_linux_process
from runtimetruth.collectors.systemd import collect_systemd_unit
from runtimetruth.model import EvidenceRecord


def inspect_systemd_runtime(unit: str) -> tuple[EvidenceRecord, ...]:
    """Resolve a systemd unit into service, process, and local code evidence."""
    service = collect_systemd_unit(unit)
    records = [service]

    main_pid = service.data.get("main_pid")
    if not isinstance(main_pid, int):
        raise CollectionError("systemd MainPID has an invalid type")
    if main_pid == 0:
        return tuple(records)

    process = collect_linux_process(main_pid)
    records.append(process)

    cwd = process.data.get("cwd")
    if not isinstance(cwd, str):
        raise CollectionError("process cwd has an invalid type")

    try:
        repository = collect_git_repository(cwd)
    except NotRepositoryError:
        return tuple(records)

    records.append(repository)
    return tuple(records)
