"""Secret-safe evidence collection for systemd units."""

from __future__ import annotations

import re
import subprocess

from runtimetruth.model import EvidenceRecord, EvidenceSource, JsonScalar

SYSTEMD_PROPERTIES = (
    "Id",
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "FragmentPath",
    "DropInPaths",
    "MainPID",
    "ExecMainPID",
    "ExecMainCode",
    "ExecMainStatus",
    "ExecMainStartTimestampMonotonic",
    "NRestarts",
    "User",
    "Group",
    "DynamicUser",
    "WorkingDirectory",
    "ControlGroup",
)

_PROPERTY_NAMES = {
    "Id": "unit_id",
    "LoadState": "load_state",
    "ActiveState": "active_state",
    "SubState": "sub_state",
    "UnitFileState": "unit_file_state",
    "FragmentPath": "fragment_path",
    "DropInPaths": "drop_in_paths",
    "MainPID": "main_pid",
    "ExecMainPID": "exec_main_pid",
    "ExecMainCode": "exec_main_code",
    "ExecMainStatus": "exec_main_status",
    "ExecMainStartTimestampMonotonic": "exec_main_start_timestamp_monotonic",
    "NRestarts": "restart_count",
    "User": "user",
    "Group": "group",
    "DynamicUser": "dynamic_user",
    "WorkingDirectory": "working_directory",
    "ControlGroup": "control_group",
}

_INTEGER_PROPERTIES = {
    "MainPID",
    "ExecMainPID",
    "ExecMainCode",
    "ExecMainStatus",
    "ExecMainStartTimestampMonotonic",
    "NRestarts",
}

_BOOLEAN_PROPERTIES = {"DynamicUser"}
_UNIT_NAME = re.compile(r"^[-A-Za-z0-9_.@:]+$")


class CollectionError(RuntimeError):
    """Raised when live evidence cannot be collected safely or reliably."""


def validate_systemd_unit_name(unit: str) -> str:
    """Validate the deliberately narrow unit-name syntax supported by the MVP."""
    if not unit or unit.startswith("-") or _UNIT_NAME.fullmatch(unit) is None:
        raise ValueError(f"unsupported systemd unit name: {unit!r}")
    return unit


def _normalize_property(name: str, value: str) -> JsonScalar:
    if name in _INTEGER_PROPERTIES:
        try:
            return int(value)
        except ValueError as exc:
            raise CollectionError(f"systemctl returned a non-integer {name}") from exc

    if name in _BOOLEAN_PROPERTIES:
        if value == "yes":
            return True
        if value == "no":
            return False
        raise CollectionError(f"systemctl returned an invalid boolean {name}")

    return value


def parse_systemctl_show(output: str) -> dict[str, JsonScalar]:
    """Parse only the allowlisted properties from systemctl show output."""
    parsed: dict[str, JsonScalar] = {}

    for raw_line in output.splitlines():
        if not raw_line:
            continue

        key, separator, value = raw_line.partition("=")
        if not separator:
            raise CollectionError("systemctl returned malformed property data")

        field_name = _PROPERTY_NAMES.get(key)
        if field_name is None:
            continue

        parsed[field_name] = _normalize_property(key, value)

    if "unit_id" not in parsed:
        raise CollectionError("systemctl output did not include the unit identity")

    return parsed


def collect_systemd_unit(unit: str, *, timeout: float = 5.0) -> EvidenceRecord:
    """Collect a small, explicit set of live systemd properties."""
    validate_systemd_unit_name(unit)

    command = [
        "systemctl",
        "show",
        "--no-pager",
        f"--property={','.join(SYSTEMD_PROPERTIES)}",
        unit,
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CollectionError("systemctl is not available on this host") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectionError(f"systemctl timed out while inspecting {unit!r}") from exc

    if completed.returncode != 0:
        raise CollectionError(
            f"systemctl show failed for {unit!r} with exit status {completed.returncode}"
        )

    return EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(
            collector="systemd",
            method="systemctl show",
        ),
        data=parse_systemctl_show(completed.stdout),
    )
