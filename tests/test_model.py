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
