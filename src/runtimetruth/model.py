"""Versioned snapshot model for RuntimeTruth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

type JsonScalar = str | int | bool | None
type EvidencePlane = Literal["declared", "resolved", "live"]


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
