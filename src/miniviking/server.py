from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .config import ServerConfig
from .openai import (
    ApiError,
    chat_completion_response,
    embeddings_response,
    error_payload,
    normalize_messages,
    validate_json_content,
    wants_json_response,
)
from .runtime import Runtime, estimate_tokens


class MinivikingServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], config: ServerConfig, runtime: Runtime) -> None:
        super().__init__(server_address, MinivikingHandler)
        self.config = config
        self.runtime = runtime


class MinivikingHandler(BaseHTTPRequestHandler):
    server: MinivikingServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/health":
                self._write_json(
                    {
                        "status": "ok",
                        "mode": self.server.config.mode,
                        "base_url": self.server.config.base_url,
                    }
                )
                return
            if path == "/v1/models":
                self._write_json(self._models_payload())
                return
            raise ApiError(404, "not found", "not_found")
        except ApiError as exc:
            self._write_json(error_payload(exc.message, exc.error_type), exc.status)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
            path = urlsplit(self.path).path
            if path == "/v1/chat/completions":
                self._handle_chat_completions(payload)
                return
            if path == "/v1/embeddings":
                self._handle_embeddings(payload)
                return
            raise ApiError(404, "not found", "not_found")
        except ApiError as exc:
            self._write_json(error_payload(exc.message, exc.error_type), exc.status)
        except ValueError as exc:
            self._write_json(error_payload(str(exc)), HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._write_json(error_payload(str(exc), "server_error"), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_chat_completions(self, payload: dict[str, Any]) -> None:
        if not self.server.config.llm_enabled:
            raise ApiError(404, "LLM serving is disabled", "not_found")
        if payload.get("stream") is True:
            raise ApiError(400, "streaming chat completions are not supported yet")

        messages = normalize_messages(payload.get("messages"))
        result = self.server.runtime.chat(messages, payload)
        if wants_json_response(payload):
            validate_json_content(result.content)
        self._write_json(
            chat_completion_response(
                model=self.server.config.models.llm_model,
                content=result.content,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
        )

    def _handle_embeddings(self, payload: dict[str, Any]) -> None:
        if not self.server.config.embedding_enabled:
            raise ApiError(404, "embedding serving is disabled", "not_found")
        raw_input = payload.get("input")
        if isinstance(raw_input, str):
            inputs = [raw_input]
        elif isinstance(raw_input, list) and all(isinstance(item, str) for item in raw_input):
            inputs = raw_input
        else:
            raise ApiError(400, "input must be a string or list of strings")
        if not inputs:
            raise ApiError(400, "input must not be empty")

        embeddings = self.server.runtime.embed(inputs)
        self._write_json(
            embeddings_response(
                model=self.server.config.models.embedding_model,
                embeddings=embeddings,
                prompt_tokens=sum(estimate_tokens(item) for item in inputs),
            )
        )

    def _models_payload(self) -> dict[str, Any]:
        data: list[dict[str, Any]] = []
        if self.server.config.llm_enabled:
            data.append(
                {
                    "id": self.server.config.models.llm_model,
                    "object": "model",
                    "owned_by": "miniviking",
                }
            )
        if self.server.config.embedding_enabled:
            data.append(
                {
                    "id": self.server.config.models.embedding_model,
                    "object": "model",
                    "owned_by": "miniviking",
                }
            )
        return {"object": "list", "data": data}

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ApiError(400, "request body is required")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ApiError(400, f"invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "request body must be a JSON object")
        return payload

    def _write_json(self, payload: dict[str, Any], status: int | HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(config: ServerConfig, runtime: Runtime) -> None:
    runtime.load()
    httpd = MinivikingServer((config.host, config.port), config, runtime)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
