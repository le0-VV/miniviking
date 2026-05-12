from __future__ import annotations

import json
import time
import uuid
from typing import Any

JSON_SYSTEM_PROMPT = (
    "You are miniviking, a local model serving OpenViking memory ingestion. "
    "Follow the caller's schema exactly. When JSON is requested, return only "
    "valid JSON with no markdown fences, prose, comments, or trailing text."
)


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str, error_type: str = "invalid_request_error") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.error_type = error_type


def error_payload(message: str, error_type: str = "invalid_request_error") -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type, "param": None, "code": None}}


def normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
            else:
                raise ApiError(400, "miniviking only supports text chat content")
        return "\n".join(parts)
    raise ApiError(400, "message content must be a string or text content parts")


def normalize_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list) or not messages:
        raise ApiError(400, "messages must be a non-empty list")

    normalized = [{"role": "system", "content": JSON_SYSTEM_PROMPT}]
    for message in messages:
        if not isinstance(message, dict):
            raise ApiError(400, "each message must be an object")
        role = str(message.get("role", "user"))
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            raise ApiError(400, f"unsupported message role: {role}")
        normalized.append({"role": "system" if role == "developer" else role, "content": normalize_message_content(message.get("content", ""))})
    return normalized


def wants_json_response(payload: dict[str, Any]) -> bool:
    response_format = payload.get("response_format")
    if isinstance(response_format, dict):
        return response_format.get("type") in {"json_object", "json_schema"}
    return False


def validate_json_content(content: str) -> None:
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise ApiError(502, f"model did not return valid JSON: {exc.msg}", "model_response_error") from exc


def chat_completion_response(
    *,
    model: str,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def embeddings_response(
    *,
    model: str,
    embeddings: list[list[float]],
    prompt_tokens: int,
) -> dict[str, Any]:
    return {
        "object": "list",
        "model": model,
        "data": [
            {"object": "embedding", "embedding": embedding, "index": index}
            for index, embedding in enumerate(embeddings)
        ],
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
    }
