"""Versioned snapshot model for RuntimeTruth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

type JsonScalar = str | int | bool | None
type EvidencePlane = Literal["declared", "resolved", "live"]

_EVIDENCE_PLANES = {"declared", "resolved", "live"}


class SnapshotFormatError(ValueError):
    """Raised when serialized snapshot data does not match the supported schema."""


def _object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SnapshotFormatError(f"{field} must be an object")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise SnapshotFormatError(f"{field} must be a string")
    return value


def _scalar_data(value: object, *, field: str) -> dict[str, JsonScalar]:
    payload = _object(value, field=field)
    data: dict[str, JsonScalar] = {}

    for key, item in payload.items():
        if item is not None and not isinstance(item, (str, int, bool)):
            raise SnapshotFormatError(f"{field}.{key} must be a JSON scalar")
        data[key] = item

    return data


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    """Describes how one evidence record was obtained."""

    collector: str
    method: str

    def to_dict(self) -> dict[str, str]:
        return {
            "collector": self.collector,
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Observed or resolved runtime evidence with explicit provenance."""

    plane: EvidencePlane
    kind: str
    source: EvidenceSource
    data: dict[str, JsonScalar]

    def to_dict(self) -> dict[str, object]:
        return {
            "plane": self.plane,
            "kind": self.kind,
            "source": self.source.to_dict(),
            "data": dict(sorted(self.data.items())),
        }


@dataclass(frozen=True, slots=True)
class Target:
    """Identity of the runtime object being inspected."""

    kind: str
    identifier: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "identifier": self.identifier,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A versioned collection of runtime evidence."""

    schema_version: int
    captured_at: str
    target: Target
    evidence: tuple[EvidenceRecord, ...]

    @classmethod
    def capture(
        cls,
        *,
        target: Target,
        evidence: tuple[EvidenceRecord, ...],
        captured_at: datetime | None = None,
    ) -> Snapshot:
        when = captured_at or datetime.now(UTC)
        if when.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")

        timestamp = when.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return cls(
            schema_version=1,
            captured_at=timestamp,
            target=target,
            evidence=evidence,
        )

    @classmethod
    def from_dict(cls, payload: object) -> Snapshot:
        """Parse one schema-v1 snapshot from decoded JSON data."""
        root = _object(payload, field="snapshot")

        schema_version = root.get("schema_version")
        if schema_version != 1:
            raise SnapshotFormatError(f"unsupported schema_version: {schema_version!r}")

        captured_at = _string(root.get("captured_at"), field="captured_at")

        target_payload = _object(root.get("target"), field="target")
        target = Target(
            kind=_string(target_payload.get("kind"), field="target.kind"),
            identifier=_string(
                target_payload.get("identifier"),
                field="target.identifier",
            ),
        )

        evidence_payload = root.get("evidence")
        if not isinstance(evidence_payload, list):
            raise SnapshotFormatError("evidence must be an array")

        evidence: list[EvidenceRecord] = []
        for index, item in enumerate(evidence_payload):
            record_payload = _object(item, field=f"evidence[{index}]")
            plane = _string(
                record_payload.get("plane"),
                field=f"evidence[{index}].plane",
            )
            if plane not in _EVIDENCE_PLANES:
                raise SnapshotFormatError(
                    f"evidence[{index}].plane has unsupported value: {plane!r}"
                )

            source_payload = _object(
                record_payload.get("source"),
                field=f"evidence[{index}].source",
            )
            evidence.append(
                EvidenceRecord(
                    plane=plane,
                    kind=_string(
                        record_payload.get("kind"),
                        field=f"evidence[{index}].kind",
                    ),
                    source=EvidenceSource(
                        collector=_string(
                            source_payload.get("collector"),
                            field=f"evidence[{index}].source.collector",
                        ),
                        method=_string(
                            source_payload.get("method"),
                            field=f"evidence[{index}].source.method",
                        ),
                    ),
                    data=_scalar_data(
                        record_payload.get("data"),
                        field=f"evidence[{index}].data",
                    ),
                )
            )

        return cls(
            schema_version=1,
            captured_at=captured_at,
            target=target,
            evidence=tuple(evidence),
        )

    @classmethod
    def from_json(cls, payload: str) -> Snapshot:
        """Parse one schema-v1 snapshot from JSON text."""
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SnapshotFormatError(f"invalid JSON: {exc.msg}") from exc

        return cls.from_dict(decoded)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at,
            "target": self.target.to_dict(),
            "evidence": [record.to_dict() for record in self.evidence],
        }

    def to_json(self, *, pretty: bool = False) -> str:
        payload = self.to_dict()
        if pretty:
            return json.dumps(payload, indent=2, sort_keys=True)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
