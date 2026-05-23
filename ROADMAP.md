# miniviking Roadmap

## V1 Internal RC

- [x] Provide OpenAI-compatible localhost endpoints for model listing, chat completions, embeddings, and health.
- [x] Package source-built native executables for the CLI, server, LLM worker, and embedding worker.
- [x] Install as a per-user LaunchAgent or Homebrew service and eagerly download selected models during install.
- [x] Use `mlx-community/embeddinggemma-300m-4bit` for every memory budget.
- [x] Reject local LLM serving below 12 GB unified memory; those hosts are embedding-only/provider-LLM.
- [x] Route Gemma 4 OpenViking memory extraction through the prompt-compaction, JSON repair, and semantic-filter adapter.
- [x] Verify stock OpenViking `0.3.14` default v2 ingestion, memory extraction, vectorization, and retrieval with Gemma E2B.
- [ ] Verify the same stock OpenViking v2 flow with Gemma E4B before declaring the >16 GB tier supported.
- [ ] Verify Homebrew install, runtime bootstrap, service lifecycle, and `miniviking test` from a clean runtime directory.
- [ ] Prepare public release metadata after RC validation: version bump, tag, formula tarball URL, SHA, audit, and release notes.

## Completed Investigation Context

- Low-RAM local LLM candidates below 12 GB did not prove reliable enough for unattended OpenViking memory ingestion.
- Llama 1B/3B, Granite, SmolLM3, Phi, and other small candidates either failed semantic memory quality, schema fidelity, memory headroom, or tokenizer/runtime compatibility.
- Gemma E2B became viable only after prompt compaction plus host-side JSON repair, schema normalization, and semantic filtering.
- Direct `mlx-vlm` schema-constrained decoding remains disabled because the Gemma E2B probe hit an `LLGuidance matcher error`.
