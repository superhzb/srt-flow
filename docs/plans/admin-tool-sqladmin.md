# Plan: Replace dev DB tab with read-only SQLAdmin admin tool

## Goal

Remove the unauthenticated raw-DB browser from the frontend/backend and replace it
with a **read-only**, admin-gated SQLAdmin surface mounted at `/admin`. Establish an
admin gate (env allowlist) so production inspection has a safe home. All mutations
(grant credit, suspend, tier change) are deferred to explicit audited domain endpoints
in a later phase — SQLAdmin here is inspection only.

## Why

- `routes_db.py` exposes `GET /db/tables`, `GET /db/tables/{name}`, and destructive
  `POST /db/clear` (wipe + re-seed) with **no auth guard**, shipped to prod via the SPA
  `db` tab. Security hole.
- Raw table CRUD in the user app = no audit, no domain invariants. Read-only SQLAdmin
  removes the mutation risk entirely; audited domain actions come later.

## Design decisions (confirmed)

- **Write policy: read-only.** Every view `can_create/can_edit/can_delete/can_export
  = False`. No audit model this phase (nothing mutates). Mutations → later phase via
  `POST /admin/users/{id}/credits`, `/suspend`, etc. as audited domain endpoints.
- **Admin gate: env allowlist, `ADMIN_SUBS` authoritative.** Google `sub` is
  immutable + always present; email can change and the OAuth callback does NOT verify
  `email_verified` (`google.py`), so email is not a safe authorization id. Prod gate =
  `ADMIN_SUBS`. `ADMIN_EMAILS` allowed only as dev/ops convenience, and only if
  `email_verified` is enforced at callback; normalize both config + claim with
  `.strip().casefold()`. No DB write, works day-one on deploy. **No `is_admin` column,
  no migration, no `seed_dev_user` change.**
- **SQLAdmin session secret: dedicated `ADMIN_SESSION_SECRET`.** `JWT_SECRET` is
  optional under `AUTH_MODE=dev`, but `AuthenticationBackend(secret_key=...)` needs a
  string in every mode or it crashes on construction. Add `ADMIN_SESSION_SECRET` to
  `AuthSettings`: required when `env != dev`, fixed non-secret default in dev.
- **Login/logout design (not a task):** do NOT use SQLAdmin's form login. Override the
  backend:
  - `authenticate(request)` → shared `resolve_user`. Anonymous → redirect to
    `/api/auth/google/login`. Authenticated non-admin → `403`. Admin → allow.
  - `login()` → not used for creds; redirect to the Google entry point.
  - `/admin/logout` → delete the session (JWT) cookie, then redirect.
- **Dev mode:** dev user auto-authenticates without a cookie (`get_current_user`).
  Add the dev email to `ADMIN_EMAILS` in dev config so `/admin` works in dev too.

## Steps

### 1. Backend — remove dev DB routes
- Delete `srt-backend/pkg-job-orch/src/pkg_job_orch/routes_db.py`.
- Remove `db_router` from `pkg_job_orch/api.py` (`__all__` ~59, import ~99).
- Remove mount in `srt-backend/src/srt_backend/app.py:152,162`
  (`from pkg_job_orch.api import db_router` + `include_router(db_router, ...)`).
- Delete `srt-backend/pkg-job-orch/tests/test_db_route.py`.

### 2. Backend — admin gate (allowlist)
- Add to `AuthSettings` in `pkg_auth/config.py`: `admin_subs: frozenset[str]`
  (parse `ADMIN_SUBS` csv, authoritative), `admin_emails: frozenset[str]` (optional,
  casefold-normalized, dev/ops only), and `admin_session_secret` (`ADMIN_SESSION_SECRET`,
  required when `env != dev`, dev default). Extend `validate_runtime` to require the
  secret + at least one admin sub in staging/prod.
- **Extract a shared request→user resolver** so `require_admin` and the SQLAdmin
  auth backend share one path (fixes dev-bypass + boundary issues):
  - `get_current_user` already resolves dev-user-without-cookie then cookie→sub→user.
    Factor its body into a reusable `resolve_user(request, settings, store) -> User|None`
    in `pkg_auth/dependencies.py`.
  - `verify_session_token` stays internal — resolver lives in `pkg_auth`, so no need
    to export it across the boundary (was a violation to import into `app.py`).
- Add `require_admin` dependency: `resolve_user` → `403` unless
  `user.email in settings.admin_emails` (or sub in `admin_subs`).
- **Export** `require_admin` and the resolver through `pkg_auth.api.__all__`.

### 3. Backend — mount SQLAdmin (inside factory, before SPA catch-all)
- Add `sqladmin` dep to backend pyproject + uv lock.
- **Register inside `_create_app()` BEFORE `app.mount("/", SpaStaticFiles...)`**
  (app.py:164) — the SPA mount at `/` catches all remaining paths and would shadow
  `/admin` if mounted after.
- `from sqladmin import Admin, ModelView`; `Admin(app, engine=get_engine())`.
- `AuthenticationBackend` (SQLAdmin contract: implement `login`, `logout`,
  `authenticate`):
  - `authenticate(request)` → call shared `resolve_user`; allow only if admin.
  - `login`/`logout` → reuse existing session cookie flow (no separate admin creds);
    define behavior explicitly. Set SQLAdmin `secret_key` from settings.
- `ModelView` for `User` and `Job`: set `can_create=False`, `can_edit=False`,
  `can_delete=False`, `can_export=False` explicitly on each. Constrain BOTH views:
  `column_list` (table) AND `column_details_list` (detail) — detail defaults to every
  column and would otherwise leak Job `error`/`debug` fields. Exclude sensitive fields.

### 4. Frontend — remove db tab
- Delete `srt-frontend/src/DbScreen.tsx`.
- `App.tsx`: remove `DbScreen` import (~14), `"db"` from `Tab` (~34), from tab array
  (~335), and `{tab === "db" && ...}` render (~365).
- `api.ts`: delete `listTables`, `getTableRows`, `clearAllData`, `TableInfo`,
  `TablePage` (~91-181).

### 5. Replace "Clear all data" dev convenience
- `DbScreen` wipe + re-seed had no read-only equivalent in SQLAdmin. Move to dev-only:
  - Recommend: management script / pytest fixture calling `session_scope` +
    `seed_dev_user`. Keep `seed_dev_user`; only the HTTP route + UI button go away.

### 6. Verify — automated access matrix
- Tests (not just manual):
  - `/admin`: anonymous → redirect/401; ordinary user → 403; allowlisted admin → 200
    lists User/Job; malformed/expired cookie → rejected; dev-mode (dev email in
    allowlist) → 200.
  - **SPA does not shadow `/admin`** — integration test with a frontend build (`dist/`)
    present; dev without `dist/` would hide the ordering bug.
  - Mutation/export disabled: assert create/edit/delete/export routes 403 or absent.
  - Detail view excludes sensitive Job fields (`error`/`debug` not rendered).
  - `/admin/logout` clears the session cookie; anon `authenticate` redirects to Google.
  - Boot with `AUTH_MODE=dev` and no `JWT_SECRET` → app starts (admin secret has dev
    default), backend does not crash constructing `AuthenticationBackend`.
  - No `/api/db/*` route remains (grep + route table assert).
- Frontend builds clean (no dangling `db` refs).

## Deferred (separate plan)

- **Credit model**: balance-column vs. grant-ledger. Blocker for original grant-credit
  goal.
- **Audited domain admin actions**: `POST /admin/users/{id}/credits`, `/suspend` —
  explicit endpoints with append-only audit (actor, before/after, reason, ts). This is
  where write capability + auditability land, not SQLAdmin.

## Files touched

Delete: `routes_db.py`, `DbScreen.tsx`, `test_db_route.py`
Edit: `pkg_job_orch/api.py`, `srt_backend/app.py`, `App.tsx`, `api.ts`,
`pkg_auth/config.py`, `pkg_auth/dependencies.py`, `pkg_auth/api.py`, backend
`pyproject.toml`, dev env config (add dev email to `ADMIN_EMAILS`)
Add: SQLAdmin views + `AuthenticationBackend` (in `app.py` or new module),
access-matrix tests
No migration (no schema change — admin gate is env-derived).
