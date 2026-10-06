"""Semantic comparison for RuntimeTruth schema-v1 snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from runtimetruth.model import EvidenceRecord, JsonScalar, Snapshot, SnapshotFormatError

_SUPPORTED_KINDS = (
    "systemd.unit",
    "linux.process",
    "git.repository",
    "codex.runtime",
    "codex.config",
    "codex.thread",
    "codex.instructions",
    "codex.mcp",
)
_SECTION_NAMES = {
    "systemd.unit": "SERVICE",
    "linux.process": "PROCESS",
    "git.repository": "CODE",
    "codex.runtime": "CODEX RUNTIME",
    "codex.config": "CODEX CONFIG",
    "codex.thread": "CODEX THREAD",
    "codex.instructions": "CODEX INSTRUCTIONS",
    "codex.mcp": "CODEX MCP",
}


class DiffError(RuntimeError):
    """Raised when two snapshots cannot be compared faithfully."""


@dataclass(frozen=True, slots=True)
class MissingValue:
    """Represents a field absent from an evidence record."""


MISSING = MissingValue()
type DiffValue = JsonScalar | MissingValue


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One changed evidence field."""

    field: str
    before: DiffValue
    after: DiffValue


@dataclass(frozen=True, slots=True)
class EvidenceChange:
    """Change to one supported evidence record."""

    kind: str
    status: Literal["added", "removed", "changed"]
    fields: tuple[FieldChange, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """Semantic changes between two snapshots of the same target."""

    changes: tuple[EvidenceChange, ...]


def load_snapshot(path: str) -> Snapshot:
    """Load one schema-v1 snapshot from disk."""
    snapshot_path = Path(path)

    try:
        payload = snapshot_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffError(f"could not read snapshot {path!r}: {exc.strerror}") from exc

    try:
        return Snapshot.from_json(payload)
    except SnapshotFormatError as exc:
        raise DiffError(f"invalid snapshot {path!r}: {exc}") from exc


def _index_evidence(snapshot: Snapshot) -> dict[str, EvidenceRecord]:
    indexed: dict[str, EvidenceRecord] = {}

    for record in snapshot.evidence:
        if record.kind not in _SUPPORTED_KINDS:
            raise DiffError(f"unsupported evidence kind: {record.kind!r}")
        if record.kind in indexed:
            raise DiffError(f"duplicate evidence kind: {record.kind!r}")
        indexed[record.kind] = record

    return indexed


def _diff_record(before: EvidenceRecord, after: EvidenceRecord) -> tuple[FieldChange, ...]:
    if before.plane != after.plane or before.source != after.source:
        raise DiffError(
            f"evidence provenance differs for {before.kind!r}; "
            "schema-v1 provenance changes are not comparable yet"
        )

    changes: list[FieldChange] = []
    fields = sorted(set(before.data) | set(after.data))

    for field in fields:
        before_value: DiffValue = before.data.get(field, MISSING)
        after_value: DiffValue = after.data.get(field, MISSING)

        if before_value != after_value:
            changes.append(
                FieldChange(
                    field=field,
                    before=before_value,
                    after=after_value,
                )
            )

    return tuple(changes)


def diff_snapshots(before: Snapshot, after: Snapshot) -> SnapshotDiff:
    """Compare supported evidence records while ignoring capture time."""
    if before.target != after.target:
        raise DiffError(
            "snapshot targets differ: "
            f"{before.target.kind}:{before.target.identifier!r} != "
            f"{after.target.kind}:{after.target.identifier!r}"
        )

    before_records = _index_evidence(before)
    after_records = _index_evidence(after)
    changes: list[EvidenceChange] = []

    for kind in _SUPPORTED_KINDS:
        left = before_records.get(kind)
        right = after_records.get(kind)

        if left is None and right is None:
            continue
        if left is None:
            changes.append(EvidenceChange(kind=kind, status="added"))
            continue
        if right is None:
            changes.append(EvidenceChange(kind=kind, status="removed"))
            continue

        field_changes = _diff_record(left, right)
        if field_changes:
            changes.append(
                EvidenceChange(
                    kind=kind,
                    status="changed",
                    fields=field_changes,
                )
            )

    return SnapshotDiff(changes=tuple(changes))


def _format_value(value: DiffValue) -> str:
    if isinstance(value, MissingValue):
        return "<missing>"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def format_diff(result: SnapshotDiff) -> str:
    """Render a compact human-readable semantic diff."""
    if not result.changes:
        return "No runtime changes."

    lines: list[str] = []

    for index, change in enumerate(result.changes):
        if index:
            lines.append("")

        lines.append(_SECTION_NAMES[change.kind])

        if change.status != "changed":
            lines.append(f"  evidence: {change.status}")
            continue

        for field in change.fields:
            lines.append(
                f"  {field.field}: {_format_value(field.before)} -> {_format_value(field.after)}"
            )

    return "\n".join(lines)
