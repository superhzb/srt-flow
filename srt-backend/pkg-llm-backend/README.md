# pkg-llm-backend

Internal package: one OpenAI-client `LLMBackend` implementation (matching
`pkg_translator.translator.LLMBackend`), parameterized by a `LLMBackendConfig`
that carries `base_url` / `model` / `api_key` (or `api_key_env`) / `project` /
`extra_body`. This is the union of what used to be two separate worker
adapters (`srt-cloud-worker` for DeepSeek, `srt-mlx-worker` for the local
mlx-platform gateway) — both are the same OpenAI client differing only by
config.

`load_backends()` builds the registry of available backend rows from the
`LLM_BACKENDS` env var (comma-separated ids, e.g. `mlx,cloud`). Cloud deploy
sets `LLM_BACKENDS=cloud`; local dev/test additionally enables `mlx`.
