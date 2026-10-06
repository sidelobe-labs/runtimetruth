import json
from pathlib import Path

from runtimetruth.cli import build_parser, main
from runtimetruth.model import EvidenceRecord, EvidenceSource

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def test_parser_has_expected_program_name() -> None:
    parser = build_parser()

    assert parser.prog == "runtimetruth"


def test_systemd_inspect_emits_composed_snapshot_json(monkeypatch, capsys) -> None:
    service = EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(collector="systemd", method="systemctl show"),
        data={
            "unit_id": "agent.service",
            "active_state": "active",
            "main_pid": 42,
        },
    )
    process = EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(collector="procfs", method="/proc/<pid>/{cwd,exe}"),
        data={
            "pid": 42,
            "cwd": "/srv/agent",
            "executable": "/usr/bin/python3",
        },
    )
    monkeypatch.setattr(
        "runtimetruth.cli.inspect_systemd_runtime",
        lambda unit: (service, process),
    )

    assert main(["inspect", "systemd", "agent.service"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["target"] == {
        "kind": "systemd.unit",
        "identifier": "agent.service",
    }
    assert [record["kind"] for record in payload["evidence"]] == [
        "systemd.unit",
        "linux.process",
    ]


def test_git_inspect_emits_snapshot_json(monkeypatch, capsys) -> None:
    evidence = EvidenceRecord(
        plane="live",
        kind="git.repository",
        source=EvidenceSource(collector="git", method="git rev-parse/status"),
        data={
            "repository_root": "/srv/agent",
            "head_commit": "a" * 40,
            "branch": "main",
            "detached": False,
            "dirty": False,
        },
    )
    monkeypatch.setattr(
        "runtimetruth.cli.collect_git_repository",
        lambda path: evidence,
    )

    assert main(["inspect", "git", "/srv/agent"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == {
        "kind": "git.repository",
        "identifier": "/srv/agent",
    }
    assert payload["evidence"][0]["data"]["head_commit"] == "a" * 40


def test_codex_inspect_separates_live_and_resolved_evidence(monkeypatch, capsys) -> None:
    runtime = EvidenceRecord(
        plane="live",
        kind="codex.runtime",
        source=EvidenceSource(collector="codex", method="codex --version"),
        data={
            "binary": "/usr/bin/codex",
            "version": "codex-cli 0.test",
        },
    )
    config = EvidenceRecord(
        plane="resolved",
        kind="codex.config",
        source=EvidenceSource(collector="codex", method="app-server config/read"),
        data={
            "cwd": "/srv/agent",
            "model": "gpt-test",
            "sandbox_mode": "workspace-write",
        },
    )
    thread = EvidenceRecord(
        plane="resolved",
        kind="codex.thread",
        source=EvidenceSource(collector="codex", method="app-server thread/start"),
        data={
            "model": "gpt-effective",
            "cwd": "/srv/agent",
        },
    )
    instructions = EvidenceRecord(
        plane="live",
        kind="codex.instructions",
        source=EvidenceSource(
            collector="filesystem",
            method="sha256 Codex thread instructionSources",
        ),
        data={
            "source_count": 1,
            "source:/srv/agent/AGENTS.md": "sha256:" + "a" * 64,
        },
    )
    mcp = EvidenceRecord(
        plane="live",
        kind="codex.mcp",
        source=EvidenceSource(
            collector="codex",
            method="app-server mcpServerStatus/list",
        ),
        data={
            "server_count": 1,
            "server:docs:runtime_status": "connected",
            "server:docs:auth_status": "unsupported",
            "server:docs:plugin_id": None,
            "server:docs:http_origin": "https://developers.openai.com",
            "server:docs:tool_count": 1,
            "server:docs:tool_names_included": True,
            "server:docs:tools": '["search"]',
            "server:docs:tool_catalog_status": "available",
            "server:docs:tool_catalog_sha256": "sha256:" + "b" * 64,
        },
    )

    def fake_collect(
        path: str,
        *,
        resolve_thread: bool = False,
        resolve_mcp: bool = False,
    ):
        if resolve_mcp:
            return runtime, config, thread, instructions, mcp
        if resolve_thread:
            return runtime, config, thread, instructions
        return runtime, config

    monkeypatch.setattr(
        "runtimetruth.cli.collect_codex_runtime",
        fake_collect,
    )

    assert main(["inspect", "codex", "/srv/agent"]) == 0
    passive = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in passive["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
    ]

    assert main(["inspect", "codex", "/srv/agent", "--resolve-thread"]) == 0
    probed = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in probed["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
        ("codex.thread", "resolved"),
        ("codex.instructions", "live"),
    ]

    assert main(["inspect", "codex", "/srv/agent", "--resolve-mcp"]) == 0
    mcp_probed = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in mcp_probed["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
        ("codex.thread", "resolved"),
        ("codex.instructions", "live"),
        ("codex.mcp", "live"),
    ]


def test_diff_command_renders_semantic_changes(capsys) -> None:
    assert (
        main(
            [
                "diff",
                str(_FIXTURES / "before.json"),
                str(_FIXTURES / "after.json"),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "SERVICE\n" in output
    assert "PROCESS\n" in output
    assert "CODE\n" in output
    assert "head_commit:" in output


def test_verify_pass_returns_zero(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")

    assert main(["verify", baseline, baseline]) == 0

    assert capsys.readouterr().out == "PASS: runtime matches baseline.\n"


def test_verify_drift_returns_two_and_renders_diff(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert main(["verify", baseline, current]) == 2

    output = capsys.readouterr().out
    assert output.startswith("DRIFT: runtime differs from baseline.\n\n")
    assert "SERVICE\n" in output
    assert "CODE\n" in output
    assert (
        "head_commit: 1111111111111111111111111111111111111111 -> "
        "2222222222222222222222222222222222222222"
    ) in output
