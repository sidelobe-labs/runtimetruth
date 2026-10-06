import json
from pathlib import Path

from runtimetruth.cli import main

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def test_verify_policy_ignores_unprotected_drift(tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")
    policy = tmp_path / "policy.toml"
    policy.write_text('version = 1\nprotect = ["git.repository.branch"]\n', encoding="utf-8")

    assert main(["verify", baseline, current, "--policy", str(policy)]) == 0
    assert capsys.readouterr().out == "PASS: runtime matches baseline.\n"


def test_verify_policy_reports_selected_drift(tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")
    policy = tmp_path / "policy.toml"
    policy.write_text(
        'version = 1\nprotect = ["git.repository.head_commit"]\n',
        encoding="utf-8",
    )

    assert main(["verify", baseline, current, "--policy", str(policy)]) == 2
    output = capsys.readouterr().out
    assert "head_commit:" in output
    assert "dirty:" not in output


def test_verify_policy_and_cli_protect_are_additive(tmp_path, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")
    policy = tmp_path / "policy.toml"
    policy.write_text('version = 1\nprotect = ["git.repository.branch"]\n', encoding="utf-8")

    assert (
        main(
            [
                "verify",
                baseline,
                current,
                "--policy",
                str(policy),
                "--protect",
                "git.repository.head_commit",
                "--json",
            ]
        )
        == 2
    )

    report = json.loads(capsys.readouterr().out)
    assert report["protected"] == [
        "git.repository.branch",
        "git.repository.head_commit",
    ]
