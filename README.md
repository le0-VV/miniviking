# miniviking

[简体中文](README.zh-CN.md)

`miniviking` is a tiny local MLX server for working with OpenViking. It exposes OpenAI-compatible endpoints on localhost so a stock OpenViking installation can use local chat-completion and embedding models with minimal configuration where those local models are enabled.

Default server:

```text
http://127.0.0.1:8745/v1
```

Endpoints:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /health`

## Install

```sh
brew tap le0-VV/miniviking https://github.com/le0-VV/miniviking
brew install le0-VV/miniviking/miniviking
```

The Homebrew formula builds the Rust launcher from source. It does not install
a prebuilt binary and does not create a Python virtualenv during the Homebrew
build; the launcher prepares the Python/MLX runtime under `~/.miniviking/runtime`
when `miniviking install` or the server is first run.

Create the Homebrew service config and download the selected models:

```sh
miniviking install --config "$(brew --prefix)/etc/miniviking/config.json" --skip-launch-agent
```

Start the Homebrew service:

```sh
brew services start miniviking
```

Verify the running server:

```sh
miniviking test --config "$(brew --prefix)/etc/miniviking/config.json"
```

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
miniviking test
```

Print the OpenViking config snippet for the current miniviking config:

```sh
miniviking openviking-config
```

The installer detects host memory and writes a config under `~/.miniviking/config.json`. On machines below 12 GB unified memory, `miniviking install` defaults to `mode=embedding`, downloads only the embedding model, and rejects local LLM modes. Configure OpenViking's LLM provider separately on those machines, for example with an API provider.

The port, runtime mode, and models can be customized in the config file or with CLI flags during install.

Memory-tier defaults:

| Unified memory | Default mode | Embedding model                          | Local LLM default                                  | Backend   |
| -------------- | ------------ | ---------------------------------------- | -------------------------------------------------- | --------- |
| Less than 12 GB | `embedding`  | `mlx-community/embeddinggemma-300m-4bit` | Unsupported; use a separate OpenViking LLM provider | N/A       |
| 12 GB to 16 GB | `both`       | `mlx-community/embeddinggemma-300m-4bit` | `mlx-community/gemma-4-e2b-it-4bit`                | `mlx-vlm` |
| More than 16 GB | `both`      | `mlx-community/embeddinggemma-300m-4bit` | `mlx-community/gemma-4-e4b-it-4bit`                | `mlx-vlm` |

Initial context and throughput limits are intentionally below each model's maximum context window:

| Tier   | `max_kv_size` | Approx prompt cap | Max output tokens | Embedding batch |
| ------ | ------------: | ----------------: | ----------------: | --------------: |
| Small  |          8192 |              8192 |               512 |               2 |
| Medium |          8192 |              8192 |               768 |               4 |
| Large  |          8192 |              8192 |              1024 |               8 |

OpenViking should point its OpenAI-compatible provider settings at:

```text
api_base = "http://127.0.0.1:8745/v1"
api_key = "unused"
```

For the default below-12 GB embedding-only install, `miniviking openviking-config` emits only the embedding provider block. Configure OpenViking's LLM provider separately, for example with an API provider.

On 12 GB or larger hosts, Miniviking detects stock OpenViking v2 memory-extraction requests and compacts them through the Gemma memory adapter before returning OpenViking-compatible memory operations.

Internal RC verification:

```sh
bash scripts/rc_verify.sh
```

## 👉👈

If miniviking helped you in any way, or you're just feeling generous, and you have Alipay, please consider making a small donation to this project. Even 1 fen means a world of encouragement to me.

<img src="assets/support/alipay.jpg" alt="Alipay support QR code" width="180">

Also bro's got no source of income right now 💀. Your donation will help me feed my 2 fur babies: Jessie and Yolo <3

This is completely voluntary. It does not change the license, issue priority, feature priority, or support expectations.

### Jessie and Yolo

| Jessie, first day                                                                      | Jessie                                                        | Also Jessie                                                        |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| <img src="assets/cats/jessie-first-day.jpg" alt="Jessie on her first day" width="220"> | <img src="assets/cats/jessie-1.jpg" alt="Jessie" width="220"> | <img src="assets/cats/jessie-2.jpg" alt="Also Jessie" width="220"> |

| Smol Yolo                                                         | Yolo                                                      | Still Yolo                                                      | Jessie and Yolo                                                                        |
| ----------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| <img src="assets/cats/smol-yolo.jpg" alt="Smol Yolo" width="180"> | <img src="assets/cats/yolo-1.jpg" alt="Yolo" width="180"> | <img src="assets/cats/yolo-2.jpg" alt="Yolo again" width="180"> | <img src="assets/cats/yolo-and-jessie.jpg" alt="Yolo and Jessie together" width="240"> |
