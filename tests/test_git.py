import subprocess
from pathlib import Path

import pytest

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.collectors.git import collect_git_repository


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repo"
    repository.mkdir()

    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repository)],
        check=True,
    )
    _git(repository, "config", "user.name", "RuntimeTruth Tests")
    _git(repository, "config", "user.email", "tests@example.invalid")

    tracked = repository / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "initial")

    return repository, _git(repository, "rev-parse", "HEAD")


def test_collector_reports_commit_branch_and_clean_state(tmp_path: Path) -> None:
    repository, head_commit = _repository(tmp_path)

    evidence = collect_git_repository(str(repository))

    assert evidence.plane == "live"
    assert evidence.kind == "git.repository"
    assert evidence.source.collector == "git"
    assert evidence.data == {
        "repository_root": str(repository.resolve()),
        "head_commit": head_commit,
        "branch": "main",
        "detached": False,
        "dirty": False,
    }


def test_collector_detects_dirty_working_tree(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    (repository / "untracked.txt").write_text("local change\n", encoding="utf-8")

    evidence = collect_git_repository(str(repository))

    assert evidence.data["dirty"] is True


def test_collector_represents_detached_head(tmp_path: Path) -> None:
    repository, head_commit = _repository(tmp_path)
    _git(repository, "checkout", "-q", "--detach", head_commit)

    evidence = collect_git_repository(str(repository))

    assert evidence.data["head_commit"] == head_commit
    assert evidence.data["branch"] is None
    assert evidence.data["detached"] is True


def test_collector_rejects_non_repository_path(tmp_path: Path) -> None:
    directory = tmp_path / "plain"
    directory.mkdir()

    with pytest.raises(CollectionError, match="exit status"):
        collect_git_repository(str(directory))
