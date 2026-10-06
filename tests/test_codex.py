import json
import stat
from pathlib import Path

import pytest

from runtimetruth.collectors.codex import collect_codex_runtime
from runtimetruth.collectors.errors import CollectionError


def _fake_codex(
    tmp_path: Path,
    *,
    malformed_config: bool = False,
    log_path: Path | None = None,
) -> Path:
    executable = tmp_path / "codex"
    config_result = (
        "[]"
        if malformed_config
        else """{
            "model": "gpt-test",
            "model_provider": "openai",
            "model_reasoning_effort": "high",
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "web_search": "cached",
            "instructions": "DO NOT CAPTURE THIS",
            "developer_instructions": "DO NOT CAPTURE THIS EITHER",
            "model_providers": {
                "private": {"token": "provider-secret"}
            },
            "mcp_servers": {
                "private": {"env": {"TOKEN": "mcp-secret"}}
            }
        }"""
    )
    method_log = repr(str(log_path)) if log_path is not None else "None"

    executable.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

METHOD_LOG = {method_log}

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.test")
    raise SystemExit(0)

if sys.argv[1:] != ["app-server"]:
    raise SystemExit(2)

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")

    if METHOD_LOG is not None and method is not None:
        with open(METHOD_LOG, "a", encoding="utf-8") as handle:
            handle.write(method + "\\n")

    if method == "initialize":
        print(json.dumps({{"jsonrpc": "2.0", "id": message["id"], "result": {{}}}}), flush=True)
    elif method == "config/read":
        print(json.dumps({{
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {{
                "config": {config_result},
                "origins": {{}}
            }}
        }}), flush=True)
    elif method == "thread/start":
        print(json.dumps({{
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {{
                "thread": {{
                    "id": "thread-test",
                    "cliVersion": "codex-cli 0.test"
                }},
                "model": "gpt-effective",
                "modelProvider": "openai",
                "cwd": message["params"]["cwd"],
                "approvalPolicy": "on-request",
                "sandbox": {{
                    "type": "workspaceWrite",
                    "writableRoots": [message["params"]["cwd"]],
                    "networkAccess": False
                }},
                "reasoningEffort": "high",
                "instructionSources": [
                    message["params"]["cwd"] + "/AGENTS.md"
                ]
            }}
        }}), flush=True)
    elif method == "thread/delete":
        print(json.dumps({{
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {{}}
        }}), flush=True)
        break
    elif method == "turn/start":
        raise SystemExit(91)
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def test_collector_uses_codex_effective_config_and_allowlist(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _fake_codex(tmp_path)

    runtime, config = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
    )

    assert runtime.plane == "live"
    assert runtime.kind == "codex.runtime"
    assert runtime.data == {
        "binary": str(executable.resolve()),
        "version": "codex-cli 0.test",
    }

    assert config.plane == "resolved"
    assert config.kind == "codex.config"
    assert config.source.method == "app-server config/read"
    assert config.data == {
        "cwd": str(workspace.resolve()),
        "model": "gpt-test",
        "model_provider": "openai",
        "model_reasoning_effort": "high",
        "approval_policy": "on-request",
        "sandbox_mode": "workspace-write",
        "web_search": "cached",
    }

    serialized = json.dumps(config.to_dict())
    assert "DO NOT CAPTURE" not in serialized
    assert "provider-secret" not in serialized
    assert "mcp-secret" not in serialized


def test_collector_resolves_ephemeral_thread_without_starting_turn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    method_log = tmp_path / "methods.log"
    executable = _fake_codex(tmp_path, log_path=method_log)

    runtime, config, thread = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
        resolve_thread=True,
    )

    assert runtime.kind == "codex.runtime"
    assert config.kind == "codex.config"
    assert thread.plane == "resolved"
    assert thread.kind == "codex.thread"
    assert thread.data == {
        "model": "gpt-effective",
        "model_provider": "openai",
        "reasoning_effort": "high",
        "cwd": str(workspace.resolve()),
        "approval_policy": "on-request",
        "sandbox": json.dumps(
            {
                "type": "workspaceWrite",
                "writableRoots": [str(workspace.resolve())],
                "networkAccess": False,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        "instruction_sources": json.dumps(
            [str(workspace.resolve() / "AGENTS.md")],
            separators=(",", ":"),
        ),
        "cli_version": "codex-cli 0.test",
    }

    methods = method_log.read_text(encoding="utf-8").splitlines()
    assert methods == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
        "thread/delete",
    ]
    assert "turn/start" not in methods


def test_collector_serializes_granular_approval_policy(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "codex"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import sys

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.test")
    raise SystemExit(0)

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), flush=True)
    elif message.get("method") == "config/read":
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "config": {
                    "approval_policy": {
                        "granular": {
                            "mcp_elicitations": True,
                            "rules": False,
                            "sandbox_approval": True
                        }
                    }
                },
                "origins": {}
            }
        }), flush=True)
        break
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    _, config = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
    )

    assert config.data["approval_policy"] == (
        '{"granular":{"mcp_elicitations":true,"rules":false,"sandbox_approval":true}}'
    )


def test_collector_rejects_malformed_config_response(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _fake_codex(tmp_path, malformed_config=True)

    with pytest.raises(CollectionError, match="no config object"):
        collect_codex_runtime(
            str(workspace),
            codex_binary=str(executable),
        )
