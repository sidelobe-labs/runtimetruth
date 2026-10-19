import subprocess
from pathlib import Path

import pytest

from runtimetruth import inspection
from runtimetruth.collectors.errors import CollectionError
from runtimetruth.collectors.git import NotRepositoryError, collect_git_repository
from runtimetruth.model import EvidenceRecord, EvidenceSource


def _git(*arguments: str) -> str:
    result = subprocess.run(["git", *arguments], check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    _git("init", "-q", "-b", "main", str(path))
    _git(
        "-C",
        str(path),
        "-c",
        "user.name=RuntimeTruth Tests",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "initial",
    )
    return path


def test_invalid_git_config_is_a_collection_failure(repository: Path) -> None:
    (repository / ".git" / "config").write_text("[broken\n", encoding="utf-8")

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(repository))

    assert not isinstance(caught.value, NotRepositoryError)


def test_systemd_inspection_does_not_hide_a_broken_repository(
    repository: Path, monkeypatch
) -> None:
    (repository / ".git" / "config").write_text("[broken\n", encoding="utf-8")
    service = EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(collector="systemd", method="systemctl show"),
        data={"unit_id": "agent.service", "main_pid": 4242},
    )
    process = EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(collector="procfs", method="/proc/<pid>/{cwd,exe}"),
        data={"pid": 4242, "cwd": str(repository), "executable": "/usr/bin/python3"},
    )
    monkeypatch.setattr(inspection, "collect_systemd_unit", lambda unit: service)
    monkeypatch.setattr(inspection, "collect_linux_process", lambda pid: process)

    with pytest.raises(CollectionError):
        inspection.inspect_systemd_runtime("agent.service")


def test_broken_global_config_does_not_look_like_a_non_repository(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "gitconfig"
    config.write_text("[broken\n", encoding="utf-8")
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(plain))

    assert not isinstance(caught.value, NotRepositoryError)


def test_linked_worktree_remains_inspectable(repository: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "linked"
    _git("-C", str(repository), "worktree", "add", "--detach", str(worktree), "HEAD")

    evidence = collect_git_repository(str(worktree))

    assert evidence.data["repository_root"] == str(worktree.resolve())
    assert evidence.data["head_commit"] == _git("-C", str(repository), "rev-parse", "HEAD")
    assert evidence.data["detached"] is True
    assert evidence.data["dirty"] is False


def test_broken_worktree_gitfile_is_a_collection_failure(repository: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "linked"
    _git("-C", str(repository), "worktree", "add", "--detach", str(worktree), "HEAD")
    (worktree / ".git").write_text("gitdir: missing\n", encoding="utf-8")

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(worktree))

    assert not isinstance(caught.value, NotRepositoryError)


def test_bare_repository_is_not_a_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "bare"
    _git("init", "-q", "--bare", str(repository))

    with pytest.raises(NotRepositoryError):
        collect_git_repository(str(repository))
