# srt-flow — dev orchestration.
# `make dev` runs backend + frontend concurrently; Ctrl-C tears both down.
#
# Ports (brebot router convention; override on the make command line for clones):
#   frontend 19105 · backend 19205
#
# Choosing the local mlx backend vs. cloud (DeepSeek) is an LLM_BACKENDS
# config decision (see srt-backend/.env), not a process to start — the mlx
# row talks to the mlx-platform gateway running separately on the Mac.

.PHONY: dev serve backend backend-serve frontend install hooks lint typecheck test build check

FRONTEND_PORT ?= 19105
BACKEND_PORT  ?= 19205
ENV           ?= dev
SRT_FLOW_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)

export SRT_FLOW_COMMIT ENV

# One-line local stack.
dev:
	@echo "backend :$(BACKEND_PORT) · frontend :$(FRONTEND_PORT)  (Ctrl-C stops both)"
	@pids=""; \
	cleanup() { trap - INT TERM EXIT; for pid in $$pids; do kill "$$pid" 2>/dev/null || true; done; for pid in $$pids; do wait "$$pid" 2>/dev/null || true; done; }; \
	trap 'exit 130' INT TERM; trap cleanup EXIT; \
	$(MAKE) backend & pids="$$pids $$!"; \
	$(MAKE) frontend & pids="$$pids $$!"; \
	wait

# Deployment stack: FastAPI serves the prebuilt frontend on BACKEND_PORT.
serve:
	@echo "app :$(BACKEND_PORT)  (Ctrl-C stops)"
	$(MAKE) backend-serve

backend:
	cd srt-backend && uv run uvicorn srt_backend.app:api --reload --port $(BACKEND_PORT)

backend-serve:
	cd srt-backend && uv run uvicorn srt_backend.app:api --host 127.0.0.1 --port $(BACKEND_PORT)

frontend:
	cd srt-frontend && FRONTEND_PORT=$(FRONTEND_PORT) BACKEND_PORT=$(BACKEND_PORT) npm run dev

install:
	cd srt-backend && uv sync
	cd srt-frontend && npm install

# Use the repository-managed Git hooks in this checkout.
hooks:
	git config core.hooksPath .githooks

lint:
	uvx ruff check .
	uvx ruff format --check .
	cd srt-frontend && npm run format:check
	cd srt-frontend && npm run lint

typecheck:
	cd srt-backend && uv run pyright
	cd srt-frontend && npm run typecheck

test:
	cd srt-backend && uv run pytest -q
	cd srt-frontend && npm run test

build:
	cd srt-frontend && npm run build

check: lint typecheck test build
