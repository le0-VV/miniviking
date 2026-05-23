from __future__ import annotations

import json
from typing import Any

from .config import ServerConfig

LOCAL_API_KEY = "local"


def openviking_config(config: ServerConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if config.embedding_enabled:
        payload["embedding"] = {
            "max_input_tokens": config.embedding.max_input_tokens,
            "dense": {
                "provider": "openai",
                "api_base": config.base_url,
                "api_key": LOCAL_API_KEY,
                "model": config.models.embedding_model,
                "dimension": config.models.embedding_dimensions,
                "input": "text",
                "batch_size": config.embedding.batch_size,
            },
        }
    if config.llm_enabled:
        payload["vlm"] = {
            "provider": "openai",
            "api_base": config.base_url,
            "api_key": LOCAL_API_KEY,
            "model": config.models.llm_model,
            "max_tokens": config.generation.max_tokens,
        }
    return payload


def openviking_config_json(config: ServerConfig) -> str:
    return json.dumps(openviking_config(config), indent=2)
