"""Agent-aware evidence collection for the Codex CLI runtime."""

from __future__ import annotations

import contextlib
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


def _thread_evidence(result: dict[str, object]) -> EvidenceRecord:
    thread = result.get("thread")
    if not isinstance(thread, dict):
        raise CollectionError("codex thread/start returned no thread object")

    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise CollectionError("codex thread/start returned no thread id")

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

    instruction_sources = result.get("instructionSources")
    if instruction_sources is not None:
        if not isinstance(instruction_sources, list) or not all(
            isinstance(item, str) for item in instruction_sources
        ):
            raise CollectionError("codex thread/start returned invalid instructionSources")
        data["instruction_sources"] = json.dumps(
            instruction_sources,
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


def _query_codex_state(
    binary: Path,
    cwd: Path,
    *,
    timeout: float,
    resolve_thread: bool,
) -> tuple[dict[str, object], EvidenceRecord | None]:
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
        if resolve_thread:
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
            thread_evidence = _thread_evidence(thread_result)

        return config, thread_evidence
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
) -> tuple[EvidenceRecord, ...]:
    """Collect Codex runtime/config evidence and optional effective thread state."""
    requested_cwd = Path(cwd).expanduser()
    if not requested_cwd.exists():
        raise CollectionError(f"Codex working directory does not exist: {cwd!r}")
    if not requested_cwd.is_dir():
        raise CollectionError(f"Codex working directory is not a directory: {cwd!r}")

    resolved_cwd = requested_cwd.resolve()
    binary = _resolve_codex_binary(codex_binary)
    version = _run_codex_version(binary, timeout=timeout)
    config, thread = _query_codex_state(
        binary,
        resolved_cwd,
        timeout=timeout,
        resolve_thread=resolve_thread,
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
    return tuple(records)
