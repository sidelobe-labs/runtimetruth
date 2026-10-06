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


def _query_effective_config(
    binary: Path,
    cwd: Path,
    *,
    timeout: float,
) -> dict[str, object]:
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
        result = _read_response(output, request_id=2, deadline=deadline)
    finally:
        with contextlib.suppress(OSError):
            process.stdin.close()
        _stop_process(process)

    config = result.get("config")
    if not isinstance(config, dict):
        raise CollectionError("codex config/read returned no config object")
    return config


def _safe_config_value(field: str, value: object) -> JsonScalar:
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if field == "approval_policy" and isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    raise CollectionError(f"codex config/read returned unsupported value type for {field!r}")


def collect_codex_runtime(
    cwd: str,
    *,
    codex_binary: str | None = None,
    timeout: float = 5.0,
) -> tuple[EvidenceRecord, EvidenceRecord]:
    """Collect live Codex identity and its effective config for one working directory."""
    requested_cwd = Path(cwd).expanduser()
    if not requested_cwd.exists():
        raise CollectionError(f"Codex working directory does not exist: {cwd!r}")
    if not requested_cwd.is_dir():
        raise CollectionError(f"Codex working directory is not a directory: {cwd!r}")

    resolved_cwd = requested_cwd.resolve()
    binary = _resolve_codex_binary(codex_binary)
    version = _run_codex_version(binary, timeout=timeout)
    config = _query_effective_config(binary, resolved_cwd, timeout=timeout)

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
    return runtime, effective_config
