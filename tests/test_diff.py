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
