# 02 — Auth & Admin

Authentication is Google OAuth 2.0 (OIDC) only, producing a stateless HS256 JWT
session held in an httponly cookie; the backend re-reads the canonical user from
the DB on every request rather than trusting the token's claims. Admin
authorization is an environment-driven allowlist (`ADMIN_SUBS` / `ADMIN_EMAILS`)
with **no `is_admin` DB column** — admin status is derived, never stored. The
only admin surface is a read-only SQLAdmin console at `/admin`, gated by the same
session and allowlist.

Auth lives in the `pkg-auth` package (`pkg_auth`); the admin console lives in
`srt-backend/src/srt_backend/admin.py`. All auth routes mount under `/api`
(`app.py:165` includes the auth router with `prefix="/api"`), so the public paths
are `/api/auth/...`. Billing/credits are out of scope (see 03/04); job internals
see 06.

## Components

| Concern | Location |
|---|---|
| OAuth login/callback routes | `pkg_auth/google.py:login`, `pkg_auth/google.py:callback` |
| App auth routes (`/me`, `/logout`, `/paid-check`) | `pkg_auth/router.py` |
| JWT mint/verify | `pkg_auth/tokens.py:mint_session_token`, `verify_session_token` |
| Google JWKS id_token verification | `pkg_auth/google.py:verify_id_token` |
| Request→user resolution & auth dependencies | `pkg_auth/dependencies.py` |
| Runtime config & validation | `pkg_auth/config.py:AuthSettings` |
| User store protocol (DB-backed at runtime) | `pkg_auth/models.py:UserStore`, `pkg_auth/state.py` |
| Public boundary | `pkg_auth/api.py` |
| Admin console | `srt-backend/src/srt_backend/admin.py` |

The `User` row is canonical in `pkg-job-orch` (`pkg_job_orch/models.py:User`:
`id`, `email`, `tier`, `google_sub`, `created_at`, plus `purchased_minutes`) and
re-exported through `pkg_auth`. The single DB-backed `AppStore` is wired into
`pkg_auth` at the composition root via `set_user_store` (`app.py:120`);
`get_user_store` raises loudly if accessed before wiring (`pkg_auth/state.py`).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/auth/google/login` | none | Set CSRF-state cookie, 302 to Google's consent screen (`pkg_auth/google.py:login`) |
| GET | `/api/auth/google/callback` | state cookie | Verify state, exchange code, verify id_token, upsert user, set session cookie, redirect (`pkg_auth/google.py:callback`) |
| GET | `/api/auth/me` | session | Return `{id, email, tier, is_admin, created_at}` (`pkg_auth/router.py:me`) |
| POST | `/api/auth/logout` | none | 204, delete session cookie (`pkg_auth/router.py:logout`) |
| GET | `/api/auth/paid-check` | session + paid tier | 200 `{ok: true}`, else 402 (`pkg_auth/router.py:paid_check`, via `require_tier("paid")`) |
| GET | `/admin`, `/admin/*` | session + admin allowlist | Read-only SQLAdmin console (`admin.py:register_admin`) |

Note the OAuth routes are namespaced under `/google` (the Google router is
included into the `/auth` router), so the live paths are
`/api/auth/google/{login,callback}`, not `/api/auth/{login,callback}`.

## OAuth login flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant API as Backend (pkg-auth)
    participant G as Google
    participant DB as UserStore (AppStore)

    B->>API: GET /api/auth/google/login
    API->>B: 302 to Google + Set-Cookie srt_oauth_state (state, 10m)
    B->>G: consent (scope: openid email profile)
    G->>B: 302 /callback?code&state
    B->>API: GET /api/auth/google/callback (code, state, state cookie)
    API->>API: constant-time compare state vs cookie (else 400)
    API->>G: POST token endpoint (code + client secret)
    G->>API: id_token (JWT)
    API->>G: GET JWKS certs
    API->>API: verify id_token (iss/aud/exp/signature); require email_verified
    API->>DB: upsert(google_sub, email, tier="free")
    DB->>API: User
    API->>API: mint HS256 session JWT (sub=google_sub)
    API->>B: 302 APP_REDIRECT_PATH + Set-Cookie srt_session (httponly, 7d)
```

Key details, all in `pkg_auth/google.py`:

- **CSRF**: `login` generates a 32-byte `secrets.token_urlsafe` state, stored in
  the `srt_oauth_state` cookie (httponly, `samesite=lax`, 10-minute max-age).
  `callback` rejects with 400 unless `secrets.compare_digest` matches.
- **Token exchange**: `exchange_code_for_tokens` POSTs to
  `https://oauth2.googleapis.com/token`; a missing `id_token` → 400.
- **id_token verification** (`verify_id_token`): fetches Google JWKS
  (`https://www.googleapis.com/oauth2/v3/certs`), imports the key set via
  `authlib.jose.JsonWebKey`, and validates `iss` (against
  `https://accounts.google.com` / `accounts.google.com`), `aud` (the configured
  client id), and `exp`. The callback additionally requires
  `email_verified is True` and string `sub`/`email` (else 400).
- **Upsert**: new users are created at `tier="free"`; the store's upsert is
  sticky-paid (never downgrades an existing paid user — see 03).

## Session / JWT handling

- The session is a stateless **HS256 JWT** minted in
  `pkg_auth/tokens.py:mint_session_token`, signed with `JWT_SECRET`. Payload:
  `sub` (= `google_sub`), `email`, `tier`, `iat`, `exp` (`iat + JWT_TTL_HOURS`,
  default 168h / 7d).
- Stored in cookie `srt_session` (name configurable): httponly,
  `samesite=lax`, `secure` in any non-dev env (`AuthSettings.cookie_secure`),
  max-age = `jwt_ttl_hours * 3600`.
- `verify_session_token` decodes and validates signature/expiry; any
  `PyJWTError` or empty `sub` → 401. **Only `sub` is trusted** — the tier claim
  is informational; the live tier is re-read from the DB per request via
  `get_by_sub`.
- Logout is client-side: `POST /api/auth/logout` just deletes the cookie; there
  is no server-side token revocation list (JWTs remain valid until expiry).

## Request→user resolution & dependencies

All in `pkg_auth/dependencies.py`:

- **`resolve_user(request, settings, store) -> User | None`** — the shared,
  non-enforcing resolver. In dev (`env=="dev"` and `auth_mode=="dev"`) it returns
  the seeded dev user (`get_dev_user`) with no cookie. Otherwise it reads the
  `srt_session` cookie, verifies it to a `google_sub`, and loads the user;
  missing/invalid cookie or unknown user → `None`.
- **`get_current_user`** — wraps `resolve_user`; raises 401 if `None`. This is
  the standard "must be logged in" dependency.
- **`require_tier(tier)`** — depends on `get_current_user`; compares tier rank
  (`free=0`, `paid=1`) and raises 402 "Upgrade required" if insufficient. Backs
  `/paid-check`.
- **`is_admin(user, settings)`** — pure predicate: `True` if the user's
  `google_sub` (stripped, casefolded) is in `settings.admin_subs`, **or** (dev
  only) their email is in `settings.admin_emails`. Email is accepted only when
  `env=="dev"`; in staging/prod the sub allowlist is authoritative.
- **`require_admin`** — resolves the user and raises 403 "Admin access required"
  unless `is_admin` is true.

The public boundary `pkg_auth/api.py` re-exports `get_current_user`,
`require_admin`, `require_tier`, `is_admin`, `resolve_user`, `router`,
`load_settings`, `set_user_store`, `get_user_store`, `User`, `UserStore`,
`AuthSettings`.

## Admin allowlist authorization

Admin is authorized purely from environment config — there is intentionally **no
`is_admin` column** on `User` and no migration. Rationale (per
`docs/plans/admin-tool-sqladmin.md`): Google `sub` is immutable and always
present, so it is the safe authorization identity; email can change, so
`ADMIN_EMAILS` is a dev/ops convenience only. Both config values and the lookup
key are normalized with `.strip().casefold()` (`config.py:_parse_admin_allowlist`,
`dependencies.py:is_admin`).

`AuthSettings.validate_runtime` (`config.py:123`) enforces at startup (called by
`load_settings`, which runs per request via the FastAPI dependency and at the
auth router's lifespan):

- staging/prod must use `AUTH_MODE=google`; `AUTH_MODE=dev` is allowed only in
  dev.
- non-dev requires `ADMIN_SESSION_SECRET` (dev gets a fixed built-in default).
- **staging/prod require a non-empty `ADMIN_SUBS`** — the app refuses to start
  otherwise, so there is never an env with no admin gate.
- `AUTH_MODE=google` requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `JWT_SECRET`.

## Read-only SQLAdmin console

`srt-backend/src/srt_backend/admin.py` mounts a [SQLAdmin](https://aminalaee.dev/sqladmin/)
app via `register_admin(app)`, called in the app factory **before** the SPA
catch-all mount at `/` (`app.py:172`) so `/admin` is not shadowed. A companion
`_noindex_admin` middleware (`app.py:175`) marks `/admin*` responses noindex.

- **`OAuthAdmin(Admin)`** — subclass that overrides SQLAdmin's built-in login
  form; `login()` delegates to the auth backend, redirecting into the app's
  Google OAuth entry point rather than showing a credential form.
- **`AdminAuthentication(AuthenticationBackend)`** — reuses the app session:
  - `authenticate(request)` calls the shared `resolve_user`; anonymous →
    302 to `/api/auth/google/login`, authenticated non-admin → 403 "Forbidden",
    admin → allow.
  - `login()` → 302 to `/api/auth/google/login` (no separate admin credentials).
  - `logout()` clears the session and deletes the `srt_session` cookie, then
    redirects to `/`.
  - Constructed with `ADMIN_SESSION_SECRET`; `register_admin` raises if it is
    missing (after calling `validate_runtime` to surface the precise config
    error).
- **Model views** are strictly read-only — every view sets
  `can_create/can_edit/can_delete/can_export/can_import = False`:
  - `UserAdmin` (model `User`): lists `id, email, tier, google_sub, created_at`.
  - `JobAdmin` (model `Job`): lists core job fields; `column_details_list` is
    explicitly constrained (adds `started_at, finished_at, error_kind, attempts`)
    so sensitive raw error/debug fields are not leaked in the detail view.
  - `EventAdmin` (model `Event`) and an `AnalyticsView` (`BaseView` at
    `/admin/analytics`) render read-only product-analytics tables via direct SQL.
- `GET /admin` (no trailing slash) is a 307 redirect to `/admin/`.

## Configuration

Env vars read by `AuthSettings` (`pkg_auth/config.py`):

| Env var | Default | Purpose |
|---|---|---|
| `ENV` | `dev` | `dev` \| `staging` \| `prod`; gates dev bypass and cookie `secure` |
| `AUTH_MODE` | `google` | `google` \| `dev`; `dev` honored only when `ENV=dev` |
| `DEV_USER_EMAIL` | `dev@local` | Seeded dev user (dev bypass) |
| `DEV_USER_TIER` | `paid` | Dev user tier (`free`\|`paid`) |
| `GOOGLE_CLIENT_ID` | — | OAuth client id (also `aud` for id_token) |
| `GOOGLE_CLIENT_SECRET` | — | OAuth client secret |
| `GOOGLE_REDIRECT_URI` | `http://localhost:5730/api/auth/google/callback` | OAuth redirect |
| `GOOGLE_CLIENT_JSON` / `GOOGLE_OAUTH_CLIENT_JSON` | — | Optional Google client JSON; fills id/secret/redirect if unset |
| `JWT_SECRET` | — | HS256 session signing key (required for `google` mode) |
| `JWT_TTL_HOURS` | `168` | Session lifetime (must be > 0) |
| `ADMIN_SUBS` | ∅ | CSV of allowlisted Google subs (authoritative; required in staging/prod) |
| `ADMIN_EMAILS` | ∅ | CSV of allowlisted emails (dev-only convenience) |
| `ADMIN_SESSION_SECRET` | dev default | SQLAdmin session secret (required non-dev) |
| `APP_REDIRECT_PATH` | `/` | Post-login redirect target |
| `SESSION_COOKIE_NAME` | `srt_session` | Session cookie name |
| `CSRF_COOKIE_NAME` | `srt_oauth_state` | OAuth state cookie name |

## Known gaps

- **No token revocation.** Logout only clears the cookie; a leaked session JWT
  stays valid until `exp`. There is no session store or blocklist.
- **`ADMIN_EMAILS` is unverified-email-based** and therefore accepted in dev
  only. In production only `ADMIN_SUBS` grants admin — an operator who knows only
  a target's email (not their Google sub) cannot be added via config in prod.
