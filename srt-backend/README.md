# srt-backend

FastAPI mono-app. Imports `pkg-*` libraries and mounts their routers under
`/api`. Slice 1 only wires `pkg-srt-services` and the parse route.

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

`DEV_AUTH=1` is honored by `pkg-auth` (slice 3); slice 1 has no auth at all.

## Layout

```
src/srt_backend/
  app.py        # FastAPI() instance, mounts pkg routers under /api
  routes_srt.py # POST /api/srt/parse
tests/
  test_parse_route.py
sample.srt
```
