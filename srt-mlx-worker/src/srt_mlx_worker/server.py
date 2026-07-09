"""Command-line entry point for the API server."""

from .api import create_app

app = create_app()


def main() -> None:
    import os

    import uvicorn

    port = int(os.environ.get("WORKER_PORT", "5732"))
    uvicorn.run("srt_mlx_worker.server:app", host="0.0.0.0", port=port)
