"""Agent-aware evidence collection for the Codex CLI runtime."""

from __future__ import annotations

import contextlib
import hashlib
import json
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TextIO

from runtimetruth.collectors.errors import CollectionError
from runtimetruth.model import EvidenceRecord, EvidenceSource, JsonScalar

_SAFE_CONFIG_FIELDS = (
    "model",
    "model_provider",
    "model_reasoning_effort",
    "approval_policy",
    "sandbox_mode",
    "web_search",
)


def _resolve_codex_binary(binary: str | None) -> Path:
    candidate = binary or shutil.which("codex")
    if candidate is None:
        raise CollectionError("codex is not available on this host")

    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_file():
        raise CollectionError(f"codex executable does not exist: {str(resolved)!r}")
    return resolved


def _run_codex_version(binary: Path, *, timeout: float) -> str:
    try:
        completed = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CollectionError("codex --version timed out") from exc

    if completed.returncode != 0:
        raise CollectionError(f"codex --version failed with exit status {completed.returncode}")

    version = completed.stdout.strip()
    if not version:
        raise CollectionError("codex --version returned an empty version")
    return version


def _reader(stdout: TextIO, output: queue.Queue[str | None]) -> None:
    try:
        for line in stdout:
            output.put(line)
    finally:
        output.put(None)


def _send_message(stdin: TextIO, payload: dict[str, object]) -> None:
    stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    stdin.flush()


def _read_response(
    output: queue.Queue[str | None],
    *,
    request_id: int,
    deadline: float,
) -> dict[str, object]:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CollectionError(f"codex app-server timed out waiting for response {request_id}")

        try:
            line = output.get(timeout=remaining)
        except queue.Empty as exc:
            raise CollectionError(
                f"codex app-server timed out waiting for response {request_id}"
            ) from exc

        if line is None:
            raise CollectionError(f"codex app-server exited before response {request_id}")

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CollectionError("codex app-server returned invalid JSON") from exc

        if not isinstance(message, dict):
            raise CollectionError("codex app-server returned a non-object message")
        if message.get("id") != request_id:
            continue

        error = message.get("error")
        if error is not None:
            raise CollectionError(f"codex app-server request {request_id} failed: {error!r}")

        result = message.get("result")
        if not isinstance(result, dict):
            raise CollectionError(f"codex app-server response {request_id} has no object result")
        return result


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.0)


def _safe_json(value: object, *, field: str) -> str:
    if not isinstance(value, (dict, list)):
        raise CollectionError(f"codex thread/start returned invalid {field}")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _safe_config_value(field: str, value: object) -> JsonScalar:
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if field == "approval_policy" and isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    raise CollectionError(f"codex config/read returned unsupported value type for {field!r}")


def _instruction_sources(result: dict[str, object]) -> tuple[str, ...]:
    value = result.get("instructionSources")
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CollectionError("codex thread/start returned invalid instructionSources")
    return tuple(value)


def _thread_id(result: dict[str, object]) -> str:
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise CollectionError("codex thread/start returned no thread object")

    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise CollectionError("codex thread/start returned no thread id")
    return thread_id


def _thread_evidence(
    result: dict[str, object],
    *,
    instruction_sources: tuple[str, ...],
) -> EvidenceRecord:
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise CollectionError("codex thread/start returned no thread object")

    _thread_id(result)
    data: dict[str, JsonScalar] = {}

    scalar_fields = {
        "model": "model",
        "modelProvider": "model_provider",
        "reasoningEffort": "reasoning_effort",
        "cwd": "cwd",
    }
    for source_field, output_field in scalar_fields.items():
        value = result.get(source_field)
        if value is not None and not isinstance(value, (str, int, bool)):
            raise CollectionError(f"codex thread/start returned invalid {source_field}")
        data[output_field] = value

    approval_policy = result.get("approvalPolicy")
    if approval_policy is None or isinstance(approval_policy, (str, int, bool)):
        data["approval_policy"] = approval_policy
    elif isinstance(approval_policy, dict):
        data["approval_policy"] = json.dumps(
            approval_policy,
            separators=(",", ":"),
            sort_keys=True,
        )
    else:
        raise CollectionError("codex thread/start returned invalid approvalPolicy")

    sandbox = result.get("sandbox")
    if sandbox is not None:
        data["sandbox"] = _safe_json(sandbox, field="sandbox")

    if "instructionSources" in result:
        data["instruction_sources"] = json.dumps(
            list(instruction_sources),
            separators=(",", ":"),
        )

    cli_version = thread.get("cliVersion")
    if cli_version is not None:
        if not isinstance(cli_version, str):
            raise CollectionError("codex thread/start returned invalid thread cliVersion")
        data["cli_version"] = cli_version

    return EvidenceRecord(
        plane="resolved",
        kind="codex.thread",
        source=EvidenceSource(
            collector="codex",
            method="app-server thread/start",
        ),
        data=data,
    )


def _sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()

    try:
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        return None

    return digest.hexdigest()


def _instruction_file_evidence(
    sources: tuple[str, ...],
    *,
    cwd: Path,
) -> EvidenceRecord:
    data: dict[str, JsonScalar] = {
        "source_count": len(sources),
    }

    for source in sources:
        reported_path = Path(source).expanduser()
        observed_path = reported_path if reported_path.is_absolute() else cwd / reported_path
        fingerprint = _sha256_file(observed_path)
        data[f"source:{source}"] = (
            f"sha256:{fingerprint}" if fingerprint is not None else "unavailable"
        )

    return EvidenceRecord(
        plane="live",
        kind="codex.instructions",
        source=EvidenceSource(
            collector="filesystem",
            method="sha256 Codex thread instructionSources",
        ),
        data=data,
    )


def _optional_string(
    payload: dict[str, object],
    field: str,
    *,
    context: str,
) -> str | None:
    value = payload.get(field)
    if value is not None and not isinstance(value, str):
        raise CollectionError(f"{context} returned invalid {field}")
    return value


def _mcp_server_data(
    server: dict[str, object],
    *,
    data: dict[str, JsonScalar],
    seen_names: set[str],
) -> None:
    name = server.get("name")
    if not isinstance(name, str) or not name:
        raise CollectionError("codex mcpServerStatus/list returned invalid server name")
    if name in seen_names:
        raise CollectionError(f"codex mcpServerStatus/list returned duplicate server {name!r}")
    seen_names.add(name)

    runtime_status = _optional_string(
        server,
        "runtimeStatus",
        context="codex mcpServerStatus/list",
    )
    plugin_id = _optional_string(
        server,
        "pluginId",
        context="codex mcpServerStatus/list",
    )
    http_origin = _optional_string(
        server,
        "httpOrigin",
        context="codex mcpServerStatus/list",
    )

    auth_status = server.get("authStatus")
    if not isinstance(auth_status, str):
        raise CollectionError("codex mcpServerStatus/list returned invalid authStatus")

    tools = server.get("tools")
    if not isinstance(tools, dict) or not all(isinstance(key, str) for key in tools):
        raise CollectionError("codex mcpServerStatus/list returned invalid tools catalog")

    tools_error = server.get("toolsError")
    if tools_error is not None and not isinstance(tools_error, str):
        raise CollectionError("codex mcpServerStatus/list returned invalid toolsError")

    tool_names = sorted(tools)
    canonical_tools = json.dumps(
        tools,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    catalog_hash = hashlib.sha256(canonical_tools).hexdigest()
    prefix = f"server:{name}"

    data[f"{prefix}:runtime_status"] = runtime_status
    data[f"{prefix}:auth_status"] = auth_status
    data[f"{prefix}:plugin_id"] = plugin_id
    data[f"{prefix}:http_origin"] = http_origin
    data[f"{prefix}:tool_count"] = len(tool_names)
    data[f"{prefix}:tools"] = json.dumps(tool_names, separators=(",", ":"))
    data[f"{prefix}:tool_catalog_status"] = (
        "error" if tools_error is not None else "available"
    )
    data[f"{prefix}:tool_catalog_sha256"] = f"sha256:{catalog_hash}"


def _query_mcp_evidence(
    stdin: TextIO,
    output: queue.Queue[str | None],
    *,
    thread_id: str,
    deadline: float,
) -> EvidenceRecord:
    data: dict[str, JsonScalar] = {}
    seen_names: set[str] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = None
    request_id = 4

    while True:
        params: dict[str, object] = {
            "limit": 100,
            "detail": "toolsAndAuthOnly",
            "threadId": thread_id,
        }
        if cursor is not None:
            params["cursor"] = cursor

        _send_message(
            stdin,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "mcpServerStatus/list",
                "params": params,
            },
        )
        result = _read_response(output, request_id=request_id, deadline=deadline)
        request_id += 1

        servers = result.get("data")
        if not isinstance(servers, list):
            raise CollectionError("codex mcpServerStatus/list returned no data array")

        for server in servers:
            if not isinstance(server, dict):
                raise CollectionError(
                    "codex mcpServerStatus/list returned a non-object server"
                )
            _mcp_server_data(
                server,
                data=data,
                seen_names=seen_names,
            )

        next_cursor = result.get("nextCursor")
        if next_cursor is None:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise CollectionError("codex mcpServerStatus/list returned invalid nextCursor")
        if next_cursor in seen_cursors:
            raise CollectionError("codex mcpServerStatus/list repeated a pagination cursor")

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    data["server_count"] = len(seen_names)
    return EvidenceRecord(
        plane="live",
        kind="codex.mcp",
        source=EvidenceSource(
            collector="codex",
            method="app-server mcpServerStatus/list",
        ),
        data=data,
    )


def _query_codex_state(
    binary: Path,
    cwd: Path,
    *,
    timeout: float,
    resolve_thread: bool,
    resolve_mcp: bool,
) -> tuple[
    dict[str, object],
    EvidenceRecord | None,
    tuple[str, ...] | None,
    EvidenceRecord | None,
]:
    try:
        process = subprocess.Popen(
            [str(binary), "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise CollectionError(f"could not start codex app-server: {exc}") from exc

    if process.stdin is None or process.stdout is None:
        _stop_process(process)
        raise CollectionError("codex app-server stdio was not available")

    output: queue.Queue[str | None] = queue.Queue()
    reader = threading.Thread(
        target=_reader,
        args=(process.stdout, output),
        daemon=True,
        name="runtimetruth-codex-stdout",
    )
    reader.start()
    deadline = time.monotonic() + timeout

    try:
        _send_message(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "runtimetruth",
                        "version": "0.0.1",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                    },
                },
            },
        )
        _read_response(output, request_id=1, deadline=deadline)

        _send_message(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "method": "initialized",
            },
        )
        _send_message(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "config/read",
                "params": {
                    "includeLayers": False,
                    "cwd": str(cwd),
                },
            },
        )
        config_result = _read_response(output, request_id=2, deadline=deadline)
        config = config_result.get("config")
        if not isinstance(config, dict):
            raise CollectionError("codex config/read returned no config object")

        thread_evidence: EvidenceRecord | None = None
        instruction_sources: tuple[str, ...] | None = None
        mcp_evidence: EvidenceRecord | None = None
        if resolve_thread or resolve_mcp:
            _send_message(
                process.stdin,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "thread/start",
                    "params": {
                        "cwd": str(cwd),
                        "ephemeral": True,
                    },
                },
            )
            thread_result = _read_response(output, request_id=3, deadline=deadline)
            instruction_sources = _instruction_sources(thread_result)
            thread_evidence = _thread_evidence(
                thread_result,
                instruction_sources=instruction_sources,
            )

            if resolve_mcp:
                mcp_evidence = _query_mcp_evidence(
                    process.stdin,
                    output,
                    thread_id=_thread_id(thread_result),
                    deadline=deadline,
                )

        return config, thread_evidence, instruction_sources, mcp_evidence
    finally:
        with contextlib.suppress(OSError):
            process.stdin.close()
        _stop_process(process)


def collect_codex_runtime(
    cwd: str,
    *,
    codex_binary: str | None = None,
    timeout: float = 5.0,
    resolve_thread: bool = False,
    resolve_mcp: bool = False,
) -> tuple[EvidenceRecord, ...]:
    """Collect Codex runtime/config evidence and optional effective runtime state."""
    requested_cwd = Path(cwd).expanduser()
    if not requested_cwd.exists():
        raise CollectionError(f"Codex working directory does not exist: {cwd!r}")
    if not requested_cwd.is_dir():
        raise CollectionError(f"Codex working directory is not a directory: {cwd!r}")

    resolved_cwd = requested_cwd.resolve()
    binary = _resolve_codex_binary(codex_binary)
    version = _run_codex_version(binary, timeout=timeout)
    config, thread, instruction_sources, mcp = _query_codex_state(
        binary,
        resolved_cwd,
        timeout=timeout,
        resolve_thread=resolve_thread,
        resolve_mcp=resolve_mcp,
    )

    config_data: dict[str, JsonScalar] = {
        "cwd": str(resolved_cwd),
    }
    for field in _SAFE_CONFIG_FIELDS:
        if field not in config:
            continue
        config_data[field] = _safe_config_value(field, config[field])

    runtime = EvidenceRecord(
        plane="live",
        kind="codex.runtime",
        source=EvidenceSource(
            collector="codex",
            method="codex --version",
        ),
        data={
            "binary": str(binary),
            "version": version,
        },
    )
    effective_config = EvidenceRecord(
        plane="resolved",
        kind="codex.config",
        source=EvidenceSource(
            collector="codex",
            method="app-server config/read",
        ),
        data=config_data,
    )

    records = [runtime, effective_config]
    if thread is not None:
        records.append(thread)
        records.append(
            _instruction_file_evidence(
                instruction_sources or (),
                cwd=resolved_cwd,
            )
        )
    if mcp is not None:
        records.append(mcp)
    return tuple(records)
