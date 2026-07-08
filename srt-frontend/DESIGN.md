# srt-frontend — Prototype Design

Goal: simplest UI that drives the backend request flow. Same-origin with mono-app so JWT httpOnly cookie "just works" — no CORS, no token juggling.

## Decisions

- **Stack**: Vite + React + TypeScript. Build to static `dist/`, served by FastAPI `StaticFiles` at same origin as API.
- **Why same-origin**: backend auth = JWT in httpOnly cookie. Same origin → cookie sent automatically, no CORS preflight, no localStorage token, no XSS token theft.
- **Routing**: React Router (SPA). FastAPI serves `index.html` fallback for client routes.
- **State/data**: TanStack Query (server cache + polling). No Redux — overkill for this.
- **Styling**: Tailwind. Fast, no design system needed for prototype.
- **Auth model**: no client-side token. Call `GET /auth/me` on load; 401 → show login. Login = full-page redirect to `/auth/google/login` (OAuth needs top-level nav, not fetch).

## Serving topology

```
Cloudflare Tunnel  staging.you.com→8001  app.you.com→8002
                        │
          FastAPI mono-app (uvicorn)
          ├── /api/*        → pkg-* routers
          └── /*            → StaticFiles(dist/)  + index.html fallback
```

Dev: Vite dev server :5173 with proxy `/api → :8001` (or backend port). Prod: `vite build` → FastAPI mounts `dist/`.

> **Backend ask**: prefix all pkg routers under `/api` (`/api/auth`, `/api/jobs`, `/api/billing`) so `/*` static fallback never collides with API. Add `GET /api/auth/me` returning current user + tier (frontend needs it; DESIGN only lists login/callback).

## Screens

| Route | Purpose | Calls |
|---|---|---|
| `/login` | Google button | redirect → `GET /api/auth/google/login` |
| `/` (jobs) | job list, status, upload entry | `GET /api/jobs`, poll `GET /api/jobs/{id}` |
| `/upload` | drop SRT + pick src/tgt lang + submit | `GET /api/languages`, `POST /api/jobs` |
| `/jobs/:id` | detail, live status, download | `GET /api/jobs/{id}`, `GET /api/jobs/{id}/download` |
| `/billing` | tier badge, upgrade | `POST /api/billing/checkout` |

## API contract used (from srt-backend DESIGN)

| Method | Path | Frontend use |
|---|---|---|
| GET | `/api/auth/me` *(new)* | bootstrap session; 401 → /login |
| GET | `/api/auth/google/login` | full-page redirect |
| GET | `/api/languages` | src/tgt dropdowns (proxy worker `/languages`) |
| POST | `/api/jobs` (multipart srt + src_lang + tgt_lang) | upload → `{job_id}` |
| GET | `/api/jobs` *(new, list)* | jobs table |
| GET | `/api/jobs/{id}` | status poll |
| GET | `/api/jobs/{id}/download` | download output.srt (anchor href) |
| POST | `/api/billing/checkout` | → Stripe link, redirect |

> **Backend asks (2)**: `GET /api/jobs` list endpoint + `GET /api/auth/me`. DESIGN has neither; both needed by UI.

## Job status UX

`status ∈ pending | processing | done | failed`

- Poll `GET /api/jobs/{id}` every 2s while `pending|processing` (TanStack Query `refetchInterval`).
- `done` → stop poll, enable Download.
- `failed` → show `error` field, offer re-upload.
- Email notify handled backend-side; UI doesn't wait on it.

## Upload flow

```
1. GET /api/languages → fill src/tgt selects
2. drag-drop / pick .srt (client validate: ext=.srt, size cap, non-empty)
3. POST /api/jobs multipart → 202 {job_id}   (handle 402 = quota exceeded → /billing)
4. redirect /jobs/{id} → poll → download
```

## Free-tier / quota

- `/api/auth/me` returns `tier`. Show badge.
- `POST /api/jobs` may return **402** (quota exceeded, per backend free-tier guard) → toast + link to `/billing`.

## Build order

1. Scaffold Vite+React+TS+Tailwind+Router+TanStack Query in `srt-frontend/`.
2. Auth bootstrap: `/api/auth/me` gate, `/login` with Google redirect.
3. Jobs list `/` + detail `/jobs/:id` with polling + download.
4. Upload `/upload` (languages, multipart, 402 handling).
5. Billing `/billing` (tier badge, checkout redirect).
6. `vite build` + wire FastAPI `StaticFiles` mount (coordinate w/ backend team).

## Sharp edges

- **OAuth = top-level redirect, not fetch** — `window.location = /api/auth/google/login`; can't XHR a Google redirect.
- **Cookie needs same origin** — if frontend ever split to own host, backend must set `SameSite=None; Secure` + CORS `credentials`. Same-origin avoids all of it.
- **Static fallback vs API routes** — API under `/api/*`, everything else → `index.html`, or client routes 404 on refresh.
- **Download via authed route** — use plain `<a href>` (cookie rides along); don't fetch-blob unless you need progress.
- **402 on upload** — quota guard fires before save; handle explicitly, not as generic error.
