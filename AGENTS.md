# AGENTS

## Codebase Map

- `srt-backend/`: FastAPI app + uv workspace. It mounts backend package routers under `/api`
  and calls `pkg_translator.translate_segments` in-process (no worker services).
- `srt-backend/pkg-auth/`: auth routes, Google OAuth, dev auth, and `UserStore` protocol.
- `srt-backend/pkg-billing/`: billing/quota routes, Stripe helpers, and billing store protocol.
- `srt-backend/pkg-file-upload/`: storage protocol and local filesystem storage.
- `srt-backend/pkg-job-orch/`: job database, queue orchestration, in-process LLM backend
  registry, and download routes.
- `srt-backend/pkg-llm-backend/`: one OpenAI-client `LLMBackend` (cloud DeepSeek or local
  mlx-platform gateway, config-driven) + the `LLM_BACKENDS` registry.
- `srt-backend/pkg-notification/`: notification abstraction.
- `srt-backend/pkg-srt-services/`: SRT parse/serialize utilities.
- `srt-backend/pkg-translator/`: translation prompts, language catalog, batching, and validation.
- `srt-frontend/`: Vite + React + TypeScript app.

## Commands

- Install everything with `make install`.
- Run the full local stack with `make dev`.
- Run CI-equivalent validation with `make check`.
- Narrow loops: `make lint`, `make typecheck`, `make test`, `make build`.

## Repository Constraints

- `srt-backend` is a uv workspace; `srt-frontend` is the separate npm project.
- Choosing the `mlx` (local) vs. `cloud` (DeepSeek) translation backend is an
  `LLM_BACKENDS` config decision — never fork business logic per backend.
- Keep package-specific rules in nested `AGENTS.md` files authoritative for
  their package.
- Public API for backend packages lives in `api.py`; tests should prefer the
  public package API instead of internals.
- Library code must not print to stdout or stderr. Use module loggers without
  configuring handlers in libraries.
- Keep secrets out of source and logs.

## Code Discovery

This project uses `codebase-memory-mcp` to maintain a knowledge graph. Prefer
graph tools over grep/glob/file search for code discovery:

1. `search_graph` for functions, classes, routes, variables, and natural-language discovery.
2. `trace_path` for caller/callee relationships when available.
3. `get_code_snippet` for exact function/class source after finding the qualified name.
4. `query_graph` for complex structural queries.
5. `get_architecture` for high-level summaries when available.

Fall back to text search for string literals, config files, non-code files, or
when the graph is incomplete.
