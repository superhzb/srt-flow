# srt-flow — Cleanup / Refactor / Tech-Debt Plan

Senior-review of all 4 services (srt-backend, srt-frontend, srt-mlx-worker,
srt-cloud-worker) + repo tooling. Ordered by **value ÷ risk**. Each item has
concrete file locations so it can be picked up cold.

> **Status: prototyping, and a large refactor is already in flight on disk
> (uncommitted).** The working tree already implements much of Phase 0 (job-orch
> `User.google_sub` + `processed_events` via migration `0002`; billing/app_store
> mid-migration to DB-backed), Phase 2 (`pkg-translator` extracted at repo root;
> both workers depend on it; `languages.yaml`/`template.txt` moved), and **Phase 4
> tooling** (root `pyproject.toml`, `.github/workflows/ci.yml`, frontend
> eslint/prettier/vitest, `.python-version`/`.nvmrc` — all present untracked;
> the uv-workspace idea was reversed, see item 17). Items tagged **"in progress on
> disk"** / **"landed on disk"** are *finish/reconcile* work, not greenfield.
> Sections reflect this actual state, not a from-scratch design.

Guiding rules (from PLAN.md): vertical slices, no import side-effects. **Package
contracts are NOT frozen — we are prototyping**, so re-export/compat shims can be
deleted freely and API breaks between packages are fine (the "frozen contracts"
aspiration is deferred until post-prototype). The only behavior changes intended
are the correctness fixes explicitly called out in Phase 0.

---

## Phase 0 — Correctness landmines (do first, small, real bugs)

These are not cosmetic. They lose data or money on a restart.

1. **Paid tier + webhook idempotency evaporate on restart.**
   `src/srt_backend/app_store.py` keeps users, `paid` status, and processed
   Stripe event IDs in dicts, wired into the real app (`app.py:79-80`). A
   customer who paid reverts to free on reboot; a re-delivered webhook
   re-processes. Jobs are already durable (SQLite) — move user/paid/event state
   to the same DB. This is the same fix as item 2 (canonical DB `User`) and
   resolves item 9 (three in-memory stores collapse into the one DB-backed store).

   > **In progress on disk.** Migration `0002_users_google_sub_processed_events`
   > already adds the `processed_events` table (PK `event_id`, FK `user_id`,
   > `session_id`, `paid_at`, `created_at`) and `user.google_sub` UNIQUE, and
   > `app_store.py`/`pkg_billing/api.py` are mid-migration to DB-backed. **What is
   > NOT yet done: atomicity (below).** The store still exposes the three separate
   > calls, so the TOCTOU window persists even after the table lands.

   - **Collapse the 3-call webhook path into one atomic op.** The `BillingStore`
     contract today is `has_processed_event()` → `mark_paid()` → `record_event()`
     as **three** separate awaits (`pkg_billing/api.py:58,49,60`). Even DB-backed,
     that is a TOCTOU race + a partial-write window (paid flipped, event not
     recorded, or vice-versa). Add a single method
     `apply_paid_webhook_once(event_id, session_id, user_id, paid_at) -> bool` that,
     **inside one transaction**, inserts the `processed_events` row and flips the
     user to paid; returns `False` (no-op) if the event was already recorded. The
     webhook route calls only this. Remove `has_processed_event`/`record_event` from
     the contract (or keep as read-only helpers, not the write path).

   **Acceptance criteria:**
   - A user upserted before restart is still present (same id, tier) after restart.
   - `processed_events.event_id` is the PRIMARY KEY (already so in `0002`) → a
     duplicate Stripe `event.id` insert raises, not silently upserts.
   - `apply_paid_webhook_once` is the sole webhook write path: event-insert + paid-flip
     commit in **one** transaction; a duplicate `event_id` (unique/PK violation) makes
     the whole call a no-op returning `False`; no path flips paid without recording
     the event and vice-versa.
   - **Tests:** (a) pay → restart → `GET /me` still `tier=paid`; (b) deliver the same
     webhook twice **across a restart** → `apply_paid_webhook_once` returns `True`
     then `False`, user paid exactly once, no second side-effect; (c) a forced failure
     between insert and flip rolls back both (no half-applied state).

2. **Two divergent `User` identity models — unify on one DB `User`.**
   `pkg_auth.models.User` (frozen dataclass, `int id`, has `google_sub`) vs
   `pkg_job_orch.models.User` (SQLModel `str id`). Nothing reconciles them; blocks
   the slice-4 OAuth→DB upsert.

   > **In progress on disk (ownership already decided).** `pkg-job-orch` is the DB
   > owner — it holds the `Engine`, `session_scope`, `run_migrations`, and the
   > Alembic tree. The in-flight work put the canonical `User` (now with
   > `google_sub: str | None`, UNIQUE) **in `pkg_job_orch/models.py`** and added
   > migration `0002` there. **Do not introduce a `pkg-db` package** — that would be
   > an ownership move (Engine/migrations/metadata/FK rewiring) hidden inside a
   > correctness fix, and disk has already committed to job-orch as owner. The
   > earlier `pkg-db` recommendation is **withdrawn**; keep the existing job-orch DB
   > owner. auth/billing depend on job-orch's store/models (or a store injected at
   > composition root — the pattern `set_billing_store`/`set_user_store` already
   > supports this, so no new package dep is forced).

   **Decisions to lock:**
   - **Owner = `pkg-job-orch`** (existing). No `pkg-db`. `Job.user_id` FK already
     references `user.id` there; `processed_events.user_id` FK likewise (`0002`).
   - **id type = `str`.** New OAuth users get a **UUID4-hex** id at upsert; the
     seeded **`dev-user` keeps its stable non-UUID sentinel id** (`"dev-user"`) — it
     is a fixed seed row, not a generated one. (These are consistent: UUID4 applies
     to *generated* identities only.) Auth's old `int` id lived only in the
     in-memory store and was **never persisted**, so there is no int→str backfill.
   - **`google_sub`**: nullable, UNIQUE (NULL for `dev-user`; one row per Google
     identity). Already added by migration `0002` — this item just finishes wiring
     auth/billing to read/write the DB `User` instead of their in-memory copies.
   - **Migration path:** none for real data — the only persisted row today is the
     `dev-user` seed. Finish: point auth/billing at the job-orch store, re-seed
     `dev-user` if absent, delete the in-memory `User` dataclass + stores (item 9).

3. **`_is_valid_translation` dead branch (both workers).**
   `validation.py:75-77` — `bool(stripped) and (_STATS_RE.match(...) or len(stripped)>0)`
   reduces to `bool(value.strip())`; `_STATS_RE` (`:9`) is dead. Either restore
   the intended numeric-only special-case or delete the regex. Fix once (see
   Phase 2, shared package).

4. **Alembic autogenerate diffs against empty metadata.** `migrations/env.py:17-18`
   comments that models must be imported but never imports
   `pkg_job_orch.models`. Works today only via `db.py` import order; standalone
   `alembic revision --autogenerate` is broken. Add the explicit import.

---

## Phase 1 — Quick wins (low-risk deletions, hours not days)

Mostly subtraction, no behavior change. **Exception: item 6 is a decision note
(KEEP / no change), not a deletion** — kept here so the pkg-notification call is
recorded next to the cleanup it was originally slated for.

5. **Delete dead code:**
   - `resolve_worker` (`routes.py:183`, zero callers)
   - `count_jobs_by_status` + `get_user_by_email` (`db.py:120,126`, zero callers)
   - `_ = Path` (`app.py:135`), `_ = asyncio` (`conftest.py`) linter no-ops — drop the imports instead
   - `parseSrt` + unused path in frontend `api.ts:116-122` (App uses `prepareSrt`)

6. **`pkg-notification` — KEEP (decided).** Stub (`api.py` = `__all__=[]`),
   unwired, live seam is `NullNotifier` (`orchestration.py:82`). Retained as
   scaffolding for slice 6. No action now — just don't let it rot; wire it into
   `[tool.uv.sources]` only when slice 6 fills it in.

7. **Repo hygiene:**
   - gitignore committed e2e reports (`srt-{cloud,mlx}-worker/tests/reports/*.md` — churns every run)
   - remove stray fixtures: root `simple_5_lines.srt`, `srt-backend/sample.srt`, `srt-backend/note.md`
   - drop committed `.env` files (`srt-backend/.env`, `pkg-auth/.env`); keep only `.env.example`. **Verify no live secrets first**, then gitignore. (A live `DEEPSEEK_API_KEY` also sits untracked in `srt-cloud-worker/.env` — footgun.)
   - remove `srt-cloud-worker/dist/.gitignore` placeholder (empty build dir in VCS)

8. **Frontend `lint` — DONE (was broken).** Previously `package.json` `"lint":"eslint ."`
   with no eslint dep and no config. Now wired on disk: `eslint.config.js` (flat config)
   + eslint/prettier deps + `lint`/`format`/`format:check` scripts, run in CI. See
   Phase 4 item 19. No action.

---

## Phase 2 — Finish the in-flight worker de-duplication

**~85% of each worker was copy-pasted** (~650 lines source + ~750 lines tests).
Worker-specific surface is exactly two things: the `llm.py` adapter and the
`TranslationConfig` field set.

> **Already in progress on disk (uncommitted).** This is not greenfield —
> the extraction is partly done and just needs finishing + reconciling:
> - `pkg-translator/` **exists at repo root** (shared core: `translator.py`,
>   `validation.py`, `prompts.py`, `models.py`, `app.py` w/ `create_app` +
>   `_translate_stream`, `api.py`, `config.py`, `languages.yaml`, `template.txt`).
> - Both workers already `dependencies += ["pkg-translator"]` via
>   `[tool.uv.sources] pkg-translator = {path="../pkg-translator", editable=true}`.
> - `languages.yaml`/`template.txt` **deleted** from both workers (moved to core).
> - `mlx`/`mlx-lm` are now an **`[mlx]` optional-dependency extra** on
>   `srt-mlx-worker`; `openai` is a hard dep of `srt-cloud-worker`.
> - **Names unchanged** — the packages are still `srt-mlx-worker` and
>   `srt-cloud-worker` (no rename to `pkg-*-worker`, no `srt-translator` repo).
>   Any earlier plan text proposing those renames is **superseded** — keep the
>   existing names so the Makefile, `[project.scripts]`
>   (`srt-mlx-worker = "srt_mlx_worker.server:main"`), and deploy scripts stay valid.

### Actual layout (as on disk)

```
srt-flow/                        # repo root unchanged (no srt-translator rename)
├── pkg-translator/              # shared core — deps: fastapi, pyyaml, pydantic, uvicorn
│   └── src/pkg_translator/{translator,validation,prompts,models,app,api,config}.py
│       + languages.yaml + template.txt        # NO mlx, NO openai
├── srt-cloud-worker/            # deps: pkg-translator + openai
│   └── src/srt_cloud_worker/…
└── srt-mlx-worker/              # deps: pkg-translator + [mlx] extra (mlx, mlx-lm)
    └── src/srt_mlx_worker/…
```

### Remaining work (finish the migration)

The workers still carry **leftover half-migrated modules** — `translator.py`,
`validation.py`, `prompts.py`, `models.py`, `app.py` now just re-wrap
`pkg_translator` (e.g. `srt_mlx_worker/app.py` imports `create_app` from
`pkg_translator.api` *and* local `.translator`). Finish:

- **Delete the worker-local re-wrappers** that only forward to `pkg_translator`
  (`translator.py`, `validation.py`, `prompts.py`, `models.py`, and the `app.py`
  wrapper if `server.py` can call `create_app` directly). Each worker should end at
  **`llm.py` (LLMBackend impl) + `config.py` (TranslationConfig subclass) +
  `server.py` (wires backend into the shared `create_app`)**.
- **`api.py` re-export shim — optional, no obligation.** *We are prototyping, so
  package contracts are not frozen* (the "frozen contracts" note in the intro is
  the north-star aspiration, not a current constraint). `srt_{cloud,mlx}_worker.api`
  currently re-exports from `pkg_translator.api` + local modules; since nothing
  external consumes it, **delete it** unless a test imports it. If kept, it must be
  a pure thin re-export, not a second source of truth. No deprecation shim needed.
- **Confirm the LLM seam is normalized.** `LLMBackend` protocol in
  `pkg_translator.config`: `generate_text(prompt, config) -> str` +
  `ensure_model_available(config) -> None` (disk names it `ensure_backend_available`
  in `mlx llm.py` — verify both workers match the core protocol exactly).
- **De-dup the tests.** Move the shared `test_api.py` into `pkg-translator`; each
  worker keeps only its `llm`-adapter test + e2e. (Both `test_api.py` are still
  ~identical on disk.)
- **Kill the dotenv duplication.** `load_local_env`/`_parse_env_value` → core (or
  adopt `python-dotenv`); delete the copy in `cloud test_e2e_real_worker.py:21-36`.
- **Fold in the `_STATS_RE` dead-branch fix (Phase 0 #3)** — now a one-place fix in
  `pkg_translator/validation.py`.

### Deploy model — 2 entry points, NOT 1 process

Topology is fixed: **mlx runs local on the user's Mac** (Apple-silicon, `mlx_lm`),
**cloud runs remote** (Linux, DeepSeek). The backend addresses both by separate
`base_url`; both run **simultaneously** (user picks in UI). The shared core is a
**codebase merge, not a runtime merge** — still two processes on two hosts, each
installing only its own package:

- Cloud host (Linux): `uv sync` in `srt-cloud-worker/` → core + `openai`,
  **never pulls `mlx_lm`**.
- Mac: `uv sync --extra mlx` in `srt-mlx-worker/` → core + `mlx`/`mlx-lm` (the
  `[mlx]` extra; without `--extra mlx` the heavy backend isn't installed).

**Do NOT** collapse to one process with a `BACKEND=mlx|cloud` runtime switch that
imports both backends — the Linux cloud image can't install `mlx_lm`. Two
separately-installable packages keep dep-correctness at install time.

### Packaging acceptance criteria

- **Package data:** `languages.yaml` + `template.txt` ship inside the
  `pkg-translator` wheel and load via
  `importlib.resources.files("pkg_translator") / "languages.yaml"` — **not** the
  current `_PACKAGE_DIR.parents[...]` path walk (`config.py:8`), which breaks once
  the files live in an installed dependency. Declare them in `[tool.hatch.build]`
  / `[tool.setuptools.package-data]` (or `force-include`) so `uv build` includes
  them; add a test that loads both from the installed package, not the source tree.
- **Public API:** one `pkg_translator.api` re-export module is the only supported
  import surface — `create_app`, `translate_segments`, `TranslationConfig`,
  `LLMBackend` (protocol), `TranslationRequest/Response`, `available_languages`.
  Internal modules (`translator`, `validation`, `prompts`) are not imported
  directly by worker packages. Lock it with an `__all__` and a test asserting the
  surface resolves.
- **Backend deps live only in the worker packages:** `pkg-translator` declares
  neither `mlx`/`mlx-lm` nor `openai`; `srt-mlx-worker` owns them behind its
  `[mlx]` extra, `srt-cloud-worker` owns `openai`. A test / CI check that
  `pkg-translator`'s dep closure contains neither backend keeps the seam honest.
- **`/translate` (non-stream) endpoint stays in shared `create_app`** (both workers
  expose it identically; it is test/debug-only, no prod caller) — do not fork it
  worker-local. `/translate/stream`, `/health`, `/languages` likewise shared. The
  only worker-local wiring is injecting the `LLMBackend` + `TranslationConfig` into
  `create_app` from `server.py`.
- **No import side-effects** in `pkg-translator` or either worker (honor the repo
  rule): yaml load stays behind `lru_cache`; no model/client/detector built at
  import — the backend is constructed in `server.py` at startup, not module import.

### Migration note

Backend config already maps `worker_id → base_url` via env — **no `srt-backend`
change** needed, and package names are unchanged so the Makefile/deploy scripts
stay valid. The `/health`, `/languages`, `/translate`, `/translate/stream`
contracts are unchanged, so `srt-backend` and the frontend are untouched by this
phase.

---

**Decided: do NOT merge `pkg-srt-services` into `pkg-job-orch`.** srt-services is a
pure zero-dep leaf imported outside job-orch (`detection.py`, `routes_srt.py`).
Merging would drag job-orch's DB/alembic/sqlmodel stack into the plain SRT-parse
route. It's the cleanest package in the repo — leave it independent.

**Note on streaming (decided): keep it.** `/translate/stream` NDJSON is
server-to-server only (job-orch → worker) and powers the determinate progress bar;
the frontend consumes no stream (it polls `/api/jobs/{id}`). It is load-bearing —
keep it, and add its missing direct test (Phase 6 #26). The plain non-stream
`POST /translate` has zero production callers (worker tests only) — optionally
demote to a documented debug endpoint, low priority.

---

## Phase 3 — Backend consolidation & consistency

9. **Collapse three in-memory user stores into one.** `AppStore` (`app_store.py:16`),
   `InMemoryUserStore` (`pkg_auth/models.py:27`), `InMemoryBillingStore`
   (`pkg_billing/api.py:76`) all reimplement `get_by_sub/get_by_id/upsert/mark_paid`.
   **`upsert` tier logic diverges** — `AppStore` is sticky-paid, `InMemoryUserStore`
   overwrites unconditionally (`models.py:37-40`) — a latent bug. One store,
   DB-backed (folds into Phase 0 #1).

10. **One HTTP client.** `pkg-auth` uses `httpx>=0.28` (`google.py:9`); root +
    job-orch use `httpx2>=2.5` (`worker_client.py:21`, `workers.py:18`). Both
    ship in `.venv`. Pick one across the backend.

11. **No import side-effects (PLAN/AGENTS rule violations):**
    - `detection.py:60` builds the lingua detector at import (expensive) → lazy accessor / `lru_cache`
    - `pkg_auth/state.py:7` and `pkg_billing/api.py:129` instantiate stores at import → construct in a factory / lifespan

12. **Unify config loading.** Three styles: pydantic-settings (auth), hand-rolled
    `_required_env/_int_env` (billing `api.py:287-311`), inline `os.environ.get`
    (job-orch). Converge on pydantic-settings.

13. **`billing.get_config()` over-couples + re-parses env per request.**
    Requires `STRIPE_WEBHOOK_SECRET` even for checkout (`api.py:146-147`); no
    caching (`get_config` re-runs on every request, sometimes twice per checkout).
    Split checkout vs webhook config; `lru_cache` it.

14. **Split the 526-line billing god-module** (`pkg_billing/api.py`): config /
    HMAC ref-signing / Stripe client / store / router into separate modules.

15. **Typed errors, not string matching.** `routes.py:57-58` routes 404 vs 400 by
    `"unknown worker" in str(exc).lower()`. Use a typed exception.

16. **Dedup cue↔dict + parse-error handling.** `_cue_to_dict`/`_dict_to_cue`/
    `build_segments` scattered across `routes_srt.py:19`, `routes.py:157-179`,
    `worker_client.py:149`; ParseError→400 copy-pasted (`routes_srt.py:67-72,88-93`).
    Single cue-serialization home; `prepare` is a superset of `parse`.

---

## Phase 4 — Repo tooling & CI (prevents regression of everything above)

> **Largely landed on disk (uncommitted) — this phase is now reconcile/finish,
> not greenfield.** A root `pyproject.toml`, `.github/workflows/ci.yml`, frontend
> eslint/prettier/vitest, and `.python-version`/`.nvmrc` all exist untracked. The
> item text below reflects that actual state. Only the leftovers tagged **remaining**
> are still open.

17. **uv workspace root — decision REVERSED on disk; do NOT add a uv workspace.**
    A root `pyproject.toml` now exists (untracked) and is **deliberately not a uv
    workspace** — header comment: *"Not a uv workspace — the three deploy targets
    must remain separately-installable."* This is correct and consistent with
    Phase 2's deploy model (mlx-on-Mac / cloud-on-Linux install only their own
    package; a workspace would fight that). The earlier "hoist everything into a
    workspace" recommendation is **withdrawn.** What the root file *does* do: hoist
    `[tool.ruff]` (discovered upward). What it deliberately does **not**: a workspace
    member graph.

    **Remaining (consistency, not a workspace):**
    - `[tool.pyright]` + `[tool.pytest]` still duplicated across the 10 per-package
      `pyproject.toml` (accepted cost of no-workspace — leave unless it bites).
    - **uvicorn drift still unresolved:** backend `[standard]>=0.32`, both workers
      bare `>=0.35`. Pin to one floor.
    - `uv.lock` tracking still uneven (notification/srt-services unlocked; root
      `uv.lock` is a stub).
    - `pyright venvPath` — now set consistently in every package (resolved).

18. **CI — DONE (validate, don't rebuild).** `.github/workflows/ci.yml` exists:
    jobs `ruff` + per-service `pyright`/`pytest` (backend, pkg-translator,
    cloud-worker, mlx-worker) + `frontend` (format:check, lint, typecheck, test,
    build). Matches the intent. Action item: **confirm it's green on a push** — it
    has never run in CI yet (untracked).

19. **Frontend eslint + prettier — DONE.** `eslint.config.js` (flat config) +
    `.prettierignore` present; `package.json` carries eslint/prettier/vitest deps and
    `lint`/`format`/`format:check` scripts (the previously-broken `lint` is wired).
    `.python-version` (`3.12`) and `.nvmrc` (`22`) added. No action.

---

## Phase 5 — Frontend refactor

> **Largely landed on disk (uncommitted) — reconcile/finish, not greenfield.**
> `src/lib.ts` (`errMessage`, `apiFetch`), `src/hooks.ts` (`usePoll`, `POLL_INTERVAL_MS`,
> `useJobOutput`), and `src/components.tsx` (`ErrorBanner`, `TierBadge`, `RefreshButton`,
> `SrtPreview`) all exist and are wired into the screens. Item text reflects that state;
> only **remaining** tags are still open.

20. **Three helpers — DONE (hook renamed).**
    - `errMessage(e, fallback)` — `src/lib.ts`, re-exported via `api.ts`, used across
      App/Auth/Billing/Db/Configure/Jobs screens.
    - `apiFetch<T>(url, init, fallback)` — `src/lib.ts`, used ~10× in `api.ts`. The
      remaining raw `fetch` calls are the 401/402 special-case endpoints (by design).
    - `usePoll` (generic — **not** `usePollJob`) + `POLL_INTERVAL_MS` in `src/hooks.ts`.
      All three hand-rolled poll loops (`ProcessingScreen`, `JobsScreen`, `BillingScreen`)
      now use it. **Remaining:** none — migration complete.

21. **Shared components — DONE.** `<ErrorBanner>`, `<TierBadge>` (single canonical
    style — the two divergent copies collapsed), `<RefreshButton>`, `<SrtPreview>` all in
    `src/components.tsx` and used across the screens.

22. **Unbloat `App.tsx` — DONE.** `UploadFlow` extracted; App keeps tab routing.
    App.tsx now ~412 lines, duplicated `configure` guard resolved.

23. **Latent `workerLabel` bug — DONE (fixed).** `ConfigureScreen` now threads
    `worker?.label ?? workerId` — real human label, not the id.

24. **Converge screen state patterns — PARTIAL.** `BillingScreen` (discriminated
    `LoadState` union + ref-copy `useEffect` workaround removed) and `DbScreen`
    (stale-closure fixed via latest-ref + `useCallback`) are done. **Remaining:**
    `AuthScreen` still carries ~8 ad-hoc `useState` booleans — not yet converged to the
    union.

25. **A11y pass — DONE.** drop-zone `role="button"`+`tabIndex`+`onKeyDown`; clickable
    `<tr>` keyboard-operable; progress bar `role="progressbar"`+`aria-valuenow`; error
    banners `role="alert"`.

---

## Phase 6 — Test coverage (the scariest gaps)

> **Largely landed on disk (uncommitted) — the backend gaps are now covered; only
> the frontend extension (#29) remains open.** New untracked test files fill 26–28
> and 30; item text updated to DONE with the file that covers each.

26. **`worker_client.stream_translate` — DONE.** `pkg-job-orch/tests/test_worker_client.py`
    covers progress-denominator fold across targets, `error` event (+ missing-detail
    fallback), non-200 open (503), and stream-ends-without-terminal. Uses ASGI transport,
    no real socket.
27. **`tokens.py` + JWKS — DONE.** `pkg-auth/tests/test_tokens.py` (expiry→401, tampered→401,
    round-trip) and `pkg-auth/tests/test_google_jwks.py` (`verify_id_token` happy path,
    key-fetch failure→400, wrong-audience→400).
28. **`workers` + workers route — DONE.** `pkg-job-orch/tests/test_workers.py`
    (`probe_workers`/`fetch_languages`/WORKERS parse/unknown-worker raise) +
    `srt-backend/tests/test_workers_route.py` (`/api/workers`, `/api/languages`,
    unknown-worker→404).
29. **Frontend tests — bootstrapped, extend coverage.** vitest is now set up
    (`vitest.setup.ts` + jsdom/testing-library) with `hooks.test.tsx` (the `usePoll`
    hook from #20 — terminal/stopOnError/disabled/maxMs) and `lib.test.ts`
    (`errMessage`/`apiFetch`). **Remaining:** screen-level state-machine coverage
    (Upload/Configure → job flow) and the `api.ts` endpoints beyond `apiFetch` are
    still untested.
30. **Names-only `test_api.py` stubs — DONE.** job-orch `test_api.py` deleted;
    srt-services `test_api.py` rewritten into a real test (parse assertions +
    `__all__` resolvability).

---

## Suggested sequencing

`Phase 0` (correctness) → `Phase 1` (deletions clear the deck) → `Phase 2`
(worker dedup — biggest single win, self-contained) → `Phase 4` #18 (CI, so the
rest can't regress) → `Phase 3` (backend) → `Phase 5` (frontend) → `Phase 6`
(tests, backfilled alongside 3 & 5).

Phases 0/1/2 are the high-leverage core: real bug fixes, then ~1400 lines
deleted, then a CI net. Do those first even if 3/5/6 slip.
