"""Evidence collection for local Git repository identity."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.model import EvidenceRecord, EvidenceSource


class NotRepositoryError(CollectionError):
    """Raised when a path is valid but is not inside a Git work tree."""


def _run_git(
    repository: Path,
    *arguments: str,
    timeout: float,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(repository), *arguments]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        raise CollectionError("git is not available on this host") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectionError("git timed out while inspecting the repository") from exc

    if completed.returncode not in allowed_returncodes:
        raise CollectionError(f"git command failed with exit status {completed.returncode}")

    return completed


def _git_ceiling_directories() -> set[str]:
    # Git leaves entries after the first empty ceiling entry as literal paths.
    ceilings: set[str] = set()
    resolve_symlinks = True
    for entry in os.environ.get("GIT_CEILING_DIRECTORIES", "").split(os.pathsep):
        if not entry:
            resolve_symlinks = False
        elif os.path.isabs(entry):
            if resolve_symlinks:
                try:
                    entry = str(Path(entry).resolve(strict=True))
                except (OSError, RuntimeError):
                    continue
            ceilings.add(entry.removesuffix("/") or "/")
    return ceilings


def _has_git_metadata(repository: Path, *, mount_stop: str | None = None) -> bool:
    if "GIT_DIR" in os.environ:
        return True
    ceilings = _git_ceiling_directories()
    # A broken marker can make Git report "not a git repository". Its presence
    # rules out absence; it does not establish a usable repository or its root.
    for directory in (repository, *repository.parents):
        if directory != repository and (str(directory) in ceilings or str(directory) == mount_stop):
            break
        try:
            (directory / ".git").lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CollectionError("could not inspect Git repository metadata") from exc
        return True
    return False


def _is_outside_worktree(repository: Path, stderr: str) -> bool:
    # Git uses exit 128 for both discovery failures and invalid repository state.
    # A no-repository diagnostic establishes absence only without Git metadata.
    diagnostic = stderr.splitlines()[0] if stderr else ""
    if diagnostic == "fatal: this operation must be run in a work tree":
        return True
    if diagnostic == "fatal: not a git repository (or any of the parent directories): .git":
        return not _has_git_metadata(repository)
    mount_prefix = "fatal: not a git repository (or any parent up to mount point "
    if diagnostic.startswith(mount_prefix) and diagnostic.endswith(")"):
        # Use Git's actual boundary, including its configured cross-filesystem
        # discovery behavior, rather than guessing from device IDs ourselves.
        mount_stop = diagnostic[len(mount_prefix) : -1]
        if mount_stop in {str(parent) for parent in repository.parents}:
            return not _has_git_metadata(repository, mount_stop=mount_stop)
    return False


def collect_git_repository(path: str, *, timeout: float = 5.0) -> EvidenceRecord:
    """Collect identity and working-tree state for one local Git repository."""
    requested_path = Path(path).expanduser()
    if not requested_path.exists():
        raise CollectionError(f"repository path does not exist: {path!r}")
    if not requested_path.is_dir():
        raise CollectionError(f"repository path is not a directory: {path!r}")

    resolved_path = requested_path.resolve()

    root_result = _run_git(
        resolved_path,
        "rev-parse",
        "--show-toplevel",
        timeout=timeout,
        allowed_returncodes=(0, 128),
    )
    if root_result.returncode == 128:
        if _is_outside_worktree(resolved_path, root_result.stderr):
            raise NotRepositoryError(f"path is not inside a Git work tree: {path!r}")
        raise CollectionError("git could not resolve the work tree root (exit status 128)")

    repository_root = Path(root_result.stdout.strip()).resolve()

    head_result = _run_git(
        repository_root,
        "rev-parse",
        "--verify",
        "HEAD",
        timeout=timeout,
    )
    head_commit = head_result.stdout.strip()
    if not head_commit:
        raise CollectionError("git repository has no HEAD commit")

    branch_result = _run_git(
        repository_root,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
        timeout=timeout,
        allowed_returncodes=(0, 1),
    )
    detached = branch_result.returncode == 1
    branch = None if detached else branch_result.stdout.strip()

    status_result = _run_git(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
        timeout=timeout,
    )

    return EvidenceRecord(
        plane="live",
        kind="git.repository",
        source=EvidenceSource(
            collector="git",
            method="git rev-parse/status",
        ),
        data={
            "repository_root": str(repository_root),
            "head_commit": head_commit,
            "branch": branch,
            "detached": detached,
            "dirty": bool(status_result.stdout),
        },
    )
