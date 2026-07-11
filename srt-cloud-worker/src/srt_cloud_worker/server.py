"""Command-line entry point for the API server."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import create_app
from .config import load_local_env

load_local_env()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    del app
    root_logger = logging.getLogger()
    root_logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    yield


app = create_app(lifespan=lifespan)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("WORKER_PORT", "5733"))
    uvicorn.run("srt_cloud_worker.server:app", host="0.0.0.0", port=port)
