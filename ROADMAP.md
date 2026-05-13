# miniviking Roadmap

## Phase 1: Local OpenViking Runtime

- Provide an OpenAI-compatible localhost API for chat completions, embeddings, and model listing.
- Select default MLX models and memory-safe runtime limits from host unified memory.
- Support `llm`, `embedding`, and `both` runtime modes.
- Install as a per-user macOS LaunchAgent that starts at login and eagerly loads configured models.
- Download and validate model snapshots during install so startup fails fast when dependencies or models are unavailable.
- Keep configuration file based, with host/port/model/runtime settings customizable.
- Publish a Homebrew tap formula that builds the Apple Silicon Rust launcher from source.
