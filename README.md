# srt-flow

Monorepo for the SRT translation app: a FastAPI backend, React frontend, cloud
translation worker, local MLX worker, and shared worker core.

## Requirements

- Python 3.12 (`.python-version`)
- uv
- Node from `srt-frontend/.nvmrc`
- npm

## Install

```bash
make install
```

This syncs each separately deployable Python package and installs frontend
dependencies. The repo is intentionally not a root uv workspace: the backend,
cloud worker, and MLX worker must stay independently installable so deploy
images do not pull platform-specific dependencies they do not need.

## Run

```bash
make dev
```

Ports:

- Frontend: http://localhost:5730
- Backend: http://localhost:5731
- MLX worker: http://localhost:5732
- Cloud worker: http://localhost:5733

Other entrypoints:

- `make dev-app` runs backend + frontend.
- `make dev-cloud` runs backend + cloud worker + frontend.
- `make backend`, `make frontend`, `make worker`, and `make cloud-worker` run one service.

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

Copy `.env.example` to the package or shell environment you are running. Local
dev can use `AUTH_MODE=dev`; Google auth and billing settings are only required
when exercising those flows. The cloud worker requires `DEEPSEEK_API_KEY`.

Key variables:

- `ENV`: `dev`, `staging`, or `prod`.
- `AUTH_MODE`: `dev` or `google`.
- `WORKERS`: backend worker registry, default `mlx=http://localhost:5732,cloud=http://localhost:5733`.
- `DATABASE_URL`: backend SQLite URL, default `sqlite:///./.data/dev/db.sqlite`.
- `DEEPSEEK_API_KEY`: required by `srt-cloud-worker`.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `JWT_SECRET`: required for Google auth.
- `BILLING_REF_SECRET`: required when billing routes are configured.

## Layout

- `srt-backend/`: FastAPI app and backend library packages under `pkg-*`.
- `srt-frontend/`: Vite + React + TypeScript SPA.
- `pkg-translator/`: shared translation worker contracts and batching logic.
- `srt-cloud-worker/`: DeepSeek-backed translation worker.
- `srt-mlx-worker/`: local Apple-silicon MLX translation worker.
- `PLAN.md`: delivery plan and feature slices.
