# srt-flow

Monorepo for the SRT translation app: a FastAPI backend (with the translation
core and LLM backend as workspace members) and a React frontend.

## Requirements

- Python 3.12 (`.python-version`)
- uv
- Node from `srt-frontend/.nvmrc`
- npm

## Install

```bash
make install
```

This syncs the `srt-backend` uv workspace (backend app + all `pkg-*` members,
including `pkg-translator` and `pkg-llm-backend`) and installs frontend
dependencies.

## Run

```bash
make dev
```

Ports:

- Frontend: http://localhost:19105
- Backend: http://localhost:19205

Other entrypoints: `make backend`, `make frontend` run one service each.
`make dev` runs the Vite dev server and is for local development only — it does
**not** prerender routes or emit `sitemap.xml`, so it must never back the public
site.

## Serve the production site

The public site is served by FastAPI from the prebuilt, prerendered frontend —
not the Vite dev server. Prerendering bakes per-route `<title>`, meta
description, canonical, and Open Graph tags into static HTML and emits
`sitemap.xml`, which crawlers require.

```bash
make build     # vite build + prerender routes + write dist/sitemap.xml
make serve     # FastAPI serves srt-frontend/dist on :19205
```

Point the Cloudflare tunnel at the backend port (`19205`), not the frontend dev
port. Rerun `make build` after any change that affects markup or SEO metadata.

SEO metadata has one source of truth: `srt-frontend/src/seo.ts` (`SITE_URL`
drives canonical, `sitemap.xml`, and og:url). The canonical host is
`https://app.srt-flow.com`; the apex and `www` hosts 301-redirect to it.

Verify a running deploy:

```bash
curl -s https://app.srt-flow.com/sitemap.xml | grep -o 'https://[a-z.]*srt-flow[^<]*' | head -1
curl -s https://app.srt-flow.com/robots.txt
curl -s https://app.srt-flow.com/translate/english-to-spanish/ | grep -o '<title>[^<]*'
```

All three must show the `app.srt-flow.com` host and the real page title.

## Validate

```bash
make check
```

`make check` mirrors CI: Python Ruff lint + format check, Python pyright,
package tests, frontend Prettier/ESLint/typecheck/tests, and frontend build.
Use `make lint`, `make typecheck`, `make test`, or `make build` for narrower
local loops.

Install the repository-managed Git hooks once per checkout:

```bash
make hooks
```

The pre-push hook runs `make check` before updating a remote branch. GitHub CI
independently runs the same validation and remains the authoritative check.

## Branch workflow

- Push development commits directly to `staging`; successful CI deploys the
  tested commit to the staging environment.
- Promote `staging` to `main` with a pull request. The protected `main` branch
  requires CI to pass before merge.
- Successful CI on `main` deploys the tested commit to production.

## Environment

Copy `srt-backend/.env.example` to `srt-backend/.env`. Local dev can use
`AUTH_MODE=dev`; Google auth and billing settings are only required when
exercising those flows.

Translation runs in-process against an `LLM_BACKENDS` registry — choosing
cloud (DeepSeek) vs. local (mlx-platform gateway) is a config decision, not a
separate service. Cloud deploy sets `LLM_BACKENDS=cloud`; local dev/test
additionally enables `mlx` (see `srt-backend/.env.example`).

Key variables:

- `ENV`: `dev`, `staging`, or `prod`.
- `AUTH_MODE`: `dev` or `google`.
- `LLM_BACKENDS`: enabled translation backend ids, default `mlx,cloud`.
- `DATABASE_URL`: backend SQLite URL, default `sqlite:///./.data/dev/db.sqlite`.
- `DEEPSEEK_API_KEY`: required when the `cloud` backend is enabled.
- `MLX_PLATFORM_BASE_URL`: mlx-platform gateway URL, required when the `mlx` backend is enabled.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `JWT_SECRET`: required for Google auth.
- `BILLING_REF_SECRET`: required when billing routes are configured.

## Layout

- `srt-backend/`: FastAPI app and backend library packages under `pkg-*`,
  including `pkg-translator` (translation batching/validation core) and
  `pkg-llm-backend` (the in-process OpenAI-client LLM backend registry).
- `srt-frontend/`: Vite + React + TypeScript SPA.
- `PLAN.md`: delivery plan and feature slices.
