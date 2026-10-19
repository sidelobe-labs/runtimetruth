import json

import pytest

from runtimetruth.cli import main
from runtimetruth.diff import diff_snapshots, diff_to_dict, format_diff
from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target


def _snapshot(dirty: bool | int) -> Snapshot:
    snapshot = Snapshot.capture(
        target=Target(kind="git.repository", identifier="/srv/agent"),
        evidence=(
            EvidenceRecord(
                plane="live",
                kind="git.repository",
                source=EvidenceSource(collector="git", method="git rev-parse/status"),
                data={"dirty": dirty},
            ),
        ),
    )
    return Snapshot.from_json(snapshot.to_json())


@pytest.mark.parametrize("before, after", [(False, 0), (0, False), (True, 1), (1, True)])
def test_diff_reports_boolean_and_integer_changes(before: bool | int, after: bool | int) -> None:
    result = diff_snapshots(_snapshot(before), _snapshot(after))

    assert format_diff(result) == f"CODE\n  dirty: {json.dumps(before)} -> {json.dumps(after)}"
    field = diff_to_dict(result)["changes"][0]["fields"][0]
    assert type(field["before"]["value"]) is type(before)
    assert type(field["after"]["value"]) is type(after)


def test_verify_protected_boolean_changed_to_integer_reports_drift(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(_snapshot(False).to_json(), encoding="utf-8")
    current.write_text(_snapshot(0).to_json(), encoding="utf-8")

    exit_code = main(
        [
            "verify",
            str(baseline),
            str(current),
            "--protect",
            "git.repository.dirty",
            "--json",
        ]
    )

    assert exit_code == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "drift"
    assert report["protected"] == ["git.repository.dirty"]
    field = report["changes"][0]["fields"][0]
    assert field["before"]["value"] is False
    assert type(field["after"]["value"]) is int
    assert field["after"]["value"] == 0
