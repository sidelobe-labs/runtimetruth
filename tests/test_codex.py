import hashlib
import json
import stat
from pathlib import Path

import pytest

from runtimetruth.collectors.codex import collect_codex_runtime
from runtimetruth.collectors.errors import CollectionError
from runtimetruth.model import EvidenceSource


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
    elif method == "mcpServerStatus/list":
        params = message["params"]
        if params.get("threadId") != "thread-test":
            raise SystemExit(92)
        if params.get("detail") != "toolsAndAuthOnly":
            raise SystemExit(93)

        if params.get("cursor") is None:
            print(json.dumps({{
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {{
                    "data": [{{
                        "name": "filesystem",
                        "runtimeStatus": "connected",
                        "pluginId": None,
                        "httpOrigin": None,
                        "serverInfo": {{"name": "filesystem", "version": "1.0"}},
                        "serverCapabilities": {{"tools": {{}}}},
                        "tools": {{
                            "read_file": {{
                                "description": "DO NOT SERIALIZE TOOL DESCRIPTION",
                                "inputSchema": {{
                                    "type": "object",
                                    "properties": {{"path": {{"type": "string"}}}}
                                }}
                            }}
                        }},
                        "toolsError": None,
                        "resources": [{{"uri": "secret-resource"}}],
                        "resourceTemplates": [],
                        "authStatus": "unsupported"
                    }}],
                    "nextCursor": "page-2"
                }}
            }}), flush=True)
        else:
            print(json.dumps({{
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {{
                    "data": [{{
                        "name": "remote",
                        "runtimeStatus": "connected",
                        "pluginId": "plugin-example",
                        "httpOrigin": "https://mcp.example.test",
                        "serverInfo": None,
                        "serverCapabilities": None,
                        "tools": {{
                            "search": {{
                                "description": "DO NOT SERIALIZE SEARCH DESCRIPTION",
                                "inputSchema": {{"type": "object"}}
                            }},
                            "fetch": {{
                                "description": "DO NOT SERIALIZE FETCH DESCRIPTION",
                                "inputSchema": {{"type": "object"}}
                            }}
                        }},
                        "toolsError": None,
                        "resources": [],
                        "resourceTemplates": [],
                        "authStatus": "oAuth"
                    }}],
                    "nextCursor": None
                }}
            }}), flush=True)
    elif method in ("thread/delete", "turn/start", "mcpServer/tool/call"):
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


def test_collector_fingerprints_effective_instruction_source(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instructions_path = workspace / "AGENTS.md"
    instructions_path.write_text("runtime truth instructions\n", encoding="utf-8")
    method_log = tmp_path / "methods.log"
    executable = _fake_codex(tmp_path, log_path=method_log)

    runtime, config, thread, instructions = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
        resolve_thread=True,
    )

    expected_hash = hashlib.sha256(instructions_path.read_bytes()).hexdigest()

    assert runtime.kind == "codex.runtime"
    assert config.kind == "codex.config"
    assert thread.plane == "resolved"
    assert thread.kind == "codex.thread"
    assert thread.data["instruction_sources"] == json.dumps(
        [str(instructions_path)],
        separators=(",", ":"),
    )

    assert instructions.plane == "live"
    assert instructions.kind == "codex.instructions"
    assert instructions.source == EvidenceSource(
        collector="filesystem",
        method="sha256 Codex thread instructionSources",
    )
    assert instructions.data == {
        "source_count": 1,
        f"source:{instructions_path}": f"sha256:{expected_hash}",
    }

    serialized = json.dumps(instructions.to_dict())
    assert "runtime truth instructions" not in serialized

    methods = method_log.read_text(encoding="utf-8").splitlines()
    assert methods == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
    ]
    assert "turn/start" not in methods
    assert "thread/delete" not in methods


def test_collector_resolves_sanitized_thread_mcp_inventory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    instructions_path = workspace / "AGENTS.md"
    instructions_path.write_text("runtime truth instructions\n", encoding="utf-8")
    method_log = tmp_path / "methods.log"
    executable = _fake_codex(tmp_path, log_path=method_log)

    records = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
        resolve_mcp=True,
    )
    runtime, config, thread, instructions, mcp = records

    assert runtime.kind == "codex.runtime"
    assert config.kind == "codex.config"
    assert thread.kind == "codex.thread"
    assert instructions.kind == "codex.instructions"
    assert mcp.plane == "live"
    assert mcp.kind == "codex.mcp"
    assert mcp.source == EvidenceSource(
        collector="codex",
        method="app-server mcpServerStatus/list",
    )
    assert mcp.data["server_count"] == 2
    assert mcp.data["server:filesystem:runtime_status"] == "connected"
    assert mcp.data["server:filesystem:auth_status"] == "unsupported"
    assert mcp.data["server:filesystem:plugin_id"] is None
    assert mcp.data["server:filesystem:http_origin"] is None
    assert mcp.data["server:filesystem:tool_count"] == 1
    assert mcp.data["server:filesystem:tools"] == '["read_file"]'
    assert mcp.data["server:filesystem:tool_catalog_status"] == "available"
    assert str(mcp.data["server:filesystem:tool_catalog_sha256"]).startswith("sha256:")

    assert mcp.data["server:remote:runtime_status"] == "connected"
    assert mcp.data["server:remote:auth_status"] == "oAuth"
    assert mcp.data["server:remote:plugin_id"] == "plugin-example"
    assert mcp.data["server:remote:http_origin"] == "https://mcp.example.test"
    assert mcp.data["server:remote:tool_count"] == 2
    assert mcp.data["server:remote:tools"] == '["fetch","search"]'
    assert mcp.data["server:remote:tool_catalog_status"] == "available"

    serialized = json.dumps(mcp.to_dict())
    assert "DO NOT SERIALIZE" not in serialized
    assert "secret-resource" not in serialized
    assert "inputSchema" not in serialized

    methods = method_log.read_text(encoding="utf-8").splitlines()
    assert methods == [
        "initialize",
        "initialized",
        "config/read",
        "thread/start",
        "mcpServerStatus/list",
        "mcpServerStatus/list",
    ]
    assert "turn/start" not in methods
    assert "mcpServer/tool/call" not in methods


def test_collector_marks_missing_instruction_source_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = _fake_codex(tmp_path)

    _, _, _, instructions = collect_codex_runtime(
        str(workspace),
        codex_binary=str(executable),
        resolve_thread=True,
    )

    assert instructions.data == {
        "source_count": 1,
        f"source:{workspace / 'AGENTS.md'}": "unavailable",
    }


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
