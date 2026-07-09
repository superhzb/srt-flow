# srt-flow — Delivery Plan

Ship in thin end-to-end slices. Each slice demoable on its own. Detail lives in per-project docs:
- `srt-backend/DESIGN.md` — backend architecture, contracts, request flow, dev auth
- `srt-frontend/DESIGN.md` — SPA stack, screens, API usage
- `srt-mlx-worker/PLAN.md` — translation worker (built)

## Principle

Vertical slices, not horizontal layers. Never build a package in isolation — build it inside the feature that consumes it, tested against a real caller. `AUTH_MODE=dev` removes auth from the critical path so early slices need no OAuth/billing.

---

## Slice 1 — Parse SRT to cues  ✅ done

`upload .srt → backend parses → frontend shows cue JSON`. Synchronous. No DB, no storage, no worker, no job lifecycle, no auth. Smallest possible walking skeleton that proves the wire: file leaves browser, structured data comes back rendered.

**Touches**: pkg-srt-services (`parse`) + minimal FastAPI + minimal SPA.
**Cut**: everything else — translation, jobs, disk storage, DB, auth, langs.

### Backend tasks
1. FastAPI app skeleton — mount pkg routers under `/api` (dev CORS or Vite proxy; StaticFiles deferred).
2. `pkg-srt-services` — implement `parse(str) -> list[Cue]` (+ `serialize` can wait). `Cue = {index, start, end, text}`.
3. `POST /api/srt/parse` (multipart `.srt`) → read bytes → `parse()` → `200 {cues:[...], count}`. `400` on unparseable.

### Frontend tasks
1. Scaffold Vite + React + TS + Tailwind. Dev proxy `/api → backend`.
2. `/` — drop/pick `.srt` (validate ext/non-empty) → `POST /api/srt/parse`.
3. Render returned cues — table (index / start→end / text) + raw-JSON toggle. Show error on 400.

### Definition of done
Open app → drop a real `.srt` → see its cues as a JSON/table in the browser. One request, one response. No login, no spinner-forever.

### Integration checkpoint
- `curl -F file=@sample.srt localhost:PORT/api/srt/parse` returns cue JSON before wiring frontend.

---

## Slice 2 — Detect → pick targets → translate → download  ⬅ next

Full round-trip, in-memory, no DB/disk/auth. Upload `.srt` → backend detects source
language → user confirms source, picks **worker** + one-or-more **target** languages →
Process → determinate progress bar (per-target × per-batch) → view + download one `.srt`
per target.

Deliberately **stripped** vs the north-star DESIGN: no SQLite, no `pkg-file-upload`,
no `pkg-job-orch`, no persisted `job` table. Jobs live in an in-process `dict` and are
lost on restart — that's fine for the slice. DB/storage/auth layer on later (slices 3+).

### Language detection (by code — yes)

Detect from parsed cue text; it's a **suggestion**, user can override.

- Lib: `lingua-language-detector` (deterministic, good on subtitle-length text, gives
  confidence). Sample ~40 non-empty cue texts, join, detect.
- Map ISO result → worker-supported codes (`en es zh zh-TW fr de ja ko`).
- **Chinese script split**: detectors emit one `CHINESE`; worker splits `zh` (Simplified)
  vs `zh-TW` (Traditional). If detected Chinese, run a Simplified/Traditional char
  heuristic (`hanzidentifier`) → choose `zh` or `zh-TW`.
- Unmappable / low-confidence → return `null`, UI leaves source unselected.

### Worker choice

Two workers share one contract (`/translate`, `/languages`, `/health`) and identical
`languages.yaml`: `srt-cloud-worker` (DeepSeek, needs `DEEPSEEK_API_KEY`) and
`srt-mlx-worker` (local MLX, Apple-silicon). User picks on the UI.

- Backend config maps `worker_id → base_url` (env `WORKERS=cloud=http://…,mlx=http://…`).
- `GET /api/workers` → `[{id, label, healthy}]`. Probe every worker's `/health`
  **in parallel**, **~1s timeout** each; unreachable/timeout → `healthy: false` (never
  block the response on a dead worker).
- Both **source and target** dropdowns are filled from **one** per-worker list
  (`GET /api/languages?worker=…`) — refetched when the worker changes, in case the two
  ever diverge. (Target select = list minus the chosen source.)

### Progress model (per-target × per-batch)

Worker batches internally (`context_window=3`, plus binary split-retry on validation
failure — all kept). `batch_size` is **worker-owned and differs** (cloud=100, mlx=10),
so the backend must **not** hardcode it — the denominator comes from `batch_total` in
the stream. To move the bar smoothly instead of in N-target jumps, the worker **streams
batch-level progress**; backend folds it into a single fraction.

- **Denominator** = `Σ over targets of ceil(n_segments / batch_size)` top-level batches,
  learned from the stream's `batch_total` per target (not computed backend-side).
  Sub-splits from `_translate_with_split` happen *within* a batch unit — they don't
  change the denominator.
- **Worker change** (least-invasive): add optional `on_progress` callback threaded
  through `translate_segments` → `_translate_all`, fired once per top-level batch. Wire
  it to a new `POST /translate/stream`. **This change lands in BOTH `srt-cloud-worker`
  and `srt-mlx-worker`** (translator/app are near-identical copies; no shared pkg, so
  edit both). Existing non-streaming `POST /translate` stays.

**Wire format: NDJSON** (one JSON object per line, `\n`-terminated) — backend is the only
consumer (server-to-server), so no EventSource/SSE framing needed; stream is read via
`httpx2` `aiter_lines`. Event shapes:

```
{"event":"progress","target":"fr","target_index":0,"target_total":2,
                     "batch_index":3,"batch_total":9}
{"event":"result","source_lang":"en","targets":["fr","de"],"segments":[...]}   // mirrors TranslationResponse
{"event":"error","detail":"<message>"}                                          // terminal
```

Exactly one terminal event (`result` **or** `error`) closes the stream.

- Backend consumes the stream, updates `job.progress = batches_done / batch_total_sum`.
- **Failure policy**: an `error` event, a dropped/timed-out connection, or a non-2xx
  open → `job.status = failed`, `job.error = detail`, **partial results discarded**
  (all-or-nothing; no half-translated `.srt` returned).

### Backend endpoints (all `/api`, `AUTH_MODE=dev` — no real auth)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/workers` | — | `[{id, label, healthy}]` |
| GET | `/api/languages` | `?worker=` | `{languages:[{code, name}]}` — **pass-through** worker `available_languages()` (`{code, name}`), no key rename |
| POST | `/api/srt/prepare` | multipart `.srt` | `{cues, count, detected_lang, confidence}` — one call fills the configure screen (reuses slice-1 `parse`) |
| POST | `/api/translate` | `{cues, source_lang, targets[], worker}` | `202 {job_id}`; spawns background task |
| GET | `/api/translate/{job_id}` | — | `{status: pending\|processing\|done\|failed, progress: 0..1, results?:[{lang, srt}], error?}` |

**Cue→segment adapter**: worker wants `segments=[{id, "<source_lang>": text}]`; backend
maps `id = cue.index`, `"<source_lang>" = cue.text`. On `result`, invert per target:
clone cues, replace `text` with `segment["<tgt_code>"]` keyed by `id`, then
`pkg_srt_services.serialize(...)` → one `.srt` string per target.

Background task: stream worker `/translate/stream` with all targets → on each `progress`
event bump `job.progress` → on `result` rebuild `.srt` per target → `job.results`. On
`error`/drop → `job.status=failed` (partials discarded, see failure policy above).
In-memory `dict[job_id, Job]`, no persistence.

### Backend deps (`srt-backend/pyproject.toml`)

Add `lingua-language-detector`, `hanzidentifier`. **`httpx2>=2.5.0` already present** —
use it for the streaming worker client; do **not** add a second HTTP dep.

### Frontend (`srt-frontend/src`)

Extend the state machine past slice-1's upload→cues:

1. Upload → `POST /api/srt/prepare` (replaces bare `parseSrt`).
2. **Configure screen**: worker dropdown (`GET /api/workers`), source dropdown
   pre-filled with `detected_lang`, target multi-select (`GET /api/languages?worker=`,
   minus source), **Process** button.
3. `POST /api/translate` → `{job_id}` → poll `GET /api/translate/{job_id}` ~1.5s →
   **determinate progress bar** from `progress` (+ optional "target k/n · batch j/m" text).
4. Done → one result panel per target (reuse `CuesView` table + raw-srt toggle) +
   per-lang **Download** (Blob → `name.<lang>.srt`).

`api.ts`: add `getWorkers`, `getLanguages`, `prepareSrt`, `startTranslate`,
`pollTranslate`.

### Definition of done

Upload real `.srt` → source auto-detected → pick worker + 2 targets → Process → bar
fills as batches complete → two translated `.srt` render and download. No login, no DB.

### Integration checkpoints

- `curl -F file=@sample.srt localhost:PORT/api/srt/prepare` → cues + `detected_lang`.
- `curl -N` the worker `/translate/stream` → see `progress` events then `result`.
- Full flow via UI against a live worker before polishing.

### Deferred to later slices (unchanged)

`pkg-file-upload` (LocalStorage), `pkg-job-orch` + SQLite `job` table + persisted status,
auth/OAuth, billing/quota, notification, download-via-authed-route. This slice's
in-memory job registry is replaced by `pkg-job-orch` in slice 3.

## Slice 3 — Persist jobs (`pkg-job-orch` + `pkg-file-upload`)  ⬅ next after slice 2

Replace slice-2's in-memory `dict[job_id, Job]` with a durable job lifecycle:
SQLite `job` table + input/output `.srt` on disk. Jobs survive restart; a jobs list
shows history. Still `AUTH_MODE=dev` — one seeded dev user owns every job. **No OAuth, no
billing** — auth is bumped to slice 4 so this slice is purely about orchestration.

### What job orchestration *does*

The durable lifecycle manager for translation work. In one line: *take a translate
request, persist it, run it to completion on a single background worker, and serve its
status / history / artifacts — all surviving a process restart.* Concretely:

1. **Accept + persist** — `enqueue()`: `serialize(cues)` → `Storage.save(input.srt)` →
   `INSERT job(pending)` → put id on an in-proc `asyncio.Queue` → `202 {job_id}`. The HTTP
   request no longer holds job state; the row does. **The queue is volatile** — it holds
   nothing durable. Durability = the DB row plus the boot-time replay (every `pending` job
   re-enqueued on startup, see Restart recovery). A lost queue never loses a job.
2. **Claim + run** — one `worker_loop()` asyncio task (started via the app lifespan, see
   *Worker lifecycle*) pulls pending jobs **one at a time** (`concurrency=1` — SQLite
   single writer + mlx single-threaded; queue, don't blast), flips `processing`, streams
   the slice-2 worker `/translate/stream`, folds each `progress` event into `job.progress`.
3. **Land results** — on `result`, rebuild one `.srt` per target →
   `Storage.save(output.<lang>.srt)` → `status=done`. On `error`/drop → `status=failed`,
   partials discarded (slice-2 all-or-nothing policy unchanged). **No output file exists
   before this step** — `Storage.save(output.*)` fires only on `result`, so a job killed
   mid-flight leaves zero `output.<lang>.srt` on disk. Resume is therefore clean; no
   partial-file glob-and-delete needed.
4. **Serve** — status poll, jobs list, and (soon-to-be-)auth-gated download route, all
   DB/disk-backed.

Delta vs slice 2 = **durability, a queue, and history**. The translation path itself does
not change.

### Packages pulled in

- **pkg-file-upload** — `Storage` iface (`save/get/delete/url_for`) + `LocalStorage`.
  Layout `{STORAGE_ROOT}/{user_id}/{job_id}/{input.srt, output.<lang>.srt}`. Build the
  iface even though only Local exists — the seam is the point (swap R2/S3 later, no caller
  change).
- **pkg-job-orch** — `Job` model, `enqueue()`, `worker_loop()`, `router`
  (create/list/get/download). Depends on file-upload + srt-services + the slice-2
  streaming worker client (reused, not rewritten). Notification dep **stubbed** (no-op)
  until slice 6.

### Data model (SQLite — first real tables)

```
user (id, email, tier, created_at)              -- only the seeded dev user for now
job  (id, user_id FK, status, worker, src_lang,
      tgt_langs,                                 -- CSV/JSON: one job = one upload, N targets
      progress REAL, error,
      created_at, finished_at)
```

**One job = one upload → N targets** (matches slice-2 multi-select). Outputs keyed by lang
on disk; the row carries no per-target path (derive `{job_id}/output.<lang>.srt`). Use
SQLModel over raw `sqlite3` for the typed model.

**Dep + engine ownership.** `pkg-job-orch` owns the DB: it declares the `sqlmodel`
dependency (add to `pkg-job-orch/pyproject.toml` — `srt-backend` picks it up transitively
via the path dep, so add `pkg-job-orch` to `srt-backend` deps too), defines the `Job`
model, and constructs the single `Engine`. `pkg-file-upload` never touches the DB — it
owns disk only. The `user` table lives in job-orch for slice 3 (one dev row); slice 4
hands `user` ownership to `pkg-auth` when OAuth lands.

**`DATABASE_URL` + bootstrap.** `pkg-job-orch` reads `DATABASE_URL`
(`sqlite:///./.data/dev/db.sqlite` per DESIGN.md) at a runtime boundary — inside a
`get_engine()` / config call, **never at import** (AGENTS.md: no import side effects).
The engine is built once and reused. Schema bootstrap runs in the app lifespan (below),
not at import.

**Migrations — Alembic from day one.** Slice 3 is one table but slice 4 mutates `user`
(adds `google_sub`, etc.) and slice 5 adds `usage`. Backfilling migrations after real dev
data exists is the expensive path. So: wire Alembic now with an initial revision that
creates the slice-3 schema; the lifespan runs `alembic upgrade head` on startup. (Do **not**
use `SQLModel.metadata.create_all()` — it cannot ALTER for slice 4, and mixing it with
Alembic later causes drift.) Add `alembic` to `pkg-job-orch` deps.

### Worker lifecycle (app lifespan)

`app.py` has no lifespan yet — add a FastAPI `lifespan` context that, in order:

1. **startup** — `alembic upgrade head`; seed the dev user if absent (see below);
   run the recover-scan (reset `processing` → `pending`, re-enqueue all `pending`);
   `asyncio.create_task(worker_loop())`.
2. **shutdown** — signal the loop to stop and `await` its cancellation cleanly (no
   half-written rows; the in-flight job is left `processing` and resumes next boot).

**Dev-user seeding.** Slice 3 has no auth, but `job.user_id` FK needs a target row. The
lifespan seeds one dev user (`DEV_USER_EMAIL`, synthetic id, `google_sub=NULL`) on startup
if it does not already exist — idempotent. All slice-3 jobs point at it. Slice 4 replaces
this seed path with real OAuth upserts.

### Restart recovery (the reason to persist at all)

On startup any job left in `processing` was interrupted mid-flight. Input `.srt` is on
disk and translate is idempotent → **reset `processing` → `pending`**. The loop then
resumes it exactly like a fresh job: `Storage.get(input.srt)` → `parse()` → cues →
re-issue `/translate/stream`. (Alternative: mark failed — but resume is friendlier and
cheap since input persisted. Recommend resume.) Existing `pending` jobs re-enqueue on boot
too. This recover-scan runs in the lifespan startup, before the loop is created.

### Endpoints (`/api`, still `AUTH_MODE=dev` — no real auth)

Rename slice-2 `/api/translate*` → `/api/jobs*` to match north-star DESIGN now (cheap
while the frontend is small):

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/jobs` | `{cues, source_lang, targets[], worker}` | `202 {job_id}` — serialize+save input, INSERT pending, enqueue |
| GET | `/api/jobs` | — | `[{id, status, src_lang, tgt_langs, progress, created_at}]` (dev user's) |
| GET | `/api/jobs/{id}` | — | `{status, progress, results?:[{lang, download_url}], error?}` |
| GET | `/api/jobs/{id}/download` | `?lang=` | stream `output.<lang>.srt` via `Storage.get` |

Download route exists but **ungated** now — slice 4 adds one `get_current_user` dependency
+ ownership check; no shape change.

### Frontend

Minimal shift off slice 2: point the poll at `/api/jobs/{id}`; download hits the route
(`<a href>` / fetch-blob) instead of the inline srt string. Add a **Jobs** list screen
(history table from `GET /api/jobs`) — the first thing persistence buys the user.

**Wire-shape break — do not miss this in the SPA refactor.** The `results` element changes
shape between slices; the poll response is not backward-compatible:

| | slice 2 (`GET /api/translate/{id}`) | slice 3 (`GET /api/jobs/{id}`) |
|---|---|---|
| `results[]` | `{lang, srt}` — full SRT text inline | `{lang, download_url}` — no body |

The SPA must stop reading `results[].srt` and instead fetch/link `results[].download_url`
(→ `GET /api/jobs/{id}/download?lang=`). Same for the endpoint rename `/translate*` →
`/jobs*`.

### Definition of done

Upload → translate → a `job` row lands in SQLite, input/output `.srt` on disk.
**Kill the backend mid-processing → restart → the job resumes and finishes** (or fails
cleanly), and every completed job still shows in the jobs list with a working download.
Nothing lives only in RAM. Still no login.

### Integration checkpoints

- `sqlite3 .data/dev/db.sqlite 'select id,status,progress from job'` after a POST.
- `ls .data/dev/storage/<uid>/<jid>/` → `input.srt` + `output.*.srt`.
- Start a job → `kill` uvicorn mid-run → restart → job reaches `done`.

### Tests

Follows the slice-2 pattern (`tests/test_translate_route.py`, `test_prepare_route.py`, …):

- `srt-backend/tests/test_jobs_route.py` — POST returns `202 {job_id}` + INSERTs a
  `pending` row; `GET /api/jobs` lists the dev user's jobs; `GET /api/jobs/{id}` shape
  (`results[].download_url`, not `.srt`); download streams the right file.
- `srt-backend/tests/test_restart_recovery.py` — seed a `processing` row → run the
  recover-scan → assert reset to `pending` and re-enqueued; a `done` job is untouched.
- `pkg-job-orch/tests/test_enqueue.py` — `Job` model round-trips through the engine;
  `enqueue()` serializes + saves input + inserts pending; dev-user seed is idempotent.
- `pkg-file-upload/tests/test_local_storage.py` — `LocalStorage` `save`/`get`/`delete`
  round-trip under the `{root}/{uid}/{jid}/` layout; `url_for` shape.

Use a temp `DATABASE_URL` (`sqlite://` in-memory or tmp file) + temp `STORAGE_ROOT` per
test; no real `.data/`. Alembic `upgrade head` against the temp DB in a fixture.

### Deferred to slice 4 (auth)

Real Google OAuth, JWT httpOnly cookie, `get_current_user`, `/api/auth/me` gate, per-user
job filtering, download auth gate, `/login`. Job-orch already writes `user_id` (the dev
user) and the download route already exists — slice 4 switches to `AUTH_MODE=google` and drops
the auth dependency in. Clean seam.

## Slice 4 — Real auth

Switch to `AUTH_MODE=google`. Google OAuth, JWT httpOnly cookie, `get_current_user`,
  `GET /api/auth/me` gate, `/login`. Wire the auth dependency into the slice-3 job routes
(per-user job filtering + download ownership check). `user` table already exists from
slice 3 — this slice fills it from real Google identities instead of the seeded dev user.

## Slice 5 — Billing + quota

Free-tier guard → 402 over limit. Stripe checkout + webhook → tier=paid. Frontend `/billing`.

## Slice 7 — Deploy

2 uvicorn procs (staging :8001 / prod :8002) + cloudflared. StaticFiles serve `dist/` same-origin. Storage/DB outside repo (`~/srt-storage`, `~/srt-data`).

---

## Sequencing rationale

Slices 1–2 prove the money path (translation) with least surface, all in-memory. Slice 3
makes it durable (job-orch + storage) — the spine everything else needs. Auth/billing/notify
then layer onto that spine — each independently shippable, each demoable. Deploy last, once
there's something worth exposing.

## Outsourcing note

`pkg-file-upload` (+ optionally `pkg-notification`) are the clean split-to-other-team candidates — zero internal deps, frozen contracts. File-upload lands slice 3 (core dependency); keep in-house until its contract is battle-tested, hand off after. Notification (slice 5) is the cleaner pure handoff.
