"""RuntimeTruth command-line entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from runtimetruth import __version__
from runtimetruth.collectors.systemd import (
    CollectionError,
    collect_systemd_unit,
    validate_systemd_unit_name,
)
from runtimetruth.model import Snapshot, Target


def _systemd_unit(value: str) -> str:
    try:
        return validate_systemd_unit_name(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _inspect_systemd(args: argparse.Namespace) -> int:
    evidence = collect_systemd_unit(args.unit)
    resolved_unit = evidence.data["unit_id"]
    if not isinstance(resolved_unit, str):
        raise CollectionError("systemd unit identity has an invalid type")

    snapshot = Snapshot.capture(
        target=Target(kind="systemd.unit", identifier=resolved_unit),
        evidence=(evidence,),
    )
    print(snapshot.to_json(pretty=args.pretty))
    return 0


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
        help="Collect live evidence for one runtime target.",
    )
    inspect_targets = inspect_parser.add_subparsers(dest="target_kind", required=True)

    systemd_parser = inspect_targets.add_parser(
        "systemd",
        help="Inspect one systemd-managed unit.",
    )
    systemd_parser.add_argument("unit", type=_systemd_unit)
    systemd_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON snapshot.",
    )
    systemd_parser.set_defaults(handler=_inspect_systemd)

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
    except CollectionError as exc:
        print(f"runtimetruth: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
