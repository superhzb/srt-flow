# pkg-auth — Implementation Plan

Google OAuth only. Plus one developer shortcut: **dev auth** (seeded user, skip
the OAuth roundtrip). `DEV_USER_TIER=paid` covers the "no auth" demo case, so a
separate anonymous mode is not needed.

Scope: this package. It owns login/callback, session (JWT cookie), and the
`get_current_user` / `require_tier` dependencies the rest of the app leans on.
See `../DESIGN.md` for the system-wide picture.

## Auth modes

One env var picks the mode: `AUTH_MODE = google | dev`.

| Mode | Who resolves | Use |
|---|---|---|
| `google` | real Google OAuth → JWT cookie | staging / prod |
| `dev` | seeded dev user, no OAuth needed | local iteration + demos (set `DEV_USER_TIER=paid` to exercise paid features) |

`get_current_user()` branches on the mode:

- **google** — read JWT from httpOnly cookie, verify, load user by `google_sub`.
  No/*bad* cookie → `401`.
- **dev** — return the seeded dev user directly. `/api/auth/me` never `401`,
  so the SPA skips `/login`. Real `/api/auth/google/*` routes still registered
  so OAuth can be tested, but the requirement is lifted.

### Hard security gate (do NOT skip)

- `dev` is **ignored unless `ENV=="dev"`**.
- App **refuses to start** if `ENV in {staging, prod}` and `AUTH_MODE != google`.
  Fail loud at startup — never silently ship an open door.
- When `ENV != dev`, no dev user is seeded and no bypass path is registered.

## Config

```
ENV=dev                          # dev | staging | prod
AUTH_MODE=google                 # google | dev  (dev honored only when ENV=dev)
DEV_USER_EMAIL=dev@local         # seeded user for dev mode
DEV_USER_TIER=paid               # test paid features without Stripe
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:5731/api/auth/google/callback
JWT_SECRET=...                   # required when AUTH_MODE=google
JWT_TTL_HOURS=168                # 7d session
```

Loaded once at a runtime boundary (`config.py`, `pydantic-settings`), not at
import time — per AGENTS.md (no import side effects).

## Public API (`pkg_auth.api`)

Exactly what `DESIGN.md` promises, nothing more:

```python
__all__ = ["router", "get_current_user", "require_tier", "User"]

router: APIRouter                       # login / callback / me
async def get_current_user(...) -> User # FastAPI dependency; 401 in google mode
def require_tier(tier: str) -> Depends   # dependency factory; 402 if under tier
class User: id, google_sub, email, tier  # returned to callers
```

Downstream pkgs import only from `pkg_auth.api`. `require_tier` is used by
pkg-billing / pkg-job-orch for the free-tier guard.

## Routes (mounted under `/api` by the app)

| Route | Behavior |
|---|---|
| `GET /api/auth/me` | current user `{email, tier}` or `401`. Bootstraps SPA session. |
| `GET /api/auth/google/login` | 302 → Google consent (state param, CSRF cookie). |
| `GET /api/auth/google/callback` | exchange code → verify id_token → upsert user → mint JWT cookie → 302 to app. |
| `POST /api/auth/logout` | clear cookie. |

In `dev` mode `/me` returns the seeded user; google routes stay live but optional.

## Session token

- JWT, `sub=google_sub`, `email`, `tier`, `exp`. Signed with `JWT_SECRET` (HS256).
  `tier` is informational only; the DB/store-loaded user is authoritative.
- Delivered as **httpOnly, Secure when `ENV != dev`, SameSite=Lax cookie** — SPA holds no
  token, same-origin so no CORS.
- No server session store.

## Data / DB dependency

`DESIGN.md` gives pkg-auth a `db` dependency, but no db layer exists yet.
Decide before coding:

- **Option A (recommended):** pkg-auth defines a thin `UserStore` Protocol
  (`get_by_sub`, `upsert`, `get_dev_user`) and the app injects a SQLite-backed
  impl. Keeps pkg-auth free of a hard DB import; matches the Protocol convention
  in AGENTS.md.
- **Option B:** pkg-auth imports a shared `srt_backend.db` directly. Simpler,
  couples auth to the app's db module.

`user` table (from DESIGN): `id, google_sub UNIQUE, email, tier[free|paid], created_at`.
Dev mode upserts `DEV_USER_EMAIL` on startup (or lazily on first request).

## Deps to add (pyproject)

```
fastapi, python-jose[cryptography] (or pyjwt), authlib, httpx, pydantic-settings
```

- **authlib** — OAuth flow (login redirect, code exchange, id_token verify).
- **httpx** — declared explicitly, not left implicit. Authlib's async OAuth
  client is httpx-based, and tests mock the Google token exchange at the httpx
  layer (`respx`/`httpx.MockTransport`). Direct dep keeps the version pinned
  and the test seam honest.

## Build steps

1. `config.py` — load env, validate the hard gate (raise on prod+bypass). Unit-test the gate.
2. `models.py` — `User`, `UserStore` Protocol (Option A).
3. `tokens.py` — mint / verify JWT cookie. Test round-trip + expiry.
4. `dependencies.py` — `get_current_user` (3-way branch), `require_tier`.
5. `google.py` — OAuth login/callback (authlib), id_token verify, user upsert.
6. `router.py` — wire routes.
7. `api.py` — re-export the public names.
8. App mounts `router` under `/api`; provides the `UserStore` impl.

## Tests

- Gate: `ENV=prod` + `AUTH_MODE=dev` → startup raises. `ENV=dev` + `dev` → allowed.
- `get_current_user`: google no-cookie → 401; dev → seeded user.
- JWT round-trip + expired token → 401.
- Callback: mocked Google token exchange (httpx) → user upserted, cookie set.
- Callback CSRF: missing/mismatched OAuth state → 400.
- `/api/auth/me`: 401 in google mode w/o cookie; user in dev mode.
- Keep `ruff`, `pyright --strict`, `pytest` green (AGENTS.md).

## Open questions

- DB wiring: Option A vs B above — pick before step 2.
- Google id_token verification: authlib built-in vs google-auth lib.
