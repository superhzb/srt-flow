# Phase B Handoff — Collapse workers into `srt-backend`

**Owner of Phase A:** done (see below). **This doc:** everything needed to finish Phase B.
**Reference:** the full design is in `MLX_PLATFORM_MIGRATION.md` §"Phase B". This handoff pins the
exact files, symbols, and line refs so you don't have to re-derive them, and records the gotchas
found while doing Phase A.

**Testing:** deferred to the end by decision — do the full code change first, then run the single
combined verification pass (Phase A live + Phase B) described at the bottom. Don't stop to smoke-test
mid-migration.

---

## Where things stand

**Phase A is code-complete and green offline** (`srt-mlx-worker` is now a thin OpenAI client to the
mlx-platform gateway — no in-process MLX). Offline checks pass: boundary grep clean, `uv sync
--frozen` OK, `pytest` 9 passed / 1 e2e skipped, `pyright` + `ruff` clean. **Not yet run live** and
**not yet on prod** — that folds into the final combined test.

Both workers are now identical OpenAI clients differing only by `base_url` / `model` / `api_key` /
headers. That is the precondition that makes Phase B safe: there is no MLX-specific dependency or
in-process model load left in either worker.

**Deployment invariant that makes the merge safe:** the mlx path is local-dev/test only; cloud deploy
uses DeepSeek only. So the merged backend never reaches the Mac gateway from cloud infra — no
cross-network constraint blocks folding the workers in-process.

---

## The end state

- Repo top level = **two** projects: `srt-backend`, `srt-frontend`.
- `srt-backend` calls `pkg_translator.translate_segments` **in-process**; no HTTP `/translate/stream`
  hop, no worker services.
- A "worker" becomes a config row `{id, base_url, model, api_key/env, headers, project}` in an
  in-process registry. Choosing local (mlx) vs cloud (DeepSeek) is one config decision.
- `pkg-translator` is a `srt-backend` workspace member (business core unchanged).
- `srt-cloud-worker/` and `srt-mlx-worker/` deleted.

---

## Step-by-step, with real symbols

### 1. Fold `pkg-translator` into the backend workspace
`srt-backend/pyproject.toml`: add `openai>=1.40.0` + `pkg-translator` to deps; add
`pkg-translator = { workspace = true }` to `[tool.uv.sources]`; add `pkg-translator` to
`[tool.uv.workspace] members` (alongside `pkg-job-orch`, `pkg-auth`, `pkg-billing`, `pkg-file-upload`,
`pkg-notification`, `pkg-srt-services`). Move `pkg-translator/` under `srt-backend/pkg-translator/`.
Keep its `force-include` of `languages.yaml` / `template.txt` / `py.typed`. Nothing inside
`pkg-translator` changes.

### 2. Add one OpenAI-client `LLMBackend` in the backend
- **Decision to make first** (flagged in the plan): put it in a new workspace package
  `pkg-llm-backend` (preferred — keeps inference decoupled from product code) or directly under
  `srt_backend`. Pick one before writing code.
- It is the union of the two worker adapters. Source of truth to lift:
  - `srt-mlx-worker/src/srt_mlx_worker/llm.py` (OpenAI client, `default_headers={"X-MLX-Project":
    …}`, no `extra_body`) and its `config.py` (`model`/`base_url`/`project`/`api_key`/
    `request_timeout`).
  - `srt-cloud-worker/src/srt_cloud_worker/llm.py` (the DeepSeek-only `extra_body={"thinking":
    {"type": "disabled"}}` and `api_key_env` env-var lookup).
- One `LLMBackend` implementation (matches `pkg_translator.translator.LLMBackend` protocol:
  `ensure_model_available(config)` + `generate_text(prompt, config)` — `translator.py:20`),
  parameterized by a `TranslationConfig` carrying `base_url`/`model`/`api_key`(or env)/`project`/
  optional `extra_body`. **Do not duplicate two classes** — the only real difference is DeepSeek's
  `extra_body` and env-var key vs literal key; make both config-driven.

### 3. Replace the HTTP registry with an in-process backend registry
- `pkg-job-orch/config.py:26` `DEFAULT_WORKERS = "mlx=http://localhost:5732,cloud=http://localhost:5733"`
  and `Settings.workers` (`config.py:36`) → `LLM_BACKENDS`: same comma-separated env ergonomics, but
  each row now carries id → base_url, model, api_key/env, headers/project (not just a worker URL).
- `pkg-job-orch/workers.py`: `workers_env` (`:63`), `worker_base_url` (`:86`), `probe_workers`
  (`:94`), `fetch_languages` (`:113`) become registry lookups instead of HTTP proxying:
  - Languages: `pkg_translator.available_languages(languages_path)` in-process
    (`prompts.py:47`) instead of `fetch_languages(base_url)`.
  - Health: a backend's `ensure_model_available` reachability against its `base_url` instead of an
    HTTP `/health` probe.
  - **Keep** the `/api/workers` and `/api/languages` routes and the `_LABELS` map (`workers.py:36`,
    e.g. `{"cloud": "Cloud (DeepSeek)", "mlx": "Local MLX"}`) — only their implementation changes.
    Frontend contract stays the same.

### 4. Drop the hop in orchestration (`pkg-job-orch/orchestration.py`)
- Today: `default_worker_client` (`:126`) → `stream_translate(base_url, …)` (HTTP NDJSON). Call site:
  `orchestration.py:400-410` (`client = ctx.worker_client; result = await client(base_url, …)`),
  base_url resolved at `:373` via `worker_base_url(worker)`.
- Replace `default_worker_client`'s body with an in-process call:
  - Select the `LLMBackend` for `worker_id` from the registry.
  - `translate_segments(source_lang, targets, segments, config, None, on_progress, backend)`
    (`translator.py:40`) on a worker thread via `asyncio.to_thread`, exactly as
    `pkg-translator`'s `_translate_stream` (`app.py:109`) does today.
  - **Progress folding:** `translate_segments`' `on_progress` receives
    `pkg_translator.translator.BatchProgress` (`translator.py:27`; fields `target`, `target_index`,
    `target_total`, `batch_index`, `batch_total`) — NOT a `[0,1]` float. `worker_client` currently
    fires a normalised `[0,1]` fraction. So the new `default_worker_client` must aggregate:
    denominator = Σ `batch_total` across targets, numerator = completed batches, emit the fraction to
    the existing `on_progress`. This reproduces what `stream_translate` computed while parsing NDJSON,
    minus the JSON parsing. Match the pre-merge fraction sequence on the same input (see verification).
  - Return the existing `StreamOutcome` (`worker_client.py:43`, fields `source_lang`/`targets`/
    `segments`).
- **Keep `default_worker_client` as the patchable seam.** `JobContext.worker_client`
  (`orchestration.py:152`, defaulted in `__post_init__` at `:156`) must stay so existing test doubles
  still swap it. Keep `WorkerStreamError` (`worker_client.py:51`) as the failure type — map backend
  exceptions to it so `orchestration.py:340`'s `except WorkerStreamError` recovery is unchanged.
- The `client(base_url, …)` signature and the `WorkerClientFn` alias (`orchestration.py:120`) can
  keep their shape; `base_url` just becomes "which registry row" rather than a live URL, or fold the
  lookup inside. Preserve the dict-coercion fallback at `:405-410` if any test double returns a plain
  dict.

### 5. Delete worker projects + scaffolding
- Delete `srt-cloud-worker/` and `srt-mlx-worker/`.
- Delete `pkg-job-orch/worker_client.py` (HTTP NDJSON client: `stream_translate` / `build_segments`)
  and its tests. `StreamOutcome` / `WorkerStreamError` move to wherever the new in-process client
  lives (they're still the return/error types).
- Delete the HTTP-proxy parts of `workers.py` (see step 3).
- `Makefile`: drop `worker` / `cloud-worker` targets and the `WORKERS=…` export; `dev` runs backend +
  frontend only. Local mlx is reached via an `LLM_BACKENDS` row, not a separate process.
- Root `pyproject.toml`: delete the "three deploy targets must stay separately-installable" preamble
  (obsolete). Note: root is currently ruff-only config / "Not a uv workspace" — reconcile with the
  single-app-tree end state.
- `.env.example` / `ops/deploy.env.example`: `WORKERS=` → `LLM_BACKENDS=`; cloud deploy sets the
  DeepSeek row only. Local dev/test additionally sets the mlx row → `http://127.0.0.1:5900/v1`
  (confirm port with platform team) or a tunnel URL for a future free tier.
- Update `.github/workflows/ci.yml`: the `cloud-worker` and `mlx-worker` jobs go away; their coverage
  moves into the `backend` job. Update the `needs: […]` lists on `deploy-staging` (and prod) which
  currently list `cloud-worker, mlx-worker`.

---

## Gotchas found in Phase A (save yourself the debugging)

- **`base_url` uses `field(default_factory=…)`** in the mlx config, so `TranslationConfig.base_url`
  (class attr) raises `AttributeError` — instantiate first (`TranslationConfig().base_url`). Same
  pattern will bite in tests/config code that reads defaults off the class.
- **`pkg-translator.TranslationConfig` (base) has no `request_timeout`** — each backend config adds
  its own. The merged config must carry it explicitly.
- **Cloud vs mlx config are NOT symmetric:** cloud uses `api_key_env` (env-var *name*, read at call
  time) and has **no** `project` field; mlx uses a literal `api_key` and adds `project` /
  `X-MLX-Project`. The merged config must support both (env-var *or* literal key; optional headers).
- **pyright is strict** in these packages — annotate everything, no bare lambdas as monkeypatch
  targets.
- **`uv sync --frozen` in CI** means the lockfile must be regenerated (plain `uv sync`) after any
  `pyproject.toml` dep change, and committed.
- **Semantic retries stay in `pkg-translator`** (invalid JSON / missing items). The platform/backend
  only does operational retries. Don't move retry logic.

---

## Final combined verification (run once, at the end)

Do Phase A live checks and Phase B together after all code lands, on staging first, then prod.

**Phase A live (needs Mac gateway up):**
- `uv run pytest -m e2e` in `srt-mlx-worker` (before deletion) or via the merged mlx backend row.
- Output SRT matches a pre-migration baseline on the same input (same alias → same behavior).
- Request shows in mlx-platform console History attributed to project `srt-flow`.
- Kill gateway mid-job → clean error + existing recovery kicks in.
- Cloud path (DeepSeek) untouched.

**Phase B (staging):**
1. **Two projects only:** repo top level = `srt-backend` + `srt-frontend`; no `srt-*-worker`, no
   top-level `pkg-translator`.
2. **Boundary:** `grep -rn "stream_translate\|worker_client\|/translate/stream" srt-backend/src
   srt-backend/pkg-*` returns nothing.
3. **Cloud-only install:** cloud deploy image installs `srt-backend`, translates via DeepSeek with
   **no** mlx row; nothing MLX-related ships.
4. **Unit/CI:** `uv run pytest` green; in-process `translate_segments` exercised with a fake
   `LLMBackend`; **folded-progress values match the pre-merge NDJSON aggregation on the same input**
   (capture the `[0,1]` sequence before you delete `worker_client.py`).
5. **Types/lint:** `uv run pyright` + `uv run ruff check` clean across the merged workspace.
6. **Live (local):** Mac gateway up → route a job to the `mlx` row, output matches Phase A baseline;
   route to `cloud`, matches DeepSeek baseline; progress reaches 1.0; kill gateway → `WorkerStreamError`
   + recovery.

Apply the identical change to prod only after staging passes.

## Open questions for the mlx-platform team (still needed)
- Confirmed gateway base URL / port for `MLX_PLATFORM_BASE_URL` (Phase A used `5900` placeholder).
- Registered chat alias name + pinned revision (must match `Qwen3-4B-Instruct-2507-4bit` or
  re-baseline golden output).
- Whether `local-chat` supports `response_format: json_object` (optional optimization).
- Free-tier tunnel: auth'd exposure supported? rate/attribution limits for project `srt-flow`?
