from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .config import CONFIG_PATH, ServerConfig
from .host import detect_unified_memory_gib
from .openai import error_payload
from .runtime import ChatResult, MlxRuntime, Runtime
from .server import serve
from .tiers import MIN_LOCAL_LLM_MEMORY_GIB

SERVER_ROLE = "miniviking-server"
LLM_ROLE = "miniviking-llm"
EMBED_ROLE = "miniviking-embed"

WORKER_HOST = "127.0.0.1"
LLM_WORKER_OFFSET = 1
EMBED_WORKER_OFFSET = 2
WORKER_STARTUP_TIMEOUT_SECONDS = 300.0
WORKER_REQUEST_TIMEOUT_SECONDS = 600.0


def serve_processes(config: ServerConfig, *, config_path: Path = CONFIG_PATH) -> None:
    validate_llm_supported_for_host(config)
    supervisor = WorkerSupervisor(config, config_path=config_path)
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _raise_keyboard_interrupt)
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    try:
        supervisor.start()
        serve(config, supervisor.runtime())
    except KeyboardInterrupt:
        return
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        supervisor.stop()


def serve_llm_worker(config: ServerConfig, *, host: str | None = None, port: int | None = None) -> None:
    validate_llm_supported_for_host(config)
    _serve_worker(
        replace(config, mode="llm"),
        role=LLM_ROLE,
        host=host or WORKER_HOST,
        port=port or llm_worker_port(config),
    )


def _raise_keyboard_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def serve_embedding_worker(config: ServerConfig, *, host: str | None = None, port: int | None = None) -> None:
    _serve_worker(
        replace(config, mode="embedding"),
        role=EMBED_ROLE,
        host=host or WORKER_HOST,
        port=port or embedding_worker_port(config),
    )


def validate_llm_supported_for_host(config: ServerConfig, memory_gib: int | None = None) -> None:
    if not config.llm_enabled:
        return
    detected_memory_gib = memory_gib if memory_gib is not None else detect_unified_memory_gib()
    if detected_memory_gib < MIN_LOCAL_LLM_MEMORY_GIB:
        raise RuntimeError("Local LLM serving is not supported below 12 GB unified memory")


def llm_worker_port(config: ServerConfig) -> int:
    return _worker_port(config, LLM_WORKER_OFFSET)


def embedding_worker_port(config: ServerConfig) -> int:
    return _worker_port(config, EMBED_WORKER_OFFSET)


def _worker_port(config: ServerConfig, offset: int) -> int:
    port = config.port + offset
    if port > 65535:
        raise ValueError("config port is too high to allocate internal miniviking worker ports")
    return port


class WorkerSupervisor:
    def __init__(self, config: ServerConfig, *, config_path: Path = CONFIG_PATH) -> None:
        self.config = config
        self.config_path = config_path
        self._processes: list[WorkerProcess] = []

    def start(self) -> None:
        if self.config.llm_enabled:
            self._processes.append(self._start_worker(LLM_ROLE, llm_worker_port(self.config)))
        if self.config.embedding_enabled:
            self._processes.append(self._start_worker(EMBED_ROLE, embedding_worker_port(self.config)))

        for process in self._processes:
            self._wait_for_worker(process)

    def runtime(self) -> Runtime:
        return WorkerRuntime(
            llm_url=_worker_url(llm_worker_port(self.config)) if self.config.llm_enabled else None,
            embedding_url=_worker_url(embedding_worker_port(self.config)) if self.config.embedding_enabled else None,
        )

    def stop(self) -> None:
        for process in self._processes:
            if process.popen.poll() is None:
                process.popen.terminate()
        for process in self._processes:
            try:
                process.popen.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.popen.kill()
                process.popen.wait(timeout=10)

    def _start_worker(self, role: str, port: int) -> WorkerProcess:
        command = worker_command(role, config_path=self.config_path, host=WORKER_HOST, port=port)
        env = os.environ.copy()
        env["MINIVIKING_PROCESS_ROLE"] = role
        popen = subprocess.Popen(command.args, executable=command.executable, env=env)
        return WorkerProcess(role=role, port=port, popen=popen)

    def _wait_for_worker(self, process: "WorkerProcess") -> None:
        deadline = time.monotonic() + WORKER_STARTUP_TIMEOUT_SECONDS
        health_url = f"{_worker_url(process.port)}/health"
        last_error = "not ready"
        while time.monotonic() < deadline:
            returncode = process.popen.poll()
            if returncode is not None:
                raise RuntimeError(f"{process.role} exited during startup with code {returncode}")
            try:
                with urlopen(health_url, timeout=1) as response:
                    payload = _read_json(response.read())
                if payload.get("status") == "ok" and payload.get("role") == process.role:
                    return
                last_error = f"unexpected health payload: {payload!r}"
            except (OSError, URLError, TimeoutError, HTTPError) as exc:
                last_error = str(exc)
            time.sleep(0.25)
        raise RuntimeError(f"{process.role} did not become ready: {last_error}")


class WorkerRuntime:
    def __init__(self, *, llm_url: str | None, embedding_url: str | None) -> None:
        self.llm_url = llm_url
        self.embedding_url = embedding_url

    def load(self) -> None:
        return

    def chat(self, messages: list[dict[str, str]], payload: dict[str, Any]) -> ChatResult:
        if self.llm_url is None:
            raise RuntimeError("LLM worker is not configured")
        response = _post_json(
            f"{self.llm_url}/chat",
            {"messages": messages, "payload": payload},
            timeout=WORKER_REQUEST_TIMEOUT_SECONDS,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("LLM worker returned an invalid response")
        return ChatResult(
            content=str(result["content"]),
            prompt_tokens=int(result["prompt_tokens"]),
            completion_tokens=int(result["completion_tokens"]),
        )

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if self.embedding_url is None:
            raise RuntimeError("embedding worker is not configured")
        response = _post_json(
            f"{self.embedding_url}/embeddings",
            {"input": inputs},
            timeout=WORKER_REQUEST_TIMEOUT_SECONDS,
        )
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list):
            raise RuntimeError("embedding worker returned an invalid response")
        return embeddings


class WorkerServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int], config: ServerConfig, role: str, runtime: Runtime) -> None:
        super().__init__(server_address, WorkerHandler)
        self.config = config
        self.role = role
        self.runtime = runtime


class WorkerHandler(BaseHTTPRequestHandler):
    server: WorkerServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/health":
                self._write_json({"status": "ok", "role": self.server.role})
                return
            self._write_json(error_payload("not found", "not_found"), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._write_json(error_payload(str(exc), "server_error"), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            path = urlsplit(self.path).path
            if self.server.role == LLM_ROLE and path == "/chat":
                self._handle_chat(payload)
                return
            if self.server.role == EMBED_ROLE and path == "/embeddings":
                self._handle_embeddings(payload)
                return
            self._write_json(error_payload("not found", "not_found"), HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._write_json(error_payload(str(exc)), HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._write_json(error_payload(str(exc), "server_error"), HTTPStatus.INTERNAL_SERVER_ERROR)
        except Exception as exc:
            self._write_json(error_payload(str(exc), "server_error"), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_chat(self, payload: dict[str, Any]) -> None:
        messages = payload.get("messages")
        original_payload = payload.get("payload")
        if not isinstance(messages, list) or not isinstance(original_payload, dict):
            raise ValueError("LLM worker request must contain messages and payload")
        result = self.server.runtime.chat(messages, original_payload)
        self._write_json({"result": asdict(result)})

    def _handle_embeddings(self, payload: dict[str, Any]) -> None:
        inputs = payload.get("input")
        if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
            raise ValueError("embedding worker request input must be a list of strings")
        self._write_json({"embeddings": self.server.runtime.embed(inputs)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("request body is required")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _write_json(self, payload: dict[str, Any], status: int | HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class WorkerCommand:
    def __init__(self, args: list[str], executable: str | None) -> None:
        self.args = args
        self.executable = executable


class WorkerProcess:
    def __init__(self, *, role: str, port: int, popen: subprocess.Popen[bytes]) -> None:
        self.role = role
        self.port = port
        self.popen = popen


def worker_command(role: str, *, config_path: Path, host: str, port: int) -> WorkerCommand:
    role_executable = _role_executable(role)
    if role_executable is not None:
        return WorkerCommand(
            args=[role_executable, "--config", str(config_path), "--host", host, "--port", str(port)],
            executable=None,
        )

    prefix, executable = _miniviking_command_prefix()
    command_args = [role, "--config", str(config_path), "--host", host, "--port", str(port)]
    if executable is not None and len(prefix) == 1:
        return WorkerCommand(args=[role, *command_args], executable=executable)
    return WorkerCommand(args=[*prefix, *command_args], executable=None)


def server_program_arguments(config_path: Path = CONFIG_PATH) -> list[str]:
    role_executable = _role_executable(SERVER_ROLE)
    if role_executable is not None:
        return [role_executable, "--config", str(config_path)]

    prefix, _ = _miniviking_command_prefix()
    return [*prefix, SERVER_ROLE, "--config", str(config_path)]


def _role_executable(role: str) -> str | None:
    override = os.environ.get(_role_env_name(role))
    if override:
        return override

    for anchor in _role_executable_anchors():
        executable = _sibling_role_executable(anchor, role)
        if executable is not None:
            return executable

    executable = shutil.which(role)
    if executable:
        return executable

    return None


def _role_env_name(role: str) -> str:
    suffix = role.removeprefix("miniviking-").upper().replace("-", "_")
    return f"MINIVIKING_{suffix}_BINARY"


def _role_executable_anchors() -> list[Path]:
    anchors: list[Path] = []
    current = Path(sys.executable)
    if current.name in {SERVER_ROLE, LLM_ROLE, EMBED_ROLE, "miniviking"}:
        anchors.append(current)

    override = os.environ.get("MINIVIKING_BINARY")
    if override:
        anchors.append(Path(override))

    miniviking = shutil.which("miniviking")
    if miniviking:
        anchors.append(Path(miniviking))

    return anchors


def _sibling_role_executable(anchor: Path, role: str) -> str | None:
    if anchor.name == role and anchor.is_file():
        return str(anchor)
    candidate = anchor.with_name(role)
    if candidate.is_file():
        return str(candidate)
    return None


def _miniviking_command_prefix() -> tuple[list[str], str | None]:
    override = os.environ.get("MINIVIKING_BINARY")
    if override:
        return [override], override

    if Path(sys.executable).name == "miniviking":
        return [sys.executable], sys.executable

    executable = shutil.which("miniviking")
    if executable:
        return [executable], executable

    return [sys.executable, "-m", "miniviking"], None


def _serve_worker(config: ServerConfig, *, role: str, host: str, port: int) -> None:
    runtime = MlxRuntime(config)
    runtime.load()
    httpd = WorkerServer((host, port), config, role, runtime)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def _worker_url(port: int) -> str:
    return f"http://{WORKER_HOST}:{port}"


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return _read_json(response.read())
    except HTTPError as exc:
        error = _read_json(exc.read())
        message = _error_message(error)
        if exc.code == HTTPStatus.BAD_REQUEST:
            raise ValueError(message) from exc
        raise RuntimeError(message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"worker request failed: {exc}") from exc


def _read_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid worker JSON response: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("worker response must be a JSON object")
    return payload


def _error_message(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return "worker request failed"
