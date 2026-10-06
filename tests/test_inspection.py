import subprocess
from pathlib import Path

from runtimetruth import inspection
from runtimetruth.model import EvidenceRecord, EvidenceSource


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "agent"
    repository.mkdir()

    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repository)],
        check=True,
    )
    _git(repository, "config", "user.name", "RuntimeTruth Tests")
    _git(repository, "config", "user.email", "tests@example.invalid")
    (repository / "agent.py").write_text("print('agent')\n", encoding="utf-8")
    _git(repository, "add", "agent.py")
    _git(repository, "commit", "-q", "-m", "initial")

    return repository


def _service(*, pid: int) -> EvidenceRecord:
    return EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(collector="systemd", method="systemctl show"),
        data={
            "unit_id": "agent.service",
            "main_pid": pid,
        },
    )


def _process(*, pid: int, cwd: Path) -> EvidenceRecord:
    return EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(collector="procfs", method="/proc/<pid>/{cwd,exe}"),
        data={
            "pid": pid,
            "cwd": str(cwd),
            "executable": "/usr/bin/python3",
        },
    )


def test_systemd_inspection_composes_process_and_git_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = _repository(tmp_path)
    monkeypatch.setattr(inspection, "collect_systemd_unit", lambda unit: _service(pid=4242))
    monkeypatch.setattr(
        inspection,
        "collect_linux_process",
        lambda pid: _process(pid=pid, cwd=repository),
    )

    evidence = inspection.inspect_systemd_runtime("agent.service")

    assert [record.kind for record in evidence] == [
        "systemd.unit",
        "linux.process",
        "git.repository",
    ]
    assert evidence[2].data["repository_root"] == str(repository.resolve())
    assert evidence[2].data["dirty"] is False


def test_systemd_inspection_keeps_non_git_process_valid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workdir = tmp_path / "plain"
    workdir.mkdir()
    monkeypatch.setattr(inspection, "collect_systemd_unit", lambda unit: _service(pid=4242))
    monkeypatch.setattr(
        inspection,
        "collect_linux_process",
        lambda pid: _process(pid=pid, cwd=workdir),
    )

    evidence = inspection.inspect_systemd_runtime("agent.service")

    assert [record.kind for record in evidence] == [
        "systemd.unit",
        "linux.process",
    ]


def test_systemd_inspection_accepts_unit_without_main_process(monkeypatch) -> None:
    monkeypatch.setattr(inspection, "collect_systemd_unit", lambda unit: _service(pid=0))

    evidence = inspection.inspect_systemd_runtime("agent.service")

    assert [record.kind for record in evidence] == ["systemd.unit"]
