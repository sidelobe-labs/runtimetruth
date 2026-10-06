"""Evidence collection for local Git repository identity."""

from __future__ import annotations

import subprocess
from pathlib import Path

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.model import EvidenceRecord, EvidenceSource


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
        )
    except FileNotFoundError as exc:
        raise CollectionError("git is not available on this host") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectionError("git timed out while inspecting the repository") from exc

    if completed.returncode not in allowed_returncodes:
        raise CollectionError(
            f"git command failed with exit status {completed.returncode}"
        )

    return completed


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
    )
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
