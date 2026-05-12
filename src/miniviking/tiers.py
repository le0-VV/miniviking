from __future__ import annotations

from dataclasses import dataclass

GIB = 1024**3


@dataclass(frozen=True)
class RuntimeDefaults:
    name: str
    min_memory_gib: int
    embedding_model: str
    llm_model: str
    llm_backend: str
    embedding_dimensions: int
    max_kv_size: int
    max_prompt_tokens: int
    max_tokens: int
    embedding_batch_size: int
    warning: str | None = None


SMALL_WARNING = (
    "This 8 GB unified-memory setup is supported for local experiments, but it is "
    "not ideal for reliable OpenViking memory ingestion. Prefer a provider API "
    "such as OpenAI for the LLM when reliability matters."
)


SMALL = RuntimeDefaults(
    name="small",
    min_memory_gib=0,
    embedding_model="mlx-community/embeddinggemma-300m-4bit",
    llm_model="mlx-community/Llama-3.2-1B-Instruct-4bit",
    llm_backend="mlx-lm",
    embedding_dimensions=768,
    max_kv_size=1024,
    max_prompt_tokens=2048,
    max_tokens=512,
    embedding_batch_size=2,
    warning=SMALL_WARNING,
)

MEDIUM = RuntimeDefaults(
    name="medium",
    min_memory_gib=12,
    embedding_model="mlx-community/embeddinggemma-300m-8bit",
    llm_model="mlx-community/gemma-4-e2b-it-4bit",
    llm_backend="mlx-vlm",
    embedding_dimensions=768,
    max_kv_size=2048,
    max_prompt_tokens=4096,
    max_tokens=768,
    embedding_batch_size=4,
)

LARGE = RuntimeDefaults(
    name="large",
    min_memory_gib=17,
    embedding_model="mlx-community/embeddinggemma-300m-bf16",
    llm_model="mlx-community/gemma-4-e4b-it-4bit",
    llm_backend="mlx-vlm",
    embedding_dimensions=768,
    max_kv_size=4096,
    max_prompt_tokens=8192,
    max_tokens=1024,
    embedding_batch_size=8,
)


def unified_memory_gib(byte_count: int) -> int:
    return max(1, round(byte_count / GIB))


def defaults_for_memory(memory_gib: int) -> RuntimeDefaults:
    if memory_gib > 16:
        return LARGE
    if memory_gib >= 12:
        return MEDIUM
    return SMALL
