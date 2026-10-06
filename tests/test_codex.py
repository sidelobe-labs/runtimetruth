import json
import stat
from pathlib import Path

import pytest

from runtimetruth.collectors.codex import collect_codex_runtime
from runtimetruth.collectors.errors import CollectionError


def _fake_codex(tmp_path: Path, *, malformed_config: bool = False) -> Path:
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

    executable.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.test")
    raise SystemExit(0)

if sys.argv[1:] != ["app-server"]:
    raise SystemExit(2)

for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")

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
        break
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
