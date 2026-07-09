# srt-flow — dev orchestration.
# `make dev` runs all services concurrently;
# Ctrl-C tears all of them down together.
#
# Ports (uncommon block, avoids 3000/5173/8000/8080 clashes):
#   frontend 5730 · backend 5731 · worker 5732 · cloud-worker 5733

.PHONY: dev dev-app dev-full dev-cloud backend frontend worker cloud-worker install lint typecheck test build check

# One-line local stack.
dev:
	@echo "backend :5731 · worker :5732 · cloud-worker :5733 · frontend :5730  (Ctrl-C stops all)"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) worker & \
	$(MAKE) cloud-worker & \
	$(MAKE) frontend & \
	wait

# App only: backend + frontend.
dev-app:
	@echo "backend :5731 · frontend :5730  (Ctrl-C stops both)"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

dev-full: dev

# Cloud translation worker variant on :5733.
dev-cloud:
	@echo "backend :5731 · cloud-worker :5733 · frontend :5730  (Ctrl-C stops all)"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) backend & \
	$(MAKE) cloud-worker & \
	$(MAKE) frontend & \
	wait

backend:
	cd srt-backend && uv run uvicorn srt_backend.app:api --reload --port 5731

frontend:
	cd srt-frontend && npm run dev

worker:
	cd srt-mlx-worker && WORKER_PORT=5732 uv run --extra mlx uvicorn srt_mlx_worker.server:app --port 5732

cloud-worker:
	cd srt-cloud-worker && WORKER_PORT=5733 uv run uvicorn srt_cloud_worker.server:app --port 5733

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
