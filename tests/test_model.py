import json
from datetime import UTC, datetime

from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target


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
    try:
        Snapshot.capture(
            captured_at=datetime(2026, 10, 6),
            target=Target(kind="systemd.unit", identifier="agent.service"),
            evidence=(),
        )
    except ValueError as exc:
        assert str(exc) == "captured_at must be timezone-aware"
    else:
        raise AssertionError("expected a timezone validation error")
