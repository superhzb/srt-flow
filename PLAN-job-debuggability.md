# Plan — Job Debuggability: persist failure context in DB

Goal: when a job fails or partially succeeds, a dev can answer *what broke,
where, how long it took, how many retries, which target lost lines* — from the
`job` row + API, without grepping (currently-invisible) logs.

No backward compat required → reshape schema freely, single new Alembic
migration, no data preservation.

Scope: `pkg-job-orch` (models, orchestration, routes, migration). The
dropped-segment data is derivable backend-side — **no worker / `pkg-translator`
changes for the DB work**. The logging companion (§5) is separate: it touches
worker `server.py` entry points and adds a handler-free `lifespan` *passthrough*
param to `pkg_translator.create_app` (a hook — the library still never
configures handlers itself).

Resolved design decisions (review round 1):
- **Dropped metric = per-target JSON** `{"fr": 2, "es": 0}`. Persisted whenever
  `_build_outputs` ran — i.e. on `done` AND on `landing` failures (translation
  finished, counts known). `None` only when translation never completed
  (`worker_stream` / `internal`). Total derivable; tells you *which* target lost
  lines.
- **`started_at` = first-claim-only** — set once, never overwritten on re-claim,
  never cleared on recovery. `queue_wait = started_at - created_at` (true
  first-attempt wait). `finished_at - started_at` covers run + any retries +
  restart downtime (documented; use `attempts` to disambiguate).
- All new timestamps timezone-aware (`DateTime(timezone=True)`), matching
  existing `created_at`/`finished_at`.
- Logging configured at the **runtime boundary** (backend lifespan / worker
  `server.py`-owned lifespan), never import-time. The shared `pkg-translator`
  library only exposes a `lifespan` passthrough — it never configures handlers.

---

## 1. Schema — `Job` new columns

File: `srt-backend/pkg-job-orch/src/pkg_job_orch/models.py`

Add to `Job`:

| Column | Type | Default | Purpose |
|---|---|---|---|
| `started_at` | `datetime \| None` (tz-aware) | `None` | set ONCE on first `pending→processing` claim. `started_at - created_at` = first-attempt queue wait. |
| `error_kind` | `str \| None` | `None` | failure category enum (below). Group/filter fails without parsing free text. |
| `dropped_by_target` | `str \| None` (JSON text) | `None` | per-target untranslated-cue counts `{"fr":2,"es":0}`. Set on `done` + `landing` fails. `None` = translation never completed (`worker_stream`/`internal`). |
| `attempts` | `int` | `0` | incremented each claim. Survives recovery re-enqueue → shows retry history. |

Keep free-text `error` (human message); `error_kind` is the machine tag.

`error_kind` values (module constant / str literals):
- `worker_stream` — `WorkerStreamError` (worker error / drop / non-2xx / bad JSON).
- `internal` — unexpected exception during translation.
- `landing` — result-write / DB failure after successful translation.
- (extend later: `validation`, `timeout`.)

`dropped_by_target` helpers (mirror `tgt_langs_*` CSV pattern): small
`dropped_to_json(dict[str,int]) -> str` / `dropped_from_json(str|None) ->
dict[str,int]`. Keep JSON in the column, dicts in code.

Update `model_dump_summary()` → add `error_kind`, `attempts`, `started_at`
(isoformat or None). (Leave heavy `dropped_by_target` to the detail view.)

---

## 2. Migration — `0003_job_debug_fields.py`

Dir: `srt-backend/pkg-job-orch/src/pkg_job_orch/migrations/versions/`
`down_revision = "0002_users_google_sub_processed_events"` (verify id inside 0002).

`upgrade()`:
```python
op.add_column("job", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("job", sa.Column("error_kind", sa.String(), nullable=True))
op.add_column("job", sa.Column("dropped_by_target", sa.String(), nullable=True))   # JSON text
op.add_column("job", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
```
`downgrade()`: drop the four columns.
(`started_at`/`dropped_by_target` nullable, no server_default → clean `None`.
`attempts` non-null with `server_default="0"` for any existing rows.)

---

## 3. Orchestration wiring

File: `srt-backend/pkg-job-orch/src/pkg_job_orch/orchestration.py`

### 3a. Claim (Phase 1, `_process_job` ~line 270)
On `pending→processing`:
```python
job.status = "processing"
if job.started_at is None:          # first-claim-only — never overwrite
    job.started_at = datetime.now(UTC)
job.attempts += 1
```

### 3b. `_mark_failed` — take a kind + optional dropped counts
Signature → `_mark_failed(job_id, message, kind, dropped=None)`. Set
`row.error_kind = kind`; write `row.dropped_by_target = dropped_to_json(dropped)`
only when `dropped is not None` (else leave `None`).
Call sites in `_process_job`:
- `WorkerStreamError` branch → `_mark_failed(job_id, str(exc), "worker_stream")`
  (dropped=None — translation never finished) **+ add `logger.exception(...)`**
  (currently no traceback on the most common fail).
- generic `Exception` branch → `_mark_failed(job_id, f"internal error: {exc}", "internal")`
  (dropped=None).
- landing — TWO handlers (counts may or may not be known):
  ```python
  try:
      _land_results(ctx, job_id, outcome)
  except LandingError as exc:                    # I/O failed AFTER counts computed
      _mark_failed(job_id, f"failed to land results: {exc}", "landing", dropped=exc.dropped)
  except Exception as exc:                        # counts unknown (build/serialize failed)
      logger.exception("landing failed pre-count for job %s", job_id)
      _mark_failed(job_id, f"failed to land results: {exc}", "landing", dropped=None)
  ```
  This prevents a pre-count failure (`int(seg["id"])`, `serialize`) from masking
  the real error or leaving the job unmarked.

### 3c. Per-target dropped counts (backend-side, no worker change)
`_build_outputs` (~line 386) already falls back to the untranslated original
cue when a translation is missing. Count per target:
```python
dropped: dict[str, int] = {}
for tgt in outcome.targets:
    n = 0
    translated: list[Cue] = []
    for cue in cues:
        entry = by_id.get(cue.index)
        text = entry.get(tgt) if entry else None
        if isinstance(text, str):
            translated.append(Cue(cue.index, cue.start, cue.end, text))
        else:
            translated.append(cue)
            n += 1
    outputs[tgt] = serialize(translated)
    dropped[tgt] = n
return outputs, dropped        # was: outputs
```
Landing flow (so counts survive a landing failure). `_build_outputs` is NOT
guaranteed pure — `int(seg["id"])` and `serialize` can raise. So structure
`_land_results` as two phases:
1. **Compute** `outputs, dropped` (may raise — parse/serialize). If it raises
   here, it propagates as a plain exception → `_process_job`'s generic landing
   handler marks failed with `dropped=None` (counts genuinely unknown).
2. **Persist** — file saves + `status=done` tx, wrapped so any failure becomes
   `raise LandingError(str(err), dropped=dropped) from err`. On success write
   `row.dropped_by_target = dropped_to_json(dropped)` in the same tx; log
   `warning` if `sum(dropped.values()) > 0`.

Add `class LandingError(RuntimeError)` in this module with an optional
`dropped: dict[str,int] | None = None` attr (constructor stores it). Only the
persist phase raises it — so `exc.dropped` is always populated when the
`LandingError` handler runs.

### 3d. Recovery keeps history
`recover_jobs` (~line 220): on `processing→pending` — **keep `started_at`,
`attempts`** (history). Reset `error`/`error_kind`→None, `progress`→0.0. Do NOT
touch `dropped_by_target` (stays None on a job that never landed).

---

## 4. Route exposure

File: `srt-backend/pkg-job-orch/src/pkg_job_orch/routes.py`

`get_job` detail dict (~line 86) — add:
`created_at`, `started_at`, `finished_at` (isoformat or None), `error_kind`,
`attempts`, and `dropped_by_target` (parsed dict via `dropped_from_json`, or
omit when None). `created_at` is **required** so the client can compute
`queue_wait = started_at - created_at`. `error` already exposed.

---

## 5. Logging config (runtime boundary, ~10 lines)

Without this, breadcrumbs stay invisible (gap #1). Configure where the process
actually starts — never at import (would fire during tests, and may lose to
uvicorn's own handler setup).

- **Backend** launched as `uvicorn srt_backend.app:api` (Makefile:45) — no
  `server.py`. Configure inside the existing `lifespan` startup
  (`srt_backend/app.py:60`), before building `JobContext`:
  `logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))` +
  ensure a handler (add one if root has none — uvicorn configures its own
  loggers but not root). Alternatively ship a uvicorn `--log-config`; lifespan
  is simpler and matches their runtime-boundary convention.
- **Workers** (`srt-cloud-worker`, `srt-mlx-worker`) run via
  `uvicorn ...server:app` (Makefile:51,54) — `main()` NEVER fires on that path,
  and top-level `basicConfig` is import-time (banned). But **`pkg-translator` is
  a shared library — it must NOT configure logging handlers itself** (repo rule).
  So split hook vs config:
  - **Library** (`pkg_translator.create_app`, `app.py:46`, currently bare
    `FastAPI(...)`): add an optional `lifespan` PARAM, forwarded to
    `FastAPI(..., lifespan=lifespan)`. Pure passthrough — no logging code in the
    library.
  - **Worker `server.py`** (the runtime entry point) OWNS the config: define a
    `@asynccontextmanager lifespan` that runs
    `logging.getLogger().setLevel(os.environ.get("LOG_LEVEL","INFO"))` + ensures
    a handler on startup, and pass it into `create_app(..., lifespan=...)`. Runs
    on the uvicorn path (module-level `app`), no `main()` needed. `main()` may
    also set it for the direct-CLI path.
  - Alt (no python change): uvicorn `--log-config <file>` in the Makefile
    commands. Cleaner re: rule but adds a config file + per-deploy wiring;
    lifespan-passthrough is more robust across launch methods.

Out of scope (deferred): correlation `job_id` → worker request; append-only
`job_event` audit table; LLM prompt/response capture to Storage.

---

## 6. Tests

- Claim/timing: assert `started_at` set on first claim; a second claim (after
  recovery) does NOT change `started_at`; `attempts` increments each claim;
  recovery preserves `started_at` + `attempts`, resets `error_kind`→None.
- `error_kind`: each failure branch (`worker_stream`/`internal`/`landing`) sets
  the right tag. `dropped_by_target` stays `None` for `worker_stream`/`internal`;
  on a `landing` failure where I/O breaks AFTER counts (stub `Storage.save` to
  raise) → `error_kind=landing`, `dropped_by_target` IS persisted. Separately,
  a pre-count landing failure (malformed segment id → `int()` raises in
  `_build_outputs`) → `error_kind=landing`, `dropped_by_target=None`, job marked
  failed (not left unmarked, original error not masked).
- Dropped per-target: fake worker returns partial `segments` (one id missing for
  target `fr`, complete for `es`) **with ≥2 targets** → assert
  `dropped_by_target == {"fr":1,"es":0}`, job still `done`.
- Route: `get_job` detail includes `created_at` + `started_at` serialized;
  `queue_wait` computable.
- Migration: `init_schema` covers test DBs; add alembic upgrade/downgrade smoke
  test if the suite has a pattern.

---

## Order of work
1. models.py columns + JSON helpers + `model_dump_summary`
2. migration 0003
3. orchestration (first-claim `started_at`/`attempts`, `_mark_failed` kind +
   optional `dropped` + `logger.exception`, `LandingError` carrying counts,
   per-target dropped, recovery keeps history)
4. routes exposure (incl. `created_at`)
5. logging: backend lifespan; `create_app` gains handler-free `lifespan` param;
   worker `server.py` defines + passes its logging lifespan. No top-level
   `basicConfig`, no logging code in `pkg-translator`.
6. tests
