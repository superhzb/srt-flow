# srt-flow — dev orchestration.
# `make dev` runs all services concurrently;
# Ctrl-C tears all of them down together.
#
# Ports (brebot router convention; override on the make command line for clones):
#   frontend 19105 · backend 19205 · worker 19305 · cloud-worker 19405

.PHONY: dev dev-app dev-full dev-cloud backend frontend worker cloud-worker install lint typecheck test build check

FRONTEND_PORT ?= 19105
BACKEND_PORT  ?= 19205
MLX_PORT      ?= 19305
CLOUD_PORT    ?= 19405
SRT_FLOW_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)

export SRT_FLOW_COMMIT

# One-line local stack.
dev:
	@echo "backend :$(BACKEND_PORT) · worker :$(MLX_PORT) · cloud-worker :$(CLOUD_PORT) · frontend :$(FRONTEND_PORT)  (Ctrl-C stops all)"
	@pids=""; \
	cleanup() { trap - INT TERM EXIT; for pid in $$pids; do kill "$$pid" 2>/dev/null || true; done; for pid in $$pids; do wait "$$pid" 2>/dev/null || true; done; }; \
	trap 'exit 130' INT TERM; trap cleanup EXIT; \
	$(MAKE) backend & pids="$$pids $$!"; \
	$(MAKE) worker & pids="$$pids $$!"; \
	$(MAKE) cloud-worker & pids="$$pids $$!"; \
	$(MAKE) frontend & pids="$$pids $$!"; \
	wait

# App only: backend + frontend.
dev-app:
	@echo "backend :$(BACKEND_PORT) · frontend :$(FRONTEND_PORT)  (Ctrl-C stops both)"
	@pids=""; \
	cleanup() { trap - INT TERM EXIT; for pid in $$pids; do kill "$$pid" 2>/dev/null || true; done; for pid in $$pids; do wait "$$pid" 2>/dev/null || true; done; }; \
	trap 'exit 130' INT TERM; trap cleanup EXIT; \
	$(MAKE) backend & pids="$$pids $$!"; \
	$(MAKE) frontend & pids="$$pids $$!"; \
	wait

dev-full: dev

# Cloud translation worker variant.
dev-cloud:
	@echo "backend :$(BACKEND_PORT) · cloud-worker :$(CLOUD_PORT) · frontend :$(FRONTEND_PORT)  (Ctrl-C stops all)"
	@pids=""; \
	cleanup() { trap - INT TERM EXIT; for pid in $$pids; do kill "$$pid" 2>/dev/null || true; done; for pid in $$pids; do wait "$$pid" 2>/dev/null || true; done; }; \
	trap 'exit 130' INT TERM; trap cleanup EXIT; \
	$(MAKE) backend & pids="$$pids $$!"; \
	$(MAKE) cloud-worker & pids="$$pids $$!"; \
	$(MAKE) frontend & pids="$$pids $$!"; \
	wait

backend:
	cd srt-backend && uv run uvicorn srt_backend.app:api --reload --port $(BACKEND_PORT)

frontend:
	cd srt-frontend && FRONTEND_PORT=$(FRONTEND_PORT) BACKEND_PORT=$(BACKEND_PORT) npm run dev

worker:
	cd srt-mlx-worker && WORKER_PORT=$(MLX_PORT) uv run --extra mlx uvicorn srt_mlx_worker.server:app --port $(MLX_PORT)

cloud-worker:
	cd srt-cloud-worker && WORKER_PORT=$(CLOUD_PORT) uv run uvicorn srt_cloud_worker.server:app --port $(CLOUD_PORT)

install:
	cd srt-backend && uv sync
	cd pkg-translator && uv sync
	cd srt-mlx-worker && uv sync
	cd srt-cloud-worker && uv sync
	cd srt-frontend && npm install

lint:
	uvx ruff check .
	uvx ruff format --check .
	cd srt-frontend && npm run format:check
	cd srt-frontend && npm run lint

typecheck:
	cd srt-backend && uv run pyright
	cd pkg-translator && uv run pyright
	cd srt-cloud-worker && uv run pyright
	cd srt-mlx-worker && uv run pyright
	cd srt-frontend && npm run typecheck

test:
	cd srt-backend && uv run pytest -q
	cd pkg-translator && uv run pytest -q
	cd srt-cloud-worker && uv run pytest -q -m "not e2e"
	cd srt-mlx-worker && uv run pytest -q -m "not e2e"
	cd srt-frontend && npm run test

build:
	cd srt-frontend && npm run build

check: lint typecheck test build
