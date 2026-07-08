# srt-flow — Prototype Design

Goal: simplest possible working prototype. One Mac, Cloudflare Tunnel, staging + prod.

## Decisions

- **App topology**: single FastAPI mono-app. Imports all `pkg-*` as libraries, mounts their routers. One uvicorn process per env.
- **Database**: SQLite, one `.db` file per env. Migrate to Postgres when concurrency hurts.
- **Default worker**: `srt-mlx-worker` (already built, local MLX model, free). Wire first.
- **Auth**: Google OAuth only. No passwords.

## Architecture

```
                 Cloudflare Tunnel
          staging.you.com→8001  app.you.com→8002
                        │
        ┌───────────────▼────────────────┐
        │   FastAPI mono-app (uvicorn)     │
        │   imports pkg-* routers          │
        │  ┌──────────┬──────────┬──────┐  │
        │  │ pkg-auth │file-upload│ ...  │  │
        │  └──────────┴──────────┴──────┘  │
        │   in-proc asyncio job worker     │
        └───┬──────────────┬───────────┬───┘
            │              │           │
        SQLite {env}.db  disk storage  HTTP → srt-mlx-worker (:801x)
                         ~/srt-storage/{env}/{uid}/{jid}/
```

`pkg-srt-services` = pure parse/serialize lib (SRT text ↔ cue list). No network. Imported by app and workers.

## Components

| Piece | Choice | Why |
|---|---|---|
| Web framework | FastAPI mono-app importing pkgs | pkgs already Python |
| DB | SQLite per env → Postgres later | one file, zero setup |
| Sessions | JWT httpOnly cookie | no session store |
| Queue | in-process asyncio / BackgroundTasks | one Mac, low volume |
| Storage | local disk behind `Storage` iface | swap to R2/S3 later, no caller change |
| Translate worker | srt-mlx-worker (local MLX) | built, free; cloud-worker later for scale |
| Deploy | 2 uvicorn procs (diff port+env) + cloudflared | staging + prod on one Mac |

## Data model (SQLite)

```
user   (id, google_sub UNIQUE, email, tier[free|paid], created_at)
job    (id, user_id FK, status[pending|processing|done|failed],
        input_path, output_path, worker, error, src_lang, tgt_lang,
        created_at, finished_at)
usage  (user_id, month, job_count)   -- free-tier guard; or COUNT(job)
```

## Request flow

All pkg routers mount under **`/api`** (frontend serves SPA at `/*`; API namespaced so static fallback never collides).

```
0. GET  /api/auth/me            → current user + tier | 401   (frontend session bootstrap)
1. GET  /api/auth/google/login  → redirect Google
2. GET  /api/auth/google/callback → mint JWT cookie, upsert user
3. GET  /api/languages          → src/tgt lang list (proxy srt-mlx-worker /languages)
4. POST /api/jobs (multipart srt+src_lang+tgt_lang) → tier guard (402 if over quota)
                                → Storage.save(input) → INSERT job(pending) → enqueue → 202 {job_id}
5. worker loop: claim pending → status=processing
                → POST srt-mlx-worker /translate (input srt)
                → Storage.save(output) → status=done → notify
6. GET  /api/jobs               → list caller's jobs (frontend jobs table)
7. GET  /api/jobs/{id}          → status poll
8. GET  /api/jobs/{id}/download → auth check → stream output.srt
9. POST /api/billing/checkout   → Stripe link
10.POST /api/billing/webhook    → tier=paid
```

### Frontend-driven additions (from srt-frontend/DESIGN.md)

Three items the original design lacked; required by SPA:

1. **Router prefix `/api`** on every pkg router — reserves `/*` for static SPA + `index.html` fallback.
2. **`GET /api/auth/me`** → `{email, tier}` or 401 — SPA has no client token; bootstraps session on load.
3. **`GET /api/jobs`** → list caller's jobs — SPA jobs table (design only had single-`{id}` get).

SPA served same-origin via `StaticFiles(dist/)` so JWT httpOnly cookie needs no CORS.

### Dev auth bypass

Google OAuth loop is slow to iterate against. In **dev only**, skip it.

```
DEV_AUTH=1   (only honored when ENV=dev)
DEV_USER_EMAIL=dev@local        # upserted on startup
DEV_USER_TIER=paid              # test paid features without Stripe
```

Behavior when `ENV==dev and DEV_AUTH`:
- `get_current_user()` returns the seeded dev user directly — no cookie/JWT needed.
- `GET /api/auth/me` → dev user (never 401) → SPA skips `/login`.
- `/api/auth/google/*` still work if you want to test real OAuth; bypass just removes the requirement.

**Hard gate (security):**
- `DEV_AUTH` is ignored unless `ENV=="dev"`. In staging/prod it does nothing even if set.
- App **refuses to start** if `ENV in {staging,prod}` and `DEV_AUTH` truthy — fail loud, never silently ship an open door.
- No dev user seeded, no bypass path registered, when `ENV!=dev`.

Frontend: nothing special — `/api/auth/me` returns a user, so the session gate passes. Real Google button only exercised when `DEV_AUTH` off.

## Package contracts (public `api.py` only)

| pkg | exposes | depends on |
|---|---|---|
| pkg-auth | `router` (login/callback + **`/me`**), `get_current_user`, `require_tier()` | db |
| pkg-file-upload | `Storage` (save/get/url_for/delete), `LocalStorage`, download `router` | — |
| pkg-srt-services | `parse(str)->cues`, `serialize(cues)->str` | — |
| pkg-job-orch | `router` (create/**list**/get/download), `enqueue()`, `worker_loop()`, `Job` model | file-upload, srt-services, notification, worker HTTP |
| pkg-billing | `router` (checkout+webhook), `check_quota(user)` | auth, db |
| pkg-notification | `notify_job_done()`, `notify_job_failed()` | email provider (Resend/SMTP) |

**Rule**: pkgs import each other only via `api.py`, never internals → clean split-to-services later.

## Storage + DB layout

**Dev (now): in-repo under `.data/` (gitignored).** Easy to inspect/wipe.

```
srt-flow/.data/
  {env}/
    db.sqlite
    storage/{user_id}/{job_id}/
      input.srt
      output.srt
```

- dev:     `STORAGE_ROOT=./.data/dev/storage`   `DATABASE_URL=sqlite:///./.data/dev/db.sqlite`
- staging: `STORAGE_ROOT=./.data/staging/storage`
- prod:    `STORAGE_ROOT=./.data/prod/storage`

**Prod deploy: move OUTSIDE repo** (`~/srt-storage`, `~/srt-data`) — deploy resets repo dir, would kill data. `.data/` is gitignored so nothing commits.

Local files not web-reachable → serve downloads through auth-gated FastAPI route, never expose disk paths.

## Env config (`.env.{staging,prod}`)

```
ENV=dev
DEV_AUTH=1                                     # dev only: skip Google OAuth (ignored/blocked if ENV≠dev)
DEV_USER_EMAIL=dev@local  DEV_USER_TIER=paid   # seeded dev user when DEV_AUTH on
STORAGE_ROOT=./.data/dev/storage              # in-repo dev; prod → ~/srt-storage
DATABASE_URL=sqlite:///./.data/dev/db.sqlite  # in-repo dev; prod → ~/srt-data
WORKER_URL=http://localhost:8010              # mlx-worker
GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...
JWT_SECRET=...
STRIPE_SECRET=... STRIPE_WEBHOOK_SECRET=...
RESEND_API_KEY=...
```

## Deploy shape (one Mac)

```
uvicorn app:api --port 8001   # staging, .env.staging, staging.db, storage/staging
uvicorn app:api --port 8002   # prod,    .env.prod,    prod.db,    storage/prod
cloudflared → staging.you.com→8001, app.you.com→8002
```

## Sharp edges

- **Storage in `.data/` for dev, outside repo for prod** — `.data/` gitignored so it never commits; prod deploy resets repo dir, so point `STORAGE_ROOT`/`DATABASE_URL` at `~/srt-storage`/`~/srt-data` there.
- **SQLite single writer** — run ONE worker loop per db. No parallel writers.
- **mlx-worker single-threaded** — one model, serial translation. job-orch → concurrency=1 to mlx. Queue, don't blast.
- **Downloads via route** — auth-gate every download; local files not directly reachable.
- **Free-tier guard** — count jobs/month before `Storage.save`, block at limit.

## Build order

1. pkg-auth (Google) + DB models + FastAPI app skeleton
2. pkg-file-upload (`Storage` iface + LocalStorage) + download route
3. pkg-job-orch (job table + in-proc worker) wired to srt-mlx-worker
4. pkg-notification (email on done/failed)
5. pkg-billing (Stripe checkout + webhook + tier guard)
6. srt-cloud-worker (only if Mac not enough)
