# srt-backend

FastAPI mono-app. Imports `pkg-*` libraries and mounts their routers under
`/api`. Current app routes cover SRT parsing/preparation, worker discovery,
translation jobs, auth, billing, and artifact download.

## Dev

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"   # note: dev deps listed as dependency-group, see below
uv sync                       # preferred, resolves workspace pkgs
uv run pytest
uv run ruff check .
uv run pyright
uv run uvicorn srt_backend.app:api --reload --port 5731
```

`AUTH_MODE=dev` is honored by `pkg-auth` when `ENV=dev`.

## Layout

```
src/srt_backend/
  app.py             # FastAPI() instance, lifespan, package router mounts
  app_store.py       # DB-backed composition store
  routes_srt.py      # POST /api/srt/parse and /api/srt/prepare
  routes_workers.py  # worker and language discovery
tests/
  test_parse_route.py
  test_prepare_route.py
  test_workers_route.py
sample.srt
```

Backend package libraries live under `pkg-*`; package-specific agent rules are
in each package's `AGENTS.md` where present.
