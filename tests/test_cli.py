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
    monkeypatch.setattr(
        "runtimetruth.cli.collect_codex_runtime",
        lambda path: (runtime, config),
    )

    assert main(["inspect", "codex", "/srv/agent"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == {
        "kind": "codex.workspace",
        "identifier": "/srv/agent",
    }
    assert [(item["kind"], item["plane"]) for item in payload["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
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
