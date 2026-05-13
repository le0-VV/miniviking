from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ServerConfig


@dataclass(frozen=True)
class ServerTestCheck:
    name: str
    ok: bool
    detail: str


class ServerTestError(RuntimeError):
    pass


def run_server_tests(
    config: ServerConfig,
    *,
    base_url: str | None = None,
    timeout: float = 30.0,
    check_chat: bool = True,
    check_embeddings: bool = True,
) -> list[ServerTestCheck]:
    client = ServerTestClient((base_url or config.base_url).rstrip("/"), timeout)
    checks = [
        _check_health(client),
        _check_models(client, config),
    ]
    if check_chat and config.llm_enabled:
        checks.append(_check_chat(client, config))
    if check_embeddings and config.embedding_enabled:
        checks.append(_check_embeddings(client, config))
    return checks


class ServerTestClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.root_url = base_url.removesuffix("/v1")
        self.timeout = timeout

    def get_root(self, path: str) -> dict[str, Any]:
        with urlopen(f"{self.root_url}{path}", timeout=self.timeout) as response:
            return _read_json(response.read())

    def get(self, path: str) -> dict[str, Any]:
        with urlopen(f"{self.base_url}{path}", timeout=self.timeout) as response:
            return _read_json(response.read())

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            return _read_json(response.read())


def _check_health(client: ServerTestClient) -> ServerTestCheck:
    try:
        payload = client.get_root("/health")
        if payload.get("status") != "ok":
            return ServerTestCheck("health", False, f"unexpected status payload: {payload!r}")
        return ServerTestCheck("health", True, "server is ready")
    except (HTTPError, URLError, TimeoutError, ServerTestError) as exc:
        return ServerTestCheck("health", False, str(exc))


def _check_models(client: ServerTestClient, config: ServerConfig) -> ServerTestCheck:
    try:
        payload = client.get("/models")
        model_ids = {item.get("id") for item in payload.get("data", []) if isinstance(item, dict)}
        expected: set[str] = set()
        if config.llm_enabled:
            expected.add(config.models.llm_model)
        if config.embedding_enabled:
            expected.add(config.models.embedding_model)
        missing = expected - model_ids
        if missing:
            return ServerTestCheck("models", False, f"missing models: {', '.join(sorted(missing))}")
        return ServerTestCheck("models", True, f"found {len(model_ids)} model(s)")
    except (HTTPError, URLError, TimeoutError, ServerTestError) as exc:
        return ServerTestCheck("models", False, str(exc))


def _check_chat(client: ServerTestClient, config: ServerConfig) -> ServerTestCheck:
    try:
        payload = client.post(
            "/chat/completions",
            {
                "model": config.models.llm_model,
                "temperature": config.generation.temperature,
                "max_tokens": min(128, config.generation.max_tokens),
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": 'Return exactly this JSON object: {"miniviking_test": true}',
                    }
                ],
            },
        )
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if parsed.get("miniviking_test") is not True:
            return ServerTestCheck("chat", False, f"unexpected JSON content: {content}")
        return ServerTestCheck("chat", True, "JSON chat completion succeeded")
    except (KeyError, TypeError, json.JSONDecodeError, HTTPError, URLError, TimeoutError, ServerTestError) as exc:
        return ServerTestCheck("chat", False, str(exc))


def _check_embeddings(client: ServerTestClient, config: ServerConfig) -> ServerTestCheck:
    try:
        payload = client.post(
            "/embeddings",
            {
                "model": config.models.embedding_model,
                "input": ["miniviking test"],
            },
        )
        embedding = payload["data"][0]["embedding"]
        if not isinstance(embedding, list) or not embedding:
            return ServerTestCheck("embeddings", False, "embedding was empty or not a list")
        if len(embedding) != config.models.embedding_dimensions:
            return ServerTestCheck(
                "embeddings",
                False,
                f"expected {config.models.embedding_dimensions} dimensions, got {len(embedding)}",
            )
        return ServerTestCheck("embeddings", True, f"{len(embedding)}-dimension embedding succeeded")
    except (KeyError, TypeError, HTTPError, URLError, TimeoutError, ServerTestError) as exc:
        return ServerTestCheck("embeddings", False, str(exc))


def _read_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ServerTestError(f"invalid JSON response: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ServerTestError("response was not a JSON object")
    return payload
