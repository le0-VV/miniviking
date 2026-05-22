from __future__ import annotations

import math
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .config import ServerConfig
from .memory_adapter import finalize_memory_response, maybe_adapt_openviking_memory_request


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_message_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(message["content"]) + 4 for message in messages)


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    completion_tokens: int


class Runtime(Protocol):
    def load(self) -> None:
        ...

    def chat(self, messages: list[dict[str, str]], payload: dict[str, Any]) -> ChatResult:
        ...

    def embed(self, inputs: list[str]) -> list[list[float]]:
        ...


class MlxRuntime:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._llm_model: Any = None
        self._llm_tokenizer: Any = None
        self._llm_processor: Any = None
        self._llm_vlm_config: Any = None
        self._embedding_model: Any = None
        self._embedding_tokenizer: Any = None

    def load(self) -> None:
        if self.config.llm_enabled:
            self._load_llm()
        if self.config.embedding_enabled:
            self._load_embedding_model()

    def _load_llm(self) -> None:
        if self.config.models.llm_backend == "mlx-vlm":
            try:
                from mlx_vlm import load
            except ImportError as exc:
                raise RuntimeError("mlx-vlm is required for Gemma 4 LLM serving") from exc

            self._llm_model, self._llm_processor = load(self.config.models.llm_model)
            self._llm_vlm_config = self._llm_model.config
            return

        try:
            from mlx_lm import load
        except ImportError as exc:
            raise RuntimeError("mlx-lm is required for LLM serving") from exc

        self._llm_model, self._llm_tokenizer = load(self.config.models.llm_model)

    def _load_embedding_model(self) -> None:
        try:
            from mlx_embeddings import load
        except ImportError as exc:
            raise RuntimeError("mlx-embeddings is required for embedding serving") from exc

        self._embedding_model, self._embedding_tokenizer = load(self.config.models.embedding_model)

    def chat(self, messages: list[dict[str, str]], payload: dict[str, Any]) -> ChatResult:
        if self._llm_model is None:
            raise RuntimeError("LLM model is not loaded")

        requested_temperature = float(payload.get("temperature", self.config.generation.temperature))
        if requested_temperature != self.config.generation.temperature:
            raise ValueError("miniviking enforces temperature=0.0 for deterministic OpenViking ingestion")

        max_tokens = int(payload.get("max_tokens") or self.config.generation.max_tokens)
        if max_tokens > self.config.generation.max_tokens:
            raise ValueError(f"max_tokens exceeds configured limit of {self.config.generation.max_tokens}")

        adapter_request = maybe_adapt_openviking_memory_request(
            messages,
            payload,
            model_id=self.config.models.llm_model,
            llm_backend=self.config.models.llm_backend,
            enabled=self.config.generation.openviking_memory_adapter,
        )
        generation_messages = adapter_request.messages if adapter_request is not None else messages

        prompt_tokens = estimate_message_tokens(messages)
        generation_prompt_tokens = estimate_message_tokens(generation_messages)
        if generation_prompt_tokens > self.config.generation.max_prompt_tokens:
            raise ValueError(
                f"prompt has approximately {generation_prompt_tokens} tokens, "
                f"exceeding max_prompt_tokens={self.config.generation.max_prompt_tokens}"
            )

        if self.config.models.llm_backend == "mlx-vlm":
            content = self._chat_with_vlm(generation_messages, max_tokens)
        else:
            content = self._chat_with_lm(generation_messages, max_tokens)

        if adapter_request is not None:
            content = finalize_memory_response(content, adapter_request.transcript)

        return ChatResult(
            content=content.strip(),
            prompt_tokens=prompt_tokens,
            completion_tokens=estimate_tokens(content),
        )

    def _chat_with_lm(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        if self._llm_tokenizer is None:
            raise RuntimeError("mlx-lm tokenizer is not loaded")
        prompt = self._llm_tokenizer.apply_chat_template(messages, add_generation_prompt=True)

        try:
            from mlx_lm import generate
        except ImportError as exc:
            raise RuntimeError("mlx-lm is required for LLM serving") from exc

        content = generate(
            self._llm_model,
            self._llm_tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            max_kv_size=self.config.generation.max_kv_size,
            verbose=False,
        )
        if not isinstance(content, str):
            content = str(content)
        return content

    def _chat_with_vlm(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        if self._llm_processor is None or self._llm_vlm_config is None:
            raise RuntimeError("mlx-vlm processor is not loaded")
        try:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template
        except ImportError as exc:
            raise RuntimeError("mlx-vlm is required for Gemma 4 LLM serving") from exc

        prompt = apply_chat_template(self._llm_processor, self._llm_vlm_config, messages, num_images=0, num_audios=0)
        result = generate(
            self._llm_model,
            self._llm_processor,
            prompt,
            image=None,
            audio=None,
            max_tokens=max_tokens,
            max_kv_size=self.config.generation.max_kv_size,
            temperature=self.config.generation.temperature,
            verbose=False,
        )
        content = getattr(result, "text", result)
        if not isinstance(content, str):
            content = str(content)
        return content

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if self._embedding_model is None or self._embedding_tokenizer is None:
            raise RuntimeError("embedding model is not loaded")

        try:
            import mlx.core as mx
        except ImportError as exc:
            raise RuntimeError("mlx is required for embedding serving") from exc

        vectors: list[list[float]] = []
        for start in range(0, len(inputs), self.config.embedding.batch_size):
            batch = inputs[start : start + self.config.embedding.batch_size]
            encoded = self._embedding_tokenizer(
                batch,
                return_tensors="mlx",
                padding=True,
                truncation=True,
                max_length=self.config.embedding.max_input_tokens,
            )
            outputs = self._call_embedding_model(encoded)
            embeddings = getattr(outputs, "text_embeds", outputs)
            if self.config.embedding.normalize:
                embeddings = embeddings / mx.linalg.norm(embeddings, axis=-1, keepdims=True)
            vectors.extend(embeddings.tolist())
        return vectors

    def _call_embedding_model(self, encoded: Any) -> Any:
        if isinstance(encoded, Mapping):
            payload = dict(encoded)
        elif hasattr(encoded, "data") and isinstance(encoded.data, Mapping):
            payload = dict(encoded.data)
        else:
            return self._embedding_model(encoded)

        signature = inspect.signature(self._embedding_model.__call__)
        if "inputs" in signature.parameters and "input_ids" in payload:
            kwargs = {"inputs": payload["input_ids"]}
            if "attention_mask" in signature.parameters and "attention_mask" in payload:
                kwargs["attention_mask"] = payload["attention_mask"]
            return self._embedding_model(**kwargs)

        return self._embedding_model(**payload)


class DownloadError(RuntimeError):
    pass


def download_models(config: ServerConfig) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise DownloadError("huggingface_hub is required to download models") from exc

    model_ids: list[str] = []
    if config.llm_enabled:
        model_ids.append(config.models.llm_model)
    if config.embedding_enabled:
        model_ids.append(config.models.embedding_model)

    for model_id in model_ids:
        snapshot_download(repo_id=model_id)
