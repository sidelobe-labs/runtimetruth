from pathlib import Path

import pytest

from runtimetruth.diff import DiffError, diff_snapshots, format_diff, load_snapshot
from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def test_realistic_snapshot_diff_groups_runtime_changes() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = load_snapshot(str(_FIXTURES / "after.json"))

    rendered = format_diff(diff_snapshots(before, after))

    assert rendered == "\n".join(
        [
            "SERVICE",
            "  exec_main_pid: 3036 -> 4190",
            "  main_pid: 3036 -> 4190",
            "  restart_count: 0 -> 1",
            "",
            "PROCESS",
            "  pid: 3036 -> 4190",
            "",
            "CODE",
            "  dirty: false -> true",
            "  head_commit: 1111111111111111111111111111111111111111 -> "
            "2222222222222222222222222222222222222222",
        ]
    )


def test_codex_snapshot_diff_groups_agent_state_changes() -> None:
    target = Target(kind="codex.workspace", identifier="/srv/agent")
    runtime_source = EvidenceSource(collector="codex", method="codex --version")
    config_source = EvidenceSource(collector="codex", method="app-server config/read")
    thread_source = EvidenceSource(collector="codex", method="app-server thread/start")
    instruction_source = EvidenceSource(
        collector="filesystem",
        method="sha256 Codex thread instructionSources",
    )

    before = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="codex.runtime",
                source=runtime_source,
                data={
                    "binary": "/usr/lib/codex/codex.js",
                    "version": "codex-cli 0.156.1",
                },
            ),
            EvidenceRecord(
                plane="resolved",
                kind="codex.config",
                source=config_source,
                data={
                    "cwd": "/srv/agent",
                    "model": None,
                    "sandbox_mode": "workspace-write",
                },
            ),
            EvidenceRecord(
                plane="resolved",
                kind="codex.thread",
                source=thread_source,
                data={
                    "model": "gpt-6-astra",
                    "approval_policy": "on-request",
                    "instruction_sources": '["/srv/agent/AGENTS.md"]',
                    "sandbox": (
                        '{"networkAccess":true,"type":"workspaceWrite","writableRoots":[]}'
                    ),
                },
            ),
            EvidenceRecord(
                plane="live",
                kind="codex.instructions",
                source=instruction_source,
                data={
                    "source_count": 1,
                    "source:/srv/agent/AGENTS.md": "sha256:" + "a" * 64,
                },
            ),
        ),
    )
    after = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="codex.runtime",
                source=runtime_source,
                data={
                    "binary": "/usr/lib/codex/codex.js",
                    "version": "codex-cli 0.157.0",
                },
            ),
            EvidenceRecord(
                plane="resolved",
                kind="codex.config",
                source=config_source,
                data={
                    "cwd": "/srv/agent",
                    "model": "gpt-6-pro",
                    "sandbox_mode": "workspace-write",
                },
            ),
            EvidenceRecord(
                plane="resolved",
                kind="codex.thread",
                source=thread_source,
                data={
                    "model": "gpt-6-pro",
                    "approval_policy": "never",
                    "instruction_sources": ('["/srv/agent/AGENTS.md","/srv/agent/sub/AGENTS.md"]'),
                    "sandbox": (
                        '{"networkAccess":false,"type":"workspaceWrite","writableRoots":[]}'
                    ),
                },
            ),
            EvidenceRecord(
                plane="live",
                kind="codex.instructions",
                source=instruction_source,
                data={
                    "source_count": 2,
                    "source:/srv/agent/AGENTS.md": "sha256:" + "b" * 64,
                    "source:/srv/agent/sub/AGENTS.md": "sha256:" + "c" * 64,
                },
            ),
        ),
    )

    assert format_diff(diff_snapshots(before, after)) == "\n".join(
        [
            "CODEX RUNTIME",
            "  version: codex-cli 0.156.1 -> codex-cli 0.157.0",
            "",
            "CODEX CONFIG",
            "  model: null -> gpt-6-pro",
            "",
            "CODEX THREAD",
            "  approval_policy: on-request -> never",
            '  instruction_sources: ["/srv/agent/AGENTS.md"] -> '
            '["/srv/agent/AGENTS.md","/srv/agent/sub/AGENTS.md"]',
            "  model: gpt-6-astra -> gpt-6-pro",
            '  sandbox: {"networkAccess":true,"type":"workspaceWrite",'
            '"writableRoots":[]} -> '
            '{"networkAccess":false,"type":"workspaceWrite","writableRoots":[]}',
            "",
            "CODEX INSTRUCTIONS",
            "  source:/srv/agent/AGENTS.md: sha256:" + "a" * 64 + " -> sha256:" + "b" * 64,
            "  source:/srv/agent/sub/AGENTS.md: <missing> -> sha256:" + "c" * 64,
            "  source_count: 1 -> 2",
        ]
    )


def test_capture_time_is_not_a_runtime_change() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    payload = before.to_dict()
    payload["captured_at"] = "2030-01-01T00:00:00Z"
    after = Snapshot.from_dict(payload)

    assert format_diff(diff_snapshots(before, after)) == "No runtime changes."


def test_diff_rejects_different_targets() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = Snapshot(
        schema_version=1,
        captured_at=before.captured_at,
        target=Target(kind="systemd.unit", identifier="other.service"),
        evidence=before.evidence,
    )

    with pytest.raises(DiffError, match="snapshot targets differ"):
        diff_snapshots(before, after)


def test_diff_reports_added_evidence() -> None:
    service = EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(collector="systemd", method="systemctl show"),
        data={"unit_id": "agent.service", "main_pid": 0},
    )
    process = EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(collector="procfs", method="/proc/<pid>/{cwd,exe}"),
        data={"pid": 42, "cwd": "/srv/agent", "executable": "/usr/bin/python3"},
    )
    target = Target(kind="systemd.unit", identifier="agent.service")
    before = Snapshot.capture(target=target, evidence=(service,))
    after = Snapshot.capture(target=target, evidence=(service, process))

    assert format_diff(diff_snapshots(before, after)) == "\n".join(
        [
            "PROCESS",
            "  evidence: added",
        ]
    )


def test_missing_field_is_distinct_from_null() -> None:
    source = EvidenceSource(collector="git", method="git rev-parse/status")
    target = Target(kind="git.repository", identifier="/srv/agent")
    before = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="git.repository",
                source=source,
                data={"repository_root": "/srv/agent"},
            ),
        ),
    )
    after = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="git.repository",
                source=source,
                data={
                    "repository_root": "/srv/agent",
                    "branch": None,
                },
            ),
        ),
    )

    assert format_diff(diff_snapshots(before, after)) == "\n".join(
        [
            "CODE",
            "  branch: <missing> -> null",
        ]
    )


def test_codex_mcp_diff_reports_tool_catalog_change() -> None:
    source = EvidenceSource(
        collector="codex",
        method="app-server mcpServerStatus/list",
    )
    target = Target(kind="codex.workspace", identifier="/srv/agent")

    before = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="codex.mcp",
                source=source,
                data={
                    "server_count": 1,
                    "server:docs:runtime_status": "connected",
                    "server:docs:auth_status": "unsupported",
                    "server:docs:tool_count": 1,
                    "server:docs:tools": '["search"]',
                    "server:docs:tool_catalog_sha256": "sha256:" + "a" * 64,
                },
            ),
        ),
    )
    after = Snapshot.capture(
        target=target,
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="codex.mcp",
                source=source,
                data={
                    "server_count": 1,
                    "server:docs:runtime_status": "connected",
                    "server:docs:auth_status": "unsupported",
                    "server:docs:tool_count": 2,
                    "server:docs:tools": '["fetch","search"]',
                    "server:docs:tool_catalog_sha256": "sha256:" + "b" * 64,
                },
            ),
        ),
    )

    assert format_diff(diff_snapshots(before, after)) == "\n".join(
        [
            "CODEX MCP",
            "  server:docs:tool_catalog_sha256: sha256:" + "a" * 64 + " -> sha256:" + "b" * 64,
            "  server:docs:tool_count: 1 -> 2",
            '  server:docs:tools: ["search"] -> ["fetch","search"]',
        ]
    )


def test_diff_selects_one_protected_field() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = load_snapshot(str(_FIXTURES / "after.json"))

    rendered = format_diff(
        diff_snapshots(
            before,
            after,
            selectors=("git.repository.head_commit",),
        )
    )

    assert rendered == "\n".join(
        [
            "CODE",
            "  head_commit: 1111111111111111111111111111111111111111 -> "
            "2222222222222222222222222222222222222222",
        ]
    )


def test_diff_selector_ignores_unprotected_changes() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = load_snapshot(str(_FIXTURES / "after.json"))

    result = diff_snapshots(
        before,
        after,
        selectors=("git.repository.branch",),
    )

    assert result.changes == ()


def test_diff_selector_can_protect_whole_evidence_kind() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = load_snapshot(str(_FIXTURES / "after.json"))

    rendered = format_diff(
        diff_snapshots(
            before,
            after,
            selectors=("git.repository",),
        )
    )

    assert rendered == "\n".join(
        [
            "CODE",
            "  dirty: false -> true",
            "  head_commit: 1111111111111111111111111111111111111111 -> "
            "2222222222222222222222222222222222222222",
        ]
    )


def test_diff_selector_rejects_unknown_field() -> None:
    before = load_snapshot(str(_FIXTURES / "before.json"))
    after = load_snapshot(str(_FIXTURES / "after.json"))

    with pytest.raises(DiffError, match="does not match an evidence field"):
        diff_snapshots(
            before,
            after,
            selectors=("git.repository.not_a_real_field",),
        )
