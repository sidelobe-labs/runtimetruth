"""RuntimeTruth command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from runtimetruth import __version__
from runtimetruth.attestation import (
    AttestationError,
    create_signed_attestation,
    snapshot_sha256,
    verify_signed_attestation,
)
from runtimetruth.collectors import (
    CollectionError,
    collect_codex_runtime,
    collect_git_repository,
)
from runtimetruth.collectors.systemd import validate_systemd_unit_name
from runtimetruth.diff import (
    DiffError,
    SnapshotDiff,
    diff_snapshots,
    diff_to_dict,
    format_diff,
    load_snapshot,
)
from runtimetruth.inspection import inspect_systemd_runtime
from runtimetruth.model import Snapshot, Target
from runtimetruth.policy import PolicyError, load_policy

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


def _capture_codex_snapshot(
    path: str,
    *,
    resolve_thread: bool,
    resolve_mcp: bool,
) -> Snapshot:
    evidence = collect_codex_runtime(
        path,
        resolve_thread=resolve_thread,
        resolve_mcp=resolve_mcp,
    )
    config = evidence[1]
    cwd = config.data["cwd"]
    if not isinstance(cwd, str):
        raise CollectionError("Codex working directory identity has an invalid type")

    return Snapshot.capture(
        target=Target(kind="codex.workspace", identifier=cwd),
        evidence=evidence,
    )


def _inspect_codex(args: argparse.Namespace) -> int:
    snapshot = _capture_codex_snapshot(
        args.path,
        resolve_thread=args.resolve_thread,
        resolve_mcp=args.resolve_mcp,
    )
    print(snapshot.to_json(pretty=args.pretty))
    return 0


def _diff(args: argparse.Namespace) -> int:
    before = load_snapshot(args.before)
    after = load_snapshot(args.after)
    print(format_diff(diff_snapshots(before, after)))
    return 0


def _digest(args: argparse.Namespace) -> int:
    baseline = load_snapshot(args.baseline)
    print(f"sha256:{snapshot_sha256(baseline)}")
    return 0


def _attest(args: argparse.Namespace) -> int:
    baseline = load_snapshot(args.baseline)
    digest = create_signed_attestation(
        baseline,
        statement_path=args.statement,
        bundle_path=args.bundle,
        cosign=args.cosign,
    )
    print(f"BASELINE: sha256:{digest}")
    print(f"STATEMENT: {args.statement}")
    print(f"BUNDLE: {args.bundle}")
    return 0


def _render_verify(
    result: SnapshotDiff,
    *,
    target: Target,
    selectors: tuple[str, ...],
    json_output: bool,
) -> int:
    status = "drift" if result.changes else "pass"
    exit_code = _VERIFY_DRIFT_EXIT if result.changes else 0

    if json_output:
        report = {
            "report_schema_version": 1,
            "status": status,
            "target": target.to_dict(),
            "protected": list(selectors),
            **diff_to_dict(result),
        }
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return exit_code

    if not result.changes:
        print("PASS: runtime matches baseline.")
        return 0

    print("DRIFT: runtime differs from baseline.")
    print()
    print(format_diff(result))
    return _VERIFY_DRIFT_EXIT


def _verification_selectors(args: argparse.Namespace) -> tuple[str, ...]:
    policy_selectors = load_policy(args.policy).protect if args.policy is not None else ()
    return tuple(dict.fromkeys((*policy_selectors, *args.protect)))


def _verify(args: argparse.Namespace) -> int:
    baseline = load_snapshot(args.baseline)

    if args.current is not None and args.codex is not None:
        raise DiffError("verify accepts either a current snapshot or --codex, not both")
    if args.current is None and args.codex is None:
        raise DiffError("verify requires a current snapshot or --codex")

    if args.codex is not None:
        current = _capture_codex_snapshot(
            args.codex,
            resolve_thread=args.resolve_thread,
            resolve_mcp=args.resolve_mcp,
        )
    else:
        current = load_snapshot(args.current)

    selectors = _verification_selectors(args)
    return _render_verify(
        diff_snapshots(
            baseline,
            current,
            selectors=selectors,
        ),
        target=baseline.target,
        selectors=selectors,
        json_output=args.json,
    )


def _verify_attestation(args: argparse.Namespace) -> int:
    baseline = load_snapshot(args.baseline)

    digest = verify_signed_attestation(
        baseline,
        statement_path=args.statement,
        bundle_path=args.bundle,
        certificate_identity=args.certificate_identity,
        certificate_oidc_issuer=args.certificate_oidc_issuer,
        cosign=args.cosign,
    )

    if args.current is not None and args.codex is not None:
        raise DiffError("verify-attestation accepts either a current snapshot or --codex, not both")
    if args.current is None and args.codex is None:
        raise DiffError("verify-attestation requires a current snapshot or --codex")

    if args.codex is not None:
        current = _capture_codex_snapshot(
            args.codex,
            resolve_thread=args.resolve_thread,
            resolve_mcp=args.resolve_mcp,
        )
    else:
        current = load_snapshot(args.current)

    selectors = _verification_selectors(args)
    result = diff_snapshots(
        baseline,
        current,
        selectors=selectors,
    )
    status = "drift" if result.changes else "pass"
    exit_code = _VERIFY_DRIFT_EXIT if result.changes else 0

    if args.json:
        report = {
            "report_schema_version": 1,
            "status": status,
            "identity": {
                "verified": True,
                "certificate_identity": args.certificate_identity,
                "oidc_issuer": args.certificate_oidc_issuer,
            },
            "baseline": {
                "verified": True,
                "sha256": digest,
            },
            "target": baseline.target.to_dict(),
            "protected": list(selectors),
            **diff_to_dict(result),
        }
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return exit_code

    print("IDENTITY: VERIFIED")
    print(f"  certificate_identity: {args.certificate_identity}")
    print(f"  oidc_issuer: {args.certificate_oidc_issuer}")
    print("BASELINE: VERIFIED")
    print(f"  sha256: {digest}")

    if not result.changes:
        print("RUNTIME: PASS")
        return 0

    print("RUNTIME: DRIFT")
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

    digest_parser = commands.add_parser(
        "digest",
        help="Compute the RFC 8785 canonical SHA-256 digest of a baseline snapshot.",
    )
    digest_parser.add_argument("baseline")
    digest_parser.set_defaults(handler=_digest)

    attest_parser = commands.add_parser(
        "attest",
        help="Create and keylessly sign an in-toto attestation for a baseline snapshot.",
    )
    attest_parser.add_argument("baseline")
    attest_parser.add_argument(
        "--statement",
        required=True,
        metavar="FILE",
        help="Write the canonical in-toto Statement v1 JSON to FILE.",
    )
    attest_parser.add_argument(
        "--bundle",
        required=True,
        metavar="FILE",
        help="Write the Sigstore verification bundle for the signed statement to FILE.",
    )
    attest_parser.add_argument(
        "--cosign",
        default="cosign",
        metavar="PATH",
        help="Cosign executable to use for keyless signing (default: cosign).",
    )
    attest_parser.set_defaults(handler=_attest)

    verify_parser = commands.add_parser(
        "verify",
        help="Verify a current snapshot or live Codex runtime against a baseline.",
    )
    verify_parser.add_argument("baseline")
    verify_parser.add_argument("current", nargs="?")
    verify_parser.add_argument(
        "--codex",
        metavar="PATH",
        help="Collect a live Codex runtime from PATH instead of loading CURRENT.",
    )
    verify_parser.add_argument(
        "--resolve-thread",
        action="store_true",
        help="Resolve an ephemeral Codex thread when verifying a live Codex runtime.",
    )
    verify_parser.add_argument(
        "--resolve-mcp",
        action="store_true",
        help=(
            "Probe thread-scoped MCP runtime state when verifying live Codex. "
            "This may contact configured MCP servers or refresh authentication."
        ),
    )
    verify_parser.add_argument(
        "--policy",
        metavar="FILE",
        help=(
            "Load protected selectors from an explicit schema-v1 TOML policy file. "
            "CLI --protect selectors extend the file; no policy is auto-discovered."
        ),
    )
    verify_parser.add_argument(
        "--protect",
        action="append",
        default=[],
        metavar="SELECTOR",
        help=(
            "Only fail on drift in this evidence kind or exact field. "
            "Repeat for multiple selectors; omit for strict full-snapshot verification."
        ),
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a structured JSON PASS/DRIFT report.",
    )
    verify_parser.set_defaults(handler=_verify)

    verify_attestation_parser = commands.add_parser(
        "verify-attestation",
        help="Verify signed baseline identity before comparing the current runtime.",
    )
    verify_attestation_parser.add_argument("baseline")
    verify_attestation_parser.add_argument("current", nargs="?")
    verify_attestation_parser.add_argument(
        "--statement",
        required=True,
        metavar="FILE",
        help="Canonical in-toto Statement v1 JSON that was signed.",
    )
    verify_attestation_parser.add_argument(
        "--bundle",
        required=True,
        metavar="FILE",
        help="Sigstore verification bundle for the signed statement.",
    )
    verify_attestation_parser.add_argument(
        "--certificate-identity",
        required=True,
        metavar="IDENTITY",
        help="Exact expected Sigstore certificate identity.",
    )
    verify_attestation_parser.add_argument(
        "--certificate-oidc-issuer",
        required=True,
        metavar="URL",
        help="Exact expected OIDC issuer for the signing identity.",
    )
    verify_attestation_parser.add_argument(
        "--cosign",
        default="cosign",
        metavar="PATH",
        help="Cosign executable to use for verification (default: cosign).",
    )
    verify_attestation_parser.add_argument(
        "--codex",
        metavar="PATH",
        help="Collect a live Codex runtime from PATH instead of loading CURRENT.",
    )
    verify_attestation_parser.add_argument(
        "--resolve-thread",
        action="store_true",
        help="Resolve an ephemeral Codex thread when verifying a live Codex runtime.",
    )
    verify_attestation_parser.add_argument(
        "--resolve-mcp",
        action="store_true",
        help=(
            "Probe thread-scoped MCP runtime state when verifying live Codex. "
            "This may contact configured MCP servers or refresh authentication."
        ),
    )
    verify_attestation_parser.add_argument(
        "--policy",
        metavar="FILE",
        help=(
            "Load runtime selectors from an explicit schema-v1 TOML policy file. "
            "The policy affects only the runtime semantic gate, never attestation trust checks."
        ),
    )
    verify_attestation_parser.add_argument(
        "--protect",
        action="append",
        default=[],
        metavar="SELECTOR",
        help=(
            "Only fail on drift in this evidence kind or exact field. "
            "Repeat for multiple selectors; omit for strict full-snapshot verification."
        ),
    )
    verify_attestation_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a structured identity/baseline/runtime verification report.",
    )
    verify_attestation_parser.set_defaults(handler=_verify_attestation)

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
    except (AttestationError, CollectionError, DiffError, PolicyError) as exc:
        print(f"runtimetruth: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
