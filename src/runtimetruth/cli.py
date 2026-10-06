"""RuntimeTruth command-line entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from runtimetruth import __version__
from runtimetruth.collectors import (
    CollectionError,
    collect_codex_runtime,
    collect_git_repository,
)
from runtimetruth.collectors.systemd import validate_systemd_unit_name
from runtimetruth.diff import DiffError, diff_snapshots, format_diff, load_snapshot
from runtimetruth.inspection import inspect_systemd_runtime
from runtimetruth.model import Snapshot, Target

_VERIFY_DRIFT_EXIT = 2


def _systemd_unit(value: str) -> str:
    try:
        return validate_systemd_unit_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _inspect_systemd(args: argparse.Namespace) -> int:
    evidence = inspect_systemd_runtime(args.unit)
    service = evidence[0]
    resolved_unit = service.data["unit_id"]
    if not isinstance(resolved_unit, str):
        raise CollectionError("systemd unit identity has an invalid type")

    snapshot = Snapshot.capture(
        target=Target(kind="systemd.unit", identifier=resolved_unit),
        evidence=evidence,
    )
    print(snapshot.to_json(pretty=args.pretty))
    return 0


def _inspect_git(args: argparse.Namespace) -> int:
    evidence = collect_git_repository(args.path)
    repository_root = evidence.data["repository_root"]
    if not isinstance(repository_root, str):
        raise CollectionError("git repository identity has an invalid type")

    snapshot = Snapshot.capture(
        target=Target(kind="git.repository", identifier=repository_root),
        evidence=(evidence,),
    )
    print(snapshot.to_json(pretty=args.pretty))
    return 0


def _inspect_codex(args: argparse.Namespace) -> int:
    evidence = collect_codex_runtime(
        args.path,
        resolve_thread=args.resolve_thread,
        resolve_mcp=args.resolve_mcp,
    )
    config = evidence[1]
    cwd = config.data["cwd"]
    if not isinstance(cwd, str):
        raise CollectionError("Codex working directory identity has an invalid type")

    snapshot = Snapshot.capture(
        target=Target(kind="codex.workspace", identifier=cwd),
        evidence=evidence,
    )
    print(snapshot.to_json(pretty=args.pretty))
    return 0


def _diff(args: argparse.Namespace) -> int:
    before = load_snapshot(args.before)
    after = load_snapshot(args.after)
    print(format_diff(diff_snapshots(before, after)))
    return 0


def _verify(args: argparse.Namespace) -> int:
    baseline = load_snapshot(args.baseline)
    current = load_snapshot(args.current)
    result = diff_snapshots(baseline, current)

    if not result.changes:
        print("PASS: runtime matches baseline.")
        return 0

    print("DRIFT: runtime differs from baseline.")
    print()
    print(format_diff(result))
    return _VERIFY_DRIFT_EXIT


def _add_pretty_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON snapshot.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runtimetruth",
        description="Runtime verification and drift detection for AI agents.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    commands = parser.add_subparsers(dest="command")
    inspect_parser = commands.add_parser(
        "inspect",
        help="Collect runtime evidence for one target.",
    )
    inspect_targets = inspect_parser.add_subparsers(dest="target_kind", required=True)

    systemd_parser = inspect_targets.add_parser(
        "systemd",
        help="Inspect one systemd-managed unit.",
    )
    systemd_parser.add_argument("unit", type=_systemd_unit)
    _add_pretty_argument(systemd_parser)
    systemd_parser.set_defaults(handler=_inspect_systemd)

    git_parser = inspect_targets.add_parser(
        "git",
        help="Inspect one local Git repository.",
    )
    git_parser.add_argument("path")
    _add_pretty_argument(git_parser)
    git_parser.set_defaults(handler=_inspect_git)

    codex_parser = inspect_targets.add_parser(
        "codex",
        help="Inspect effective Codex runtime configuration for a working directory.",
    )
    codex_parser.add_argument("path", nargs="?", default=".")
    codex_parser.add_argument(
        "--resolve-thread",
        action="store_true",
        help=(
            "Start an ephemeral Codex thread to record effective thread settings "
            "without starting a turn."
        ),
    )
    codex_parser.add_argument(
        "--resolve-mcp",
        action="store_true",
        help=(
            "Probe thread-scoped MCP server/tool runtime state. This may contact "
            "configured MCP servers or refresh authentication; no MCP tool is called."
        ),
    )
    _add_pretty_argument(codex_parser)
    codex_parser.set_defaults(handler=_inspect_codex)

    diff_parser = commands.add_parser(
        "diff",
        help="Compare two RuntimeTruth snapshots.",
    )
    diff_parser.add_argument("before")
    diff_parser.add_argument("after")
    diff_parser.set_defaults(handler=_diff)

    verify_parser = commands.add_parser(
        "verify",
        help="Verify a current snapshot against a baseline snapshot.",
    )
    verify_parser.add_argument("baseline")
    verify_parser.add_argument("current")
    verify_parser.set_defaults(handler=_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] | None = getattr(args, "handler", None)

    if handler is None:
        parser.print_help()
        return 0

    try:
        return handler(args)
    except (CollectionError, DiffError) as exc:
        print(f"runtimetruth: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
