import json
from pathlib import Path

from runtimetruth.cli import build_parser, main
from runtimetruth.model import EvidenceRecord, EvidenceSource, Snapshot, Target

_FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def test_parser_has_expected_program_name() -> None:
    parser = build_parser()

    assert parser.prog == "runtimetruth"


def test_systemd_inspect_emits_composed_snapshot_json(monkeypatch, capsys) -> None:
    service = EvidenceRecord(
        plane="live",
        kind="systemd.unit",
        source=EvidenceSource(collector="systemd", method="systemctl show"),
        data={
            "unit_id": "agent.service",
            "active_state": "active",
            "main_pid": 42,
        },
    )
    process = EvidenceRecord(
        plane="live",
        kind="linux.process",
        source=EvidenceSource(collector="procfs", method="/proc/<pid>/{cwd,exe}"),
        data={
            "pid": 42,
            "cwd": "/srv/agent",
            "executable": "/usr/bin/python3",
        },
    )
    monkeypatch.setattr(
        "runtimetruth.cli.inspect_systemd_runtime",
        lambda unit: (service, process),
    )

    assert main(["inspect", "systemd", "agent.service"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["target"] == {
        "kind": "systemd.unit",
        "identifier": "agent.service",
    }
    assert [record["kind"] for record in payload["evidence"]] == [
        "systemd.unit",
        "linux.process",
    ]


def test_git_inspect_emits_snapshot_json(monkeypatch, capsys) -> None:
    evidence = EvidenceRecord(
        plane="live",
        kind="git.repository",
        source=EvidenceSource(collector="git", method="git rev-parse/status"),
        data={
            "repository_root": "/srv/agent",
            "head_commit": "a" * 40,
            "branch": "main",
            "detached": False,
            "dirty": False,
        },
    )
    monkeypatch.setattr(
        "runtimetruth.cli.collect_git_repository",
        lambda path: evidence,
    )

    assert main(["inspect", "git", "/srv/agent"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == {
        "kind": "git.repository",
        "identifier": "/srv/agent",
    }
    assert payload["evidence"][0]["data"]["head_commit"] == "a" * 40


def test_codex_inspect_separates_live_and_resolved_evidence(monkeypatch, capsys) -> None:
    runtime = EvidenceRecord(
        plane="live",
        kind="codex.runtime",
        source=EvidenceSource(collector="codex", method="codex --version"),
        data={
            "binary": "/usr/bin/codex",
            "version": "codex-cli 0.test",
        },
    )
    config = EvidenceRecord(
        plane="resolved",
        kind="codex.config",
        source=EvidenceSource(collector="codex", method="app-server config/read"),
        data={
            "cwd": "/srv/agent",
            "model": "gpt-test",
            "sandbox_mode": "workspace-write",
        },
    )
    thread = EvidenceRecord(
        plane="resolved",
        kind="codex.thread",
        source=EvidenceSource(collector="codex", method="app-server thread/start"),
        data={
            "model": "gpt-effective",
            "cwd": "/srv/agent",
        },
    )
    instructions = EvidenceRecord(
        plane="live",
        kind="codex.instructions",
        source=EvidenceSource(
            collector="filesystem",
            method="sha256 Codex thread instructionSources",
        ),
        data={
            "source_count": 1,
            "source:/srv/agent/AGENTS.md": "sha256:" + "a" * 64,
        },
    )
    mcp = EvidenceRecord(
        plane="live",
        kind="codex.mcp",
        source=EvidenceSource(
            collector="codex",
            method="app-server mcpServerStatus/list",
        ),
        data={
            "server_count": 1,
            "server:docs:runtime_status": "connected",
            "server:docs:auth_status": "unsupported",
            "server:docs:plugin_id": None,
            "server:docs:http_origin": "https://developers.openai.com",
            "server:docs:tool_count": 1,
            "server:docs:tool_names_included": True,
            "server:docs:tools": '["search"]',
            "server:docs:tool_catalog_status": "available",
            "server:docs:tool_catalog_sha256": "sha256:" + "b" * 64,
        },
    )

    def fake_collect(
        path: str,
        *,
        resolve_thread: bool = False,
        resolve_mcp: bool = False,
    ):
        if resolve_mcp:
            return runtime, config, thread, instructions, mcp
        if resolve_thread:
            return runtime, config, thread, instructions
        return runtime, config

    monkeypatch.setattr(
        "runtimetruth.cli.collect_codex_runtime",
        fake_collect,
    )

    assert main(["inspect", "codex", "/srv/agent"]) == 0
    passive = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in passive["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
    ]

    assert main(["inspect", "codex", "/srv/agent", "--resolve-thread"]) == 0
    probed = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in probed["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
        ("codex.thread", "resolved"),
        ("codex.instructions", "live"),
    ]

    assert main(["inspect", "codex", "/srv/agent", "--resolve-mcp"]) == 0
    mcp_probed = json.loads(capsys.readouterr().out)
    assert [(item["kind"], item["plane"]) for item in mcp_probed["evidence"]] == [
        ("codex.runtime", "live"),
        ("codex.config", "resolved"),
        ("codex.thread", "resolved"),
        ("codex.instructions", "live"),
        ("codex.mcp", "live"),
    ]


def test_diff_command_renders_semantic_changes(capsys) -> None:
    assert (
        main(
            [
                "diff",
                str(_FIXTURES / "before.json"),
                str(_FIXTURES / "after.json"),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "SERVICE\n" in output
    assert "PROCESS\n" in output
    assert "CODE\n" in output
    assert "head_commit:" in output


def test_verify_pass_returns_zero(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")

    assert main(["verify", baseline, baseline]) == 0

    assert capsys.readouterr().out == "PASS: runtime matches baseline.\n"


def test_verify_drift_returns_two_and_renders_diff(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert main(["verify", baseline, current]) == 2

    output = capsys.readouterr().out
    assert output.startswith("DRIFT: runtime differs from baseline.\n\n")
    assert "SERVICE\n" in output
    assert "CODE\n" in output


def test_verify_live_codex_reuses_collector(monkeypatch, tmp_path, capsys) -> None:
    source = EvidenceSource(collector="codex", method="codex --version")
    target = Target(kind="codex.workspace", identifier="/srv/agent")
    runtime = EvidenceRecord(
        plane="live",
        kind="codex.runtime",
        source=source,
        data={
            "binary": "/usr/bin/codex",
            "version": "codex-cli 0.test",
        },
    )
    config = EvidenceRecord(
        plane="resolved",
        kind="codex.config",
        source=EvidenceSource(collector="codex", method="app-server config/read"),
        data={"cwd": "/srv/agent"},
    )
    baseline = Snapshot.capture(
        target=target,
        evidence=(runtime, config),
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(baseline.to_json(pretty=True), encoding="utf-8")

    monkeypatch.setattr(
        "runtimetruth.cli.collect_codex_runtime",
        lambda path, *, resolve_thread=False, resolve_mcp=False: (runtime, config),
    )

    assert (
        main(
            [
                "verify",
                str(baseline_path),
                "--codex",
                "/srv/agent",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "PASS: runtime matches baseline.\n"


def test_verify_rejects_snapshot_and_live_codex_together(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert main(["verify", baseline, current, "--codex", "/srv/agent"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "either a current snapshot or --codex" in captured.err


def test_verify_protect_ignores_unprotected_drift(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert (
        main(
            [
                "verify",
                baseline,
                current,
                "--protect",
                "git.repository.branch",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == "PASS: runtime matches baseline.\n"


def test_verify_protect_reports_only_selected_drift(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert (
        main(
            [
                "verify",
                baseline,
                current,
                "--protect",
                "git.repository.head_commit",
            ]
        )
        == 2
    )

    output = capsys.readouterr().out
    assert "CODE\n" in output
    assert "head_commit:" in output
    assert "dirty:" not in output
    assert "SERVICE\n" not in output
    assert "PROCESS\n" not in output


def test_verify_protect_rejects_unknown_selector(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert (
        main(
            [
                "verify",
                baseline,
                current,
                "--protect",
                "git.repository.not_a_real_field",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not match an evidence field" in captured.err


def test_verify_json_pass_report(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")

    assert main(["verify", baseline, baseline, "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report == {
        "report_schema_version": 1,
        "status": "pass",
        "target": {
            "kind": "systemd.unit",
            "identifier": "agent.service",
        },
        "protected": [],
        "changes": [],
    }


def test_verify_json_drift_report_preserves_structure(capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    assert (
        main(
            [
                "verify",
                baseline,
                current,
                "--protect",
                "git.repository.head_commit",
                "--json",
            ]
        )
        == 2
    )

    report = json.loads(capsys.readouterr().out)
    assert report["report_schema_version"] == 1
    assert report["status"] == "drift"
    assert report["protected"] == ["git.repository.head_commit"]
    assert report["target"] == {
        "kind": "systemd.unit",
        "identifier": "agent.service",
    }
    assert report["changes"] == [
        {
            "kind": "git.repository",
            "status": "changed",
            "fields": [
                {
                    "field": "head_commit",
                    "before": {
                        "present": True,
                        "value": "1111111111111111111111111111111111111111",
                    },
                    "after": {
                        "present": True,
                        "value": "2222222222222222222222222222222222222222",
                    },
                }
            ],
        }
    ]


def test_digest_emits_canonical_sha256(monkeypatch, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    monkeypatch.setattr("runtimetruth.cli.snapshot_sha256", lambda snapshot: "a" * 64)

    assert main(["digest", baseline]) == 0

    assert capsys.readouterr().out == f"sha256:{'a' * 64}\n"


def test_attest_emits_digest_and_bundle_path(monkeypatch, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")

    monkeypatch.setattr(
        "runtimetruth.cli.create_signed_attestation",
        lambda baseline, *, bundle_path, cosign: "b" * 64,
    )

    assert (
        main(
            [
                "attest",
                baseline,
                "--bundle",
                "baseline.sigstore.json",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        f"BASELINE: sha256:{'b' * 64}\n"
        "ATTESTATION: baseline.sigstore.json\n"
    )


def test_verify_attestation_pass_verifies_trust_before_runtime(
    monkeypatch,
    capsys,
) -> None:
    baseline = str(_FIXTURES / "before.json")
    events: list[str] = []

    def verify_trust(*args, **kwargs):
        events.append("trust")
        return "c" * 64

    monkeypatch.setattr(
        "runtimetruth.cli.verify_signed_attestation",
        verify_trust,
    )

    assert (
        main(
            [
                "verify-attestation",
                baseline,
                baseline,
                "--bundle",
                "baseline.sigstore.json",
                "--certificate-identity",
                "signer@example.com",
                "--certificate-oidc-issuer",
                "https://accounts.example.com",
            ]
        )
        == 0
    )

    assert events == ["trust"]
    assert capsys.readouterr().out == (
        "IDENTITY: VERIFIED\n"
        "  certificate_identity: signer@example.com\n"
        "  oidc_issuer: https://accounts.example.com\n"
        "BASELINE: VERIFIED\n"
        f"  sha256: {'c' * 64}\n"
        "RUNTIME: PASS\n"
    )


def test_verify_attestation_drift_preserves_exit_two(monkeypatch, capsys) -> None:
    baseline = str(_FIXTURES / "before.json")
    current = str(_FIXTURES / "after.json")

    monkeypatch.setattr(
        "runtimetruth.cli.verify_signed_attestation",
        lambda *args, **kwargs: "d" * 64,
    )

    assert (
        main(
            [
                "verify-attestation",
                baseline,
                current,
                "--bundle",
                "baseline.sigstore.json",
                "--certificate-identity",
                "signer@example.com",
                "--certificate-oidc-issuer",
                "https://accounts.example.com",
                "--protect",
                "git.repository.head_commit",
            ]
        )
        == 2
    )

    output = capsys.readouterr().out
    assert output.startswith("IDENTITY: VERIFIED\n")
    assert "BASELINE: VERIFIED\n" in output
    assert "RUNTIME: DRIFT\n" in output
    assert "head_commit:" in output


def test_verify_attestation_json_report_includes_trust_result(
    monkeypatch,
    capsys,
) -> None:
    baseline = str(_FIXTURES / "before.json")

    monkeypatch.setattr(
        "runtimetruth.cli.verify_signed_attestation",
        lambda *args, **kwargs: "e" * 64,
    )

    assert (
        main(
            [
                "verify-attestation",
                baseline,
                baseline,
                "--bundle",
                "baseline.sigstore.json",
                "--certificate-identity",
                "https://github.com/example/project/.github/workflows/attest.yml@refs/heads/main",
                "--certificate-oidc-issuer",
                "https://token.actions.githubusercontent.com",
                "--json",
            ]
        )
        == 0
    )

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "pass"
    assert report["identity"] == {
        "verified": True,
        "certificate_identity": "https://github.com/example/project/.github/workflows/attest.yml@refs/heads/main",
        "oidc_issuer": "https://token.actions.githubusercontent.com",
    }
    assert report["baseline"] == {
        "verified": True,
        "sha256": "e" * 64,
    }
    assert report["changes"] == []


def test_verify_attestation_identity_failure_stops_before_runtime(
    monkeypatch,
    capsys,
) -> None:
    baseline = str(_FIXTURES / "before.json")

    def fail_identity(*args, **kwargs):
        from runtimetruth.attestation import AttestationError

        raise AttestationError("identity mismatch")

    monkeypatch.setattr(
        "runtimetruth.cli.verify_signed_attestation",
        fail_identity,
    )

    assert (
        main(
            [
                "verify-attestation",
                baseline,
                baseline,
                "--bundle",
                "baseline.sigstore.json",
                "--certificate-identity",
                "expected",
                "--certificate-oidc-issuer",
                "https://issuer.example",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "identity mismatch" in captured.err
