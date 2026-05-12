# Project Memory

- Project name: `miniviking`.
- Purpose: tiny local MLX runtime for OpenViking that hosts an LLM, an embedding model, or both.
- It must integrate out of the box with a stock OpenViking install by matching the server input/output that OpenViking expects.
- It should be installable with a macOS LaunchAgent so the MLX server starts with macOS and eagerly loads configured models at startup instead of loading them just-in-time on first request.
- Installer should detect host unified memory and choose defaults:
  - 8 GB unified memory: embedding `mlx-community/embeddinggemma-300m-4bit`, LLM `mlx-community/Llama-3.2-1B-Instruct-4bit`; installer should warn this setup is not ideal and recommend provider APIs such as OpenAI for more reliable LLM ingestion.
  - 12 GB to 16 GB unified memory: embedding `mlx-community/embeddinggemma-300m-8bit`, LLM `mlx-community/gemma-4-e2b-it-4bit`.
  - More than 16 GB unified memory: embedding `mlx-community/embeddinggemma-300m-bf16`, LLM `mlx-community/gemma-4-e4b-it-4bit`.
- LLM inference should enforce JSON structured responses, use a reliability-focused system prompt, and use low or zero temperature for consistency.
- Remaining runtime configuration for both LLM and embeddings should balance performance, accuracy, and low memory usage, with settings adjusted by system memory budget and discussed before implementation.
