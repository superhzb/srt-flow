"""Command-line entry point for the API server."""

from .app import create_app

app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("srt_mlx_worker.server:app", host="0.0.0.0", port=8000)
