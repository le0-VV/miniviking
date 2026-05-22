from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .memory_adapter import default_memory_adapter_enabled
from .tiers import RuntimeDefaults

RuntimeMode = Literal["llm", "embedding", "both"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8745
CONFIG_DIR = Path.home() / ".miniviking"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass(frozen=True)
class ModelConfig:
    embedding_model: str
    llm_model: str
    llm_backend: str
    embedding_dimensions: int


@dataclass(frozen=True)
class GenerationConfig:
    temperature: float
    max_kv_size: int
    max_prompt_tokens: int
    max_tokens: int
    openviking_memory_adapter: bool


@dataclass(frozen=True)
class EmbeddingConfig:
    batch_size: int
    normalize: bool
    max_input_tokens: int


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    mode: RuntimeMode
    tier: str
    models: ModelConfig
    generation: GenerationConfig
    embedding: EmbeddingConfig

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    @property
    def llm_enabled(self) -> bool:
        return self.mode in {"llm", "both"}

    @property
    def embedding_enabled(self) -> bool:
        return self.mode in {"embedding", "both"}


def config_from_defaults(
    defaults: RuntimeDefaults,
    *,
    mode: RuntimeMode = "both",
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ServerConfig:
    return ServerConfig(
        host=host,
        port=port,
        mode=mode,
        tier=defaults.name,
        models=ModelConfig(
            embedding_model=defaults.embedding_model,
            llm_model=defaults.llm_model,
            llm_backend=defaults.llm_backend,
            embedding_dimensions=defaults.embedding_dimensions,
        ),
        generation=GenerationConfig(
            temperature=0.0,
            max_kv_size=defaults.max_kv_size,
            max_prompt_tokens=defaults.max_prompt_tokens,
            max_tokens=defaults.max_tokens,
            openviking_memory_adapter=default_memory_adapter_enabled(defaults.llm_model, defaults.llm_backend),
        ),
        embedding=EmbeddingConfig(
            batch_size=defaults.embedding_batch_size,
            normalize=True,
            max_input_tokens=4096,
        ),
    )


def _read_runtime_mode(value: str) -> RuntimeMode:
    if value not in {"llm", "embedding", "both"}:
        raise ValueError("mode must be one of: llm, embedding, both")
    return value  # type: ignore[return-value]


def _read_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def load_config(path: Path = CONFIG_PATH) -> ServerConfig:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return config_from_payload(payload)


def config_from_payload(payload: dict[str, object]) -> ServerConfig:
    models = payload.get("models")
    generation = payload.get("generation")
    embedding = payload.get("embedding")
    if not isinstance(models, dict) or not isinstance(generation, dict) or not isinstance(embedding, dict):
        raise ValueError("config must contain models, generation, and embedding objects")

    llm_model = str(models["llm_model"])
    llm_backend = str(models.get("llm_backend") or _infer_llm_backend(llm_model))
    openviking_memory_adapter = generation.get("openviking_memory_adapter")
    if openviking_memory_adapter is None:
        openviking_memory_adapter = default_memory_adapter_enabled(llm_model, llm_backend)

    return ServerConfig(
        host=str(payload.get("host", DEFAULT_HOST)),
        port=int(payload.get("port", DEFAULT_PORT)),
        mode=_read_runtime_mode(str(payload.get("mode", "both"))),
        tier=str(payload.get("tier", "custom")),
        models=ModelConfig(
            embedding_model=str(models["embedding_model"]),
            llm_model=llm_model,
            llm_backend=llm_backend,
            embedding_dimensions=int(models["embedding_dimensions"]),
        ),
        generation=GenerationConfig(
            temperature=float(generation.get("temperature", 0.0)),
            max_kv_size=int(generation["max_kv_size"]),
            max_prompt_tokens=int(generation["max_prompt_tokens"]),
            max_tokens=int(generation["max_tokens"]),
            openviking_memory_adapter=_read_bool(openviking_memory_adapter),
        ),
        embedding=EmbeddingConfig(
            batch_size=int(embedding["batch_size"]),
            normalize=bool(embedding.get("normalize", True)),
            max_input_tokens=int(embedding["max_input_tokens"]),
        ),
    )


def write_config(config: ServerConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(config), fh, indent=2)
        fh.write("\n")


def config_path_from_env() -> Path:
    value = os.environ.get("MINIVIKING_CONFIG")
    return Path(value).expanduser() if value else CONFIG_PATH


def _infer_llm_backend(model_id: str) -> str:
    return "mlx-vlm" if "gemma-4-" in model_id.lower() else "mlx-lm"
