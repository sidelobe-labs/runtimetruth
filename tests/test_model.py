import json
from datetime import UTC, datetime

import pytest

from runtimetruth.model import (
    EvidenceRecord,
    EvidenceSource,
    Snapshot,
    SnapshotFormatError,
    Target,
)


def test_snapshot_serialization_is_stable() -> None:
    snapshot = Snapshot.capture(
        captured_at=datetime(2026, 10, 6, 0, 0, tzinfo=UTC),
        target=Target(kind="systemd.unit", identifier="agent.service"),
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="systemd.unit",
                source=EvidenceSource(collector="systemd", method="systemctl show"),
                data={"sub_state": "running", "main_pid": 42},
            ),
        ),
    )

    payload = json.loads(snapshot.to_json())

    assert payload == {
        "schema_version": 1,
        "captured_at": "2026-10-06T00:00:00Z",
        "target": {
            "kind": "systemd.unit",
            "identifier": "agent.service",
        },
        "evidence": [
            {
                "plane": "live",
                "kind": "systemd.unit",
                "source": {
                    "collector": "systemd",
                    "method": "systemctl show",
                },
                "data": {
                    "main_pid": 42,
                    "sub_state": "running",
                },
            }
        ],
    }


def test_snapshot_rejects_naive_capture_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Snapshot.capture(
            captured_at=datetime(2026, 10, 6),
            target=Target(kind="systemd.unit", identifier="agent.service"),
            evidence=(),
        )


def test_snapshot_json_round_trip() -> None:
    snapshot = Snapshot.capture(
        captured_at=datetime(2026, 10, 6, 0, 0, tzinfo=UTC),
        target=Target(kind="git.repository", identifier="/srv/agent"),
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="git.repository",
                source=EvidenceSource(collector="git", method="git rev-parse/status"),
                data={
                    "repository_root": "/srv/agent",
                    "branch": None,
                    "dirty": False,
                },
            ),
        ),
    )

    assert Snapshot.from_json(snapshot.to_json()) == snapshot


def test_snapshot_parser_rejects_unknown_schema_version() -> None:
    with pytest.raises(SnapshotFormatError, match="unsupported schema_version"):
        Snapshot.from_json('{"schema_version":2,"captured_at":"x","target":{},"evidence":[]}')


def test_snapshot_parser_rejects_duplicate_json_keys() -> None:
    payload = (
        '{"schema_version":1,"schema_version":1,'
        '"captured_at":"2026-10-06T00:00:00Z",'
        '"target":{"kind":"git.repository","identifier":"/srv/agent"},'
        '"evidence":[]}'
    )

    with pytest.raises(SnapshotFormatError, match="duplicate JSON object key"):
        Snapshot.from_json(payload)


def test_snapshot_parser_rejects_boolean_schema_version() -> None:
    payload = {
        "schema_version": True,
        "captured_at": "2026-10-06T00:00:00Z",
        "target": {"kind": "git.repository", "identifier": "/srv/agent"},
        "evidence": [],
    }

    with pytest.raises(SnapshotFormatError, match="unsupported schema_version"):
        Snapshot.from_dict(payload)


@pytest.mark.parametrize("timestamp", [
    "2026-02-30T00:00:00Z",
    "2026-10-06T00:00:00",
    "2026-10-06",
    "not-a-timestamp",
])
def test_snapshot_parser_rejects_invalid_capture_time(timestamp: str) -> None:
    payload = {
        "schema_version": 1,
        "captured_at": timestamp,
        "target": {"kind": "git.repository", "identifier": "/srv/agent"},
        "evidence": [],
    }

    with pytest.raises(SnapshotFormatError, match="timezone-aware ISO 8601"):
        Snapshot.from_dict(payload)


def test_snapshot_parser_accepts_capture_time_with_utc_offset() -> None:
    timestamp = "2026-10-06T02:00:00+02:00"
    snapshot = Snapshot.from_dict({
        "schema_version": 1,
        "captured_at": timestamp,
        "target": {"kind": "git.repository", "identifier": "/srv/agent"},
        "evidence": [],
    })

    assert snapshot.captured_at == timestamp
