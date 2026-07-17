# srt-flow → mlx-platform Migration + Worker Consolidation

**For:** the srt-flow team
**Goal (Phase A):** stop `srt-mlx-worker` from loading MLX models in-process; make it call the local
`mlx-platform` gateway over HTTP instead. Prompts, batching, validation, and the cloud path do not
change.
**Goal (Phase B):** once both workers are thin OpenAI clients, collapse them into `srt-backend`.
Fold `pkg-translator` in as a workspace member, drop the inter-process HTTP hop, and delete
`srt-cloud-worker` and `srt-mlx-worker`. End state: the repo has **two** projects — `srt-backend`
and `srt-frontend`.
**Companion docs:** platform contract — `../MLX_PLATFORM_ARCHITECTURE_REVIEW.md`; general consumer
guide — `../MLX_PLATFORM_CONSUMER_MIGRATION.md`. This doc is srt-flow-specific and is all you need.

---

## TL;DR

Your codebase already has the exact shape we want. `pkg-translator` defines the `LLMBackend` protocol
and owns every business concern; `srt-cloud-worker` is already a thin OpenAI client pointed at a
remote base URL (DeepSeek). **`srt-mlx-worker` becomes the same thing, pointed at mlx-platform
instead of importing `mlx_lm`.** After that, both workers are identical OpenAI clients differing only
by `base_url`/`model`/`headers`, so the "separate deploy target" boundary that split them no longer
buys anything — collapse it.

- **Phase A** — change **one package**: `srt-mlx-worker`. Rewrite `llm.py`, adjust `config.py`, drop
  the `[mlx]` extra, add `openai`. Do **not** touch `pkg-translator`, `srt-cloud-worker`, or
  `srt-backend` routing. Staging first, verify, then prod.
- **Phase B** — fold `pkg-translator` into `srt-backend` as a workspace member; replace the HTTP
  worker call with an in-process `translate_segments` call driven by an in-process LLM-backend
  registry; delete both worker projects. Cloud deploy configures only the DeepSeek backend; local
  dev/test additionally configures the mlx backend pointed at the Mac gateway (or a tunnel URL for a
  future free tier).

### Deployment topology (the decision that makes Phase B safe)

- **Cloud deploy uses DeepSeek only.** The mlx path never runs in the cloud, so the merged backend
  never needs to reach the Mac gateway from cloud infra.
- **The mlx backend is local dev / local test only** (Mac gateway on loopback). A future free tier
  can point the same backend row at a tunnel URL — a config change, not a code change.

Because the mlx path is never cloud-side, there is no cross-network constraint blocking the merge.
Both "cloud" and "local mlx" become in-process backend rows that differ only by config.

---

## Phase A — point `srt-mlx-worker` at the gateway

### What must NOT change

Keep all of this exactly where it is — it is application-owned and the platform never sees it:

- `pkg-translator`: prompt templates, language config, `make_pair`, batching, `translate_segments`,
  and the JSON-array extraction/validation in `validation.py`.
- Semantic retries and batch splitting on bad model output.
- `srt-cloud-worker` (the DeepSeek path stays as-is).
- `srt-backend` job orchestration, worker routing, and product state.

The platform does **operational** retries only (executor crash, model load). Your **semantic**
retries (invalid JSON, missing items) stay in `pkg-translator` — do not move them.

### The change, file by file (`srt-mlx-worker`)

#### 1. `pyproject.toml` — drop MLX, add openai

Remove the whole `[project.optional-dependencies] mlx = [...]` block (no more `mlx`, `mlx-lm`,
`transformers`). Add `openai` to runtime deps:

```toml
dependencies = [
  "fastapi>=0.116.0",
  "openai>=1.40.0",
  "pkg-translator",
  "pydantic>=2.11.0",
  "uvicorn>=0.35.0",
]
```

This is the point of the migration: after this, nothing in `srt-mlx-worker` imports an MLX library.

#### 2. `config.py` — replace `model_path` with gateway settings

The MLX config currently pins a local model path. Replace it with the gateway base URL, the model
**alias**, and the project header. This resembles `srt-cloud-worker/config.py` but is **not** a
verbatim mirror — two deliberate differences:

- Cloud stores `api_key_env = "DEEPSEEK_API_KEY"` (an env-var *name*, read at call time). On loopback
  the mlx worker instead carries a literal `api_key = "local"` placeholder — no env var involved.
- Cloud has **no** `project` field; the `project` / `X-MLX-Project` attribution field is new here.

Note aliases, **never** model paths (the gateway rejects arbitrary paths).

```python
"""Runtime configuration for translation via mlx-platform."""

import os
from dataclasses import dataclass, field

from pkg_translator.api import TranslationConfig as BaseTranslationConfig


def _default_base_url() -> str:
    # Confirm the port with the mlx-platform team before cutover.
    return os.environ.get("MLX_PLATFORM_BASE_URL", "http://127.0.0.1:5900/v1")


@dataclass(frozen=True)
class TranslationConfig(BaseTranslationConfig):
    model: str = "local-chat"          # mlx-platform alias, from GET /v1/models
    base_url: str = field(default_factory=_default_base_url)
    project: str = "srt-flow"          # sent as X-MLX-Project for attribution
    api_key: str = "local"             # placeholder on loopback; real key once network-exposed
    batch_size: int = 10
    max_tokens: int = 2048
    request_timeout: float = 120.0
```

`temperature` is inherited from `BaseTranslationConfig` (defaults to `0.0`) — keep it there.

#### 3. `llm.py` — replace MLX generation with an OpenAI client

Delete the entire current `llm.py` (the `mlx_lm` load/generate machinery) and replace it with a
client that mirrors `srt-cloud-worker/llm.py`, pointed at the gateway:

```python
"""Text generation via the local mlx-platform gateway."""

import logging

from openai import OpenAI

from .config import TranslationConfig

logger = logging.getLogger(__name__)


def ensure_model_available(config: TranslationConfig) -> None:
    # Cheap reachability + alias check; raises if the gateway is down or the alias is unknown.
    client = _client(config)
    ids = {m.id for m in client.models.list().data}
    if config.model not in ids:
        raise RuntimeError(f"mlx-platform has no model alias {config.model!r}; available: {sorted(ids)}")


def generate_text(prompt: str, config: TranslationConfig) -> str:
    client = _client(config)
    logger.debug("Sending %d chars to mlx-platform alias %s", len(prompt), config.model)
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            stream=False,
        )
    except Exception as exc:
        # Optional: response headers carry X-Request-Id; capture it into your job record if available.
        raise RuntimeError(f"mlx-platform generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RuntimeError("mlx-platform returned empty content")
    return content


def _client(config: TranslationConfig) -> OpenAI:
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.request_timeout,
        default_headers={"X-MLX-Project": config.project},
    )
```

**Critical differences from the cloud worker** — do not copy these DeepSeek-isms:

- **No `extra_body={"thinking": ...}`.** The gateway rejects unsupported parameters with a clear
  validation error rather than silently ignoring them. Send only the documented fields
  (`model`, `messages`, `temperature`, `max_tokens`, `top_p`, `stop`, `stream`, `response_format`).
- **No `DEEPSEEK_API_KEY`.** On loopback the key is the `"local"` placeholder.

`response_format` is **not** required — `pkg-translator/validation.py` already extracts the JSON array
from free-form text, exactly as it does for DeepSeek. Only add `response_format={"type":
"json_object"}` if the platform team confirms the `local-chat` alias supports it and you measure a
parsing benefit.

#### 4. `api.py` — no change needed

`create_app` and the `_MlxBackend` adapter stay exactly as they are. `_MlxBackend` still delegates to
`llm.ensure_model_available` / `llm.generate_text`; those now talk to the gateway. The worker's
public entry point, title, and port are unchanged (the port `5732` lives in `server.py`'s
`WORKER_PORT`, not `api.py`).

> Phase B deletes this file. In Phase A it stays intact so the migration is verifiable in isolation
> (worker still boots, still serves `/translate/stream`) before any consolidation.

#### 5. Delete the old MLX tests, add a fake-transport test

Remove `tests/test_e2e_real_worker.py`'s MLX-model expectations. Your CI must run **without MLX and
without a live gateway** — inject a fake OpenAI transport or monkeypatch `llm._client` to return a
stub that yields a canned JSON-array string, then assert `pkg-translator` parses it. Keep a separate,
opt-in `e2e` test that runs against a real local gateway.

### Configuration & routing (Phase A)

- `srt-backend/.env` keeps `WORKERS=mlx=http://localhost:5732,cloud=http://localhost:5733` — the mlx
  worker still listens on 5732; only its *backend* changed.
- Set `MLX_PLATFORM_BASE_URL` in the mlx-worker's environment (or accept the default). **Confirm the
  gateway port with the mlx-platform team** — the example uses `5900` as a placeholder.
- Ask the platform team to confirm the chat alias name (assumed `local-chat`) is registered in
  `/v1/models`, and request a different alias/revision there if you need one. Never point at a model
  path.

### Verification (Phase A, staging)

Run from `srt-flow-staging/srt-flow`:

1. **Boundary:** `grep -rn "import mlx\|mlx_lm\|mlx\.core" srt-mlx-worker/src` returns nothing.
   (The old `llm.py` loads mlx_lm *lazily* via `importlib.import_module("mlx_lm")`, so there is no
   static `import mlx` line — the `mlx_lm` string match is what the grep relies on. After the rewrite
   both are gone.)
2. **Deps:** `srt-mlx-worker` installs with no `[mlx]` extra; `mlx`/`mlx-lm` are gone from its lock.
3. **Unit/CI (no MLX, no gateway):** `uv run pytest` passes with the fake transport.
4. **Types/lint:** `uv run pyright` and `uv run ruff check` clean.
5. **Live end-to-end:** with mlx-platform running, start the mlx worker on 5732 and drive a real
   translation (see `scripts/drive_translation.py`). Confirm:
   - Output SRT matches a pre-migration baseline on the same input (same alias/model → same behavior).
   - The request shows up in the mlx-platform console History attributed to project `srt-flow`.
   - Killing the gateway mid-job surfaces a clean error and your existing recovery kicks in.
6. **Cloud path still works:** route a job to the `cloud` worker and confirm DeepSeek is untouched.

Only after all six pass on staging, apply the **identical** diff to `srt-flow-prod/srt-flow` and
repeat verification. Do not change prod first.

### Phase A done criteria

- `srt-mlx-worker` neither imports nor spawns MLX; its only inference dependency is `openai`.
- Local translation runs through mlx-platform; the cloud path is unchanged.
- Prompts, batching, validation, and semantic retries remain in `pkg-translator`.
- Staging verified, then prod verified with the same change.

---

## Phase B — collapse to two projects (`srt-backend` + `srt-frontend`)

**Do Phase A first and let it settle.** Phase A is what makes both workers thin OpenAI clients;
Phase B is only safe once neither worker holds any MLX-specific dependency or in-process model load.

### The shape after the merge

Today: `srt-backend` → HTTP `/translate/stream` (NDJSON) → `srt-cloud-worker` / `srt-mlx-worker`,
each a FastAPI service wrapping `pkg-translator.translate_segments` with an `LLMBackend`.

After Phase B: `srt-backend` calls `translate_segments` **in-process**, selecting an `LLMBackend`
from a config-driven registry. A "worker" is no longer a service — it is a registry row
`{id, base_url, model, api_key, headers, project}`. The HTTP hop is gone.

### The change, step by step

#### 1. Fold `pkg-translator` into the backend workspace

`srt-backend` is already a uv workspace with `pkg-*` members. Move `pkg-translator/` under
`srt-backend/pkg-translator/` and add it to the workspace, exactly like `pkg-job-orch`:

```toml
# srt-backend/pyproject.toml
dependencies = [
  # ...
  "openai>=1.40.0",     # single inference dependency for both backends
  "pkg-translator",
]

[tool.uv.sources]
# ...
pkg-translator = { workspace = true }

[tool.uv.workspace]
members = [
  # ...
  "pkg-translator",
]
```

Keep `pkg-translator`'s `force-include` of `languages.yaml` / `template.txt` / `py.typed`. Nothing
inside `pkg-translator` changes — it stays the business core.

#### 2. Add an OpenAI-client `LLMBackend` in the backend

Both the cloud (DeepSeek) and local (mlx gateway) paths are the same OpenAI client with different
config. Lift `llm.py` + `config.py` from the workers into one backend module. **Open decision —
pick one before starting Phase B:** a new internal package (e.g. `pkg-llm-backend`, sibling to
`pkg-job-orch` in the workspace) is preferred so `translate_segments` and its backend stay
decoupled from product code; putting it directly under `srt_backend` is the lighter alternative.
One `LLMBackend`
implementation, parameterized by a `TranslationConfig` carrying `base_url`/`model`/`api_key`/
`project`/`headers`. This is the union of the two `_CloudBackend` / `_MlxBackend` adapters — they
were already identical except for their config defaults and the DeepSeek-only `extra_body`.

#### 3. Replace the HTTP registry with an in-process backend registry

- `DEFAULT_WORKERS = "mlx=http://localhost:5732,cloud=http://localhost:5733"` in
  `pkg-job-orch/config.py` becomes `LLM_BACKENDS`, a richer per-row config (id → base_url, model,
  api_key/env var, headers/project). Same comma-separated env-string ergonomics; each row now
  describes an inference endpoint, not a worker URL.
- **Cloud deploy** configures only the `cloud` (DeepSeek) row.
- **Local dev/test** additionally configures the `mlx` row → `http://127.0.0.1:5900/v1` (or a tunnel
  URL for a future free tier).
- `workers.py`'s HTTP `probe_workers` / `fetch_languages` proxy collapses: languages come from
  `pkg_translator.available_languages` in-process; a backend's health is
  `ensure_model_available` reachability against its `base_url`. Keep `/api/workers` and
  `/api/languages` routes and the `_LABELS` mapping — only their implementation changes from
  "HTTP to a worker" to "in-process registry + gateway ping".

#### 4. Drop the hop in orchestration

`orchestration.default_worker_client` currently calls
`worker_client.stream_translate(base_url, …)` — HTTP NDJSON. Replace it with an in-process call:

- Select the `LLMBackend` for `worker_id` from the registry.
- Call `translate_segments(source_lang, targets, segments, config, None, on_progress, backend)`
  on a worker thread (`asyncio.to_thread`), exactly as `pkg-translator`'s `_translate_stream` does
  today.
- Fold progress into the `[0, 1]` fraction directly (denominator = Σ `batch_total` across
  targets) — this is the same aggregation `worker_client.stream_translate` did while parsing NDJSON,
  minus the JSON parsing. Return the existing `StreamOutcome`. Note the progress dataclass emitted by
  the in-process path is `pkg_translator.translator.BatchProgress` (fields `batch_index` /
  `batch_total` per target); `worker_client.py` itself has no `BatchProgress` — it parsed those same
  numbers out of NDJSON and exposed `StreamOutcome` / an internal `ProgressUpdate`.

Keep `default_worker_client` as the patchable seam (`JobContext.worker_client`) so the existing test
doubles still swap it. `WorkerStreamError` stays as the failure type; `stream_translate` /
`build_segments` (the NDJSON client) and their tests are deleted.

#### 5. Delete the worker projects and their scaffolding

- Delete `srt-cloud-worker/` and `srt-mlx-worker/` entirely.
- Delete `pkg-job-orch/worker_client.py` (HTTP NDJSON client) and the HTTP-proxy parts of
  `workers.py`.
- `Makefile`: drop `worker` / `cloud-worker` targets and the `WORKERS=...` export; `dev` now runs
  only backend + frontend. Local mlx is reached via the `LLM_BACKENDS` row, not a separate process.
- Root `pyproject.toml`: delete the "three deploy targets must stay separately-installable" preamble
  — it is obsolete. One installable app tree remains (`srt-backend` + its workspace members).
- `.env.example` / `ops/deploy.env.example`: `WORKERS=` → `LLM_BACKENDS=`; cloud deploy sets the
  DeepSeek row only.

### Verification (Phase B, staging)

1. **Two projects only:** repo top level has `srt-backend` and `srt-frontend`; no `srt-*-worker`,
   no top-level `pkg-translator`.
2. **Boundary:** `grep -rn "stream_translate\|worker_client\|/translate/stream" srt-backend/src
   srt-backend/pkg-*` returns nothing (the hop is gone).
3. **Cloud-only install:** the cloud deploy image installs `srt-backend` and can translate via
   DeepSeek with **no** mlx row configured; nothing MLX-related ships.
4. **Unit/CI:** `uv run pytest` passes; the in-process `translate_segments` path is exercised with a
   fake `LLMBackend`; the folded-progress values match the pre-merge NDJSON aggregation on the same
   input.
5. **Types/lint:** `uv run pyright` and `uv run ruff check` clean across the merged workspace.
6. **Live end-to-end (local):** with the Mac gateway running, drive a real job routed to the `mlx`
   backend row and confirm output matches the Phase A baseline; then route to `cloud` and confirm
   DeepSeek output matches its baseline. Progress reaches 1.0; failures (kill the gateway mid-job)
   surface as `WorkerStreamError` and recovery kicks in.

Apply the identical change to prod only after staging passes.

### Phase B done criteria

- Repo has exactly two projects: `srt-backend` and `srt-frontend`.
- `srt-backend` calls `translate_segments` in-process; no HTTP hop, no worker services.
- Choosing local (mlx gateway / tunnel) vs cloud (DeepSeek) is a single `LLM_BACKENDS` config
  decision — no application logic moved, no code duplicated across backends.
- Cloud deploy ships only the DeepSeek backend; the mlx backend exists only where configured.
- Prompts, batching, validation, and semantic retries remain in `pkg-translator` (now a backend
  workspace member).
- Staging verified, then prod verified with the same change.

---

## Questions for the mlx-platform team

- Confirmed gateway base URL / port for `MLX_PLATFORM_BASE_URL`.
- Registered chat alias name and its pinned model revision (must match the current
  `Qwen3-4B-Instruct-2507-4bit` behavior, or we re-baseline the golden output).
- Whether `local-chat` supports `response_format: json_object` (optional optimization only).
- For a future free tier: is exposing the gateway over a tunnel (auth'd, real API key) supported,
  and what rate/attribution limits apply to project `srt-flow`.
