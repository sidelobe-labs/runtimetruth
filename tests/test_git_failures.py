import subprocess
from pathlib import Path

import pytest

from runtimetruth import inspection
from runtimetruth.collectors import git as git_collector
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


@pytest.mark.parametrize("head", [None, "not a valid ref\n"], ids=["missing", "malformed"])
@pytest.mark.parametrize("nested", [False, True], ids=["root", "nested"])
def test_broken_head_is_a_collection_failure(repository: Path, head, nested: bool) -> None:
    if head is None:
        (repository / ".git" / "HEAD").unlink()
    else:
        (repository / ".git" / "HEAD").write_text(head, encoding="utf-8")
    path = repository / "nested" / "directory" if nested else repository
    path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(path))

    assert not isinstance(caught.value, NotRepositoryError)


@pytest.mark.parametrize("damage", ["config", "missing-head", "malformed-head"])
def test_systemd_inspection_does_not_hide_a_broken_repository(
    repository: Path, monkeypatch, damage: str
) -> None:
    if damage == "config":
        (repository / ".git" / "config").write_text("[broken\n", encoding="utf-8")
    elif damage == "missing-head":
        (repository / ".git" / "HEAD").unlink()
    else:
        (repository / ".git" / "HEAD").write_text("not a valid ref\n", encoding="utf-8")
    cwd = repository / "service"
    cwd.mkdir()
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
        data={"pid": 4242, "cwd": str(cwd), "executable": "/usr/bin/python3"},
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


def test_dangling_git_marker_is_a_collection_failure(tmp_path: Path) -> None:
    (tmp_path / ".git").symlink_to(tmp_path / "missing")

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(tmp_path))

    assert not isinstance(caught.value, NotRepositoryError)


@pytest.mark.parametrize("git_dir", ["missing", ""])
def test_explicit_git_dir_failure_is_not_absence(tmp_path: Path, monkeypatch, git_dir: str) -> None:
    monkeypatch.setenv("GIT_DIR", git_dir)

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(tmp_path))

    assert not isinstance(caught.value, NotRepositoryError)


@pytest.mark.parametrize("ceiling", ["at-marker", "below-marker", "symlink"])
def test_git_ceiling_excludes_ancestor_metadata(
    repository: Path, tmp_path: Path, monkeypatch, ceiling: str
) -> None:
    (repository / ".git" / "HEAD").unlink()
    plain = repository / "nested" / "plain"
    plain.mkdir(parents=True)
    boundary = repository if ceiling == "at-marker" else plain.parent
    if ceiling == "symlink":
        link = tmp_path / "ceiling-link"
        link.symlink_to(boundary, target_is_directory=True)
        boundary = link
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(boundary))

    with pytest.raises(NotRepositoryError):
        collect_git_repository(str(plain))


def test_literal_ceiling_does_not_resolve_symlinks(
    repository: Path, tmp_path: Path, monkeypatch
) -> None:
    (repository / ".git" / "HEAD").unlink()
    plain = repository / "nested"
    plain.mkdir()
    link = tmp_path / "ceiling-link"
    link.symlink_to(repository, target_is_directory=True)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", f":{link}")

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(plain))

    assert not isinstance(caught.value, NotRepositoryError)


def test_git_ceiling_does_not_exclude_cwd_metadata(repository: Path, monkeypatch) -> None:
    (repository / ".git" / "HEAD").unlink()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(repository))

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(repository))

    assert not isinstance(caught.value, NotRepositoryError)


@pytest.mark.parametrize("marker_before_boundary", [False, True])
def test_mount_boundary_only_excludes_metadata_outside_discovery(
    repository: Path, tmp_path: Path, monkeypatch, marker_before_boundary: bool
) -> None:
    plain = repository / "nested"
    plain.mkdir()
    boundary = tmp_path if marker_before_boundary else repository
    stderr = (
        f"fatal: not a git repository (or any parent up to mount point {boundary})\n"
        "Stopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).\n"
    )
    monkeypatch.setattr(
        git_collector,
        "_run_git",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 128, "", stderr),
    )

    with pytest.raises(CollectionError) as caught:
        collect_git_repository(str(plain))

    assert isinstance(caught.value, NotRepositoryError) is not marker_before_boundary


def test_bare_repository_is_not_a_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "bare"
    _git("init", "-q", "--bare", str(repository))

    with pytest.raises(NotRepositoryError):
        collect_git_repository(str(repository))
