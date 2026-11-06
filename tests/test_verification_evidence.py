import json
from pathlib import Path

import pytest

from runtimetruth.cli import main
from runtimetruth.collectors.codex import _mcp_server_data
from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target


def _snapshot(*, tools_error: str | None = None, instruction_available: bool = True) -> Snapshot:
    mcp_data = {"server_count": 1}
    _mcp_server_data(
        {
            "name": "docs",
            "runtimeStatus": "connected",
            "authStatus": "unsupported",
            "tools": {},
            "toolsError": tools_error,
        },
        data=mcp_data,
        seen_names=set(),
    )
    return Snapshot.capture(
        target=Target(kind="codex.workspace", identifier="/srv/agent"),
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="codex.mcp",
                source=EvidenceSource(collector="codex", method="app-server mcpServerStatus/list"),
                data=mcp_data,
            ),
            EvidenceRecord(
                plane="live",
                kind="codex.instructions",
                source=EvidenceSource(
                    collector="filesystem", method="sha256 Codex thread instructionSources"
                ),
                data={
                    "source_count": 1,
                    "source:/srv/agent/AGENTS.md": (
                        "sha256:" + "a" * 64 if instruction_available else "unavailable"
                    ),
                },
            ),
        ),
    )


def _write_snapshot(tmp_path: Path, name: str, snapshot: Snapshot) -> str:
    path = tmp_path / name
    path.write_text(snapshot.to_json(), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize(
    "selectors",
    [
        (),
        ("codex.mcp",),
        ("codex.mcp.server:docs:tools",),
        ("codex.mcp.server:docs:tool_count",),
        ("codex.mcp.server:docs:tool_names_included",),
        ("codex.mcp.server:docs:tool_catalog_sha256",),
        ("codex.instructions",),
        ("codex.instructions.source:/srv/agent/AGENTS.md",),
    ],
)
def test_verify_rejects_matching_incomplete_evidence(
    tmp_path, capsys, selectors: tuple[str, ...], json_output: bool
) -> None:
    snapshot = _snapshot(tools_error="connection timed out", instruction_available=False)
    path = _write_snapshot(tmp_path, "partial.json", snapshot)
    arguments = ["verify", path, path]
    for selector in selectors:
        arguments.extend(["--protect", selector])
    if json_output:
        arguments.append("--json")

    assert main(arguments) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unavailable" in captured.err


@pytest.mark.parametrize("partial_side", ["baseline", "current"])
def test_verify_checks_both_snapshots_for_incomplete_evidence(
    tmp_path, capsys, partial_side
) -> None:
    complete = _write_snapshot(tmp_path, "complete.json", _snapshot())
    partial = _write_snapshot(tmp_path, "partial.json", _snapshot(tools_error="timed out"))
    baseline, current = (partial, complete) if partial_side == "baseline" else (complete, partial)

    assert main(["verify", baseline, current, "--protect", "codex.mcp"]) == 1
    assert "unavailable MCP tool catalog" in capsys.readouterr().err


@pytest.mark.parametrize("status", [None, "unknown", "error"])
def test_verify_rejects_catalog_fields_without_available_status(tmp_path, capsys, status) -> None:
    snapshot = _snapshot()
    data = snapshot.evidence[0].data
    if status is None:
        data.pop("server:docs:tool_catalog_status")
    else:
        data["server:docs:tool_catalog_status"] = status
    path = _write_snapshot(tmp_path, "partial.json", snapshot)

    assert main(["verify", path, path, "--protect", "codex.mcp.server:docs:tools"]) == 1
    assert "unavailable MCP tool catalog" in capsys.readouterr().err


@pytest.mark.parametrize(
    "selector",
    [
        "codex.mcp.server_count",
        "codex.mcp.server:docs:runtime_status",
        "codex.mcp.server:docs:tool_catalog_status",
        "codex.instructions.source_count",
    ],
)
def test_verify_can_select_observed_metadata_from_partial_evidence(
    tmp_path, capsys, selector
) -> None:
    snapshot = _snapshot(tools_error="timed out", instruction_available=False)
    path = _write_snapshot(tmp_path, "partial.json", snapshot)

    assert main(["verify", path, path, "--protect", selector, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"


def test_verify_ignores_incomplete_unselected_evidence(tmp_path, capsys) -> None:
    snapshot = _snapshot(tools_error="timed out")
    path = _write_snapshot(tmp_path, "partial.json", snapshot)

    assert main(["verify", path, path, "--protect", "codex.instructions"]) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["codex.mcp", "codex.instructions"])
def test_verify_ignores_an_unselected_failed_source_in_the_same_record(
    tmp_path, capsys, kind
) -> None:
    snapshot = _snapshot()
    if kind == "codex.mcp":
        snapshot.evidence[0].data.update(
            {
                "server:other:tools": "[]",
                "server:other:tool_catalog_status": "error",
            }
        )
        selector = "codex.mcp.server:docs:tools"
    else:
        snapshot.evidence[1].data["source:/srv/agent/missing.md"] = "unavailable"
        selector = "codex.instructions.source:/srv/agent/AGENTS.md"
    path = _write_snapshot(tmp_path, "partial.json", snapshot)

    assert main(["verify", path, path, "--protect", selector]) == 0
    assert "PASS" in capsys.readouterr().out


def test_verify_accepts_an_available_empty_catalog(tmp_path, capsys) -> None:
    path = _write_snapshot(tmp_path, "complete.json", _snapshot())

    assert main(["verify", path, path]) == 0
    assert "PASS" in capsys.readouterr().out


def test_diff_still_reports_matching_partial_evidence(tmp_path, capsys) -> None:
    path = _write_snapshot(tmp_path, "partial.json", _snapshot(tools_error="timed out"))

    assert main(["diff", path, path]) == 0
    assert capsys.readouterr().out == "No runtime changes.\n"


@pytest.mark.parametrize("json_output", [False, True])
def test_signed_verification_rejects_matching_partial_evidence(
    monkeypatch, tmp_path, capsys, json_output: bool
) -> None:
    path = _write_snapshot(tmp_path, "partial.json", _snapshot(tools_error="timed out"))
    trust_checks = []

    def verify_trust(*args, **kwargs):
        trust_checks.append("verified")
        return "f" * 64

    monkeypatch.setattr("runtimetruth.cli.verify_signed_attestation", verify_trust)
    arguments = [
        "verify-attestation",
        path,
        path,
        "--statement",
        "baseline.intoto.json",
        "--bundle",
        "baseline.sigstore.json",
        "--certificate-identity",
        "signer@example.com",
        "--certificate-oidc-issuer",
        "https://accounts.example.com",
    ]
    if json_output:
        arguments.append("--json")

    assert main(arguments) == 1
    assert trust_checks == ["verified"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unavailable MCP tool catalog" in captured.err
