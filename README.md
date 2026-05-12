# miniviking

`miniviking` is a tiny local MLX runtime for OpenViking. It exposes OpenAI-compatible endpoints on localhost so a stock OpenViking installation can use local chat-completion and embedding models with minimal configuration.

Default server:

```text
http://127.0.0.1:8745/v1
```

Core endpoints:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /health`

Install as a per-user LaunchAgent:

```sh
miniviking install
miniviking start
```

Run directly:

```sh
miniviking serve
```

Verify a running server:

```sh
miniviking smoke
```

Print the OpenViking config snippet for the current miniviking config:

```sh
miniviking openviking-config
```

The installer detects host memory and writes a config under `~/.miniviking/config.json`. The port, runtime mode, and models can be customized in that file or with CLI flags during install.

Memory-tier defaults:

| Unified memory | Embedding model | LLM model | Backend |
| --- | --- | --- | --- |
| Less than 12 GB | `mlx-community/embeddinggemma-300m-4bit` | `mlx-community/Llama-3.2-1B-Instruct-4bit` | `mlx-lm` |
| 12 GB to 16 GB | `mlx-community/embeddinggemma-300m-8bit` | `mlx-community/gemma-4-e2b-it-4bit` | `mlx-vlm` |
| More than 16 GB | `mlx-community/embeddinggemma-300m-bf16` | `mlx-community/gemma-4-e4b-it-4bit` | `mlx-vlm` |

Initial context and throughput limits are intentionally below each model's maximum context window:

| Tier | `max_kv_size` | Approx prompt cap | Max output tokens | Embedding batch |
| --- | ---: | ---: | ---: | ---: |
| Small | 1024 | 2048 | 512 | 2 |
| Medium | 2048 | 4096 | 768 | 4 |
| Large | 4096 | 8192 | 1024 | 8 |

OpenViking should point its OpenAI-compatible provider settings at:

```text
api_base = "http://127.0.0.1:8745/v1"
api_key = "unused"
```
