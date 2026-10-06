import json

from runtimetruth.cli import build_parser, main
from runtimetruth.model import EvidenceRecord, EvidenceSource


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
