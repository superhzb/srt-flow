"""Real end-to-end coverage for the MLX worker service."""

import json
import os
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from srt_mlx_worker.config import TranslationConfig

REPORT_PATH = Path(__file__).parent / "reports" / "srt_mlx_worker_e2e_report.md"
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("SRT_MLX_E2E_TIMEOUT", "900"))
MODEL_PATH = os.environ.get("SRT_MLX_E2E_MODEL", TranslationConfig.model_path)


@pytest.mark.e2e
def test_real_worker_translates_one_source_to_three_targets_over_http(tmp_path: Path) -> None:
    started_at = time.perf_counter()
    started_at_utc = datetime.now(UTC).isoformat()
    payload = {
        "source_lang": "fr",
        "targets": ["zh", "en", "es"],
        "segments": [{"id": 1, "fr": "Bonjour, comment allez-vous aujourd'hui ?"}],
    }
    raw_input = json.dumps(payload, ensure_ascii=False, indent=2)
    result: dict[str, object] = {
        "status": "not-run",
        "model_path": MODEL_PATH,
        "started_at_utc": started_at_utc,
        "source_lang": payload["source_lang"],
        "target_langs": payload["targets"],
        "segment_count": len(payload["segments"]),
        "raw_input": raw_input,
    }

    try:
        with _running_worker(tmp_path) as (base_url, log_path):
            result["base_url"] = base_url
            result["worker_log_path"] = str(log_path)
            request_started_at = time.perf_counter()
            status_code, raw_output = _post_json(
                f"{base_url}/translate",
                payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            result["status"] = "completed"
            result["http_status"] = status_code
            result["raw_output"] = raw_output
            result["request_seconds"] = round(time.perf_counter() - request_started_at, 3)
            result["parsed_output"] = json.dumps(
                json.loads(raw_output),
                ensure_ascii=False,
                indent=2,
            )
            result["worker_log"] = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["status"] = "failed"
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)
        if "request_seconds" not in result:
            result["request_seconds"] = "n/a"
        if "worker_log_path" in result:
            result["worker_log"] = Path(str(result["worker_log_path"])).read_text(
                encoding="utf-8",
                errors="replace",
            )
        raise
    finally:
        result["total_seconds"] = round(time.perf_counter() - started_at, 3)
        result["finished_at_utc"] = datetime.now(UTC).isoformat()
        _write_report(result)

    response = json.loads(str(result["raw_output"]))
    assert result["http_status"] == 200
    assert response["source_lang"] == "fr"
    assert response["targets"] == ["zh", "en", "es"]
    assert response["segments"][0]["id"] == 1
    assert response["segments"][0]["fr"] == "Bonjour, comment allez-vous aujourd'hui ?"
    for target in response["targets"]:
        assert isinstance(response["segments"][0][target], str)
        assert response["segments"][0][target].strip()


@contextmanager
def _running_worker(tmp_path: Path) -> Generator[tuple[str, Path]]:
    port = _free_port()
    app_module = tmp_path / "real_e2e_app.py"
    log_path = tmp_path / "uvicorn.log"
    app_module.write_text(
        textwrap.dedent(
            f"""
            from srt_mlx_worker.app import create_app
            from srt_mlx_worker.config import TranslationConfig

            app = create_app(
                TranslationConfig(
                    model_path={MODEL_PATH!r},
                    batch_size=1,
                    max_tokens=256,
                    max_retries=0,
                    retry_delay=0,
                )
            )
            """
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), str(Path(__file__).parents[1] / "src"), env.get("PYTHONPATH", "")]
    )
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "real_e2e_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=tmp_path,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url, process, log_path)
        yield base_url, log_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=20)
        log_file.close()


def _wait_for_health(base_url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 30
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(f"worker exited before health check passed: {output}")
        try:
            status_code, raw_output = _get(f"{base_url}/health", timeout=2)
            if status_code == 200 and json.loads(raw_output) == {"status": "ok"}:
                return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"worker did not become healthy within 30 seconds: {last_error}")


def _get(url: str, *, timeout: float) -> tuple[int, str]:
    with urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def _post_json(url: str, payload: Mapping[str, object], *, timeout: float) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_report(result: dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw_output = result.get("raw_output", "")
    parsed_output = result.get("parsed_output", "")
    lines = [
        "# srt-mlx-worker real e2e report",
        "",
        f"- status: {result.get('status')}",
        f"- model_path: `{result.get('model_path')}`",
        f"- started_at_utc: `{result.get('started_at_utc', 'n/a')}`",
        f"- finished_at_utc: `{result.get('finished_at_utc', 'n/a')}`",
        f"- base_url: `{result.get('base_url', 'n/a')}`",
        f"- source_lang: `{result.get('source_lang', 'n/a')}`",
        f"- target_langs: `{result.get('target_langs', 'n/a')}`",
        f"- segment_count: {result.get('segment_count', 'n/a')}",
        f"- http_status: {result.get('http_status', 'n/a')}",
        f"- request_seconds: {result.get('request_seconds', 'n/a')}",
        f"- total_seconds: {result.get('total_seconds', 'n/a')}",
    ]
    if "error" in result:
        lines.extend(
            [
                f"- error_type: `{result.get('error_type')}`",
                f"- error: {result.get('error')}",
            ]
        )
    if "worker_log" in result:
        lines.extend(
            [
                f"- worker_log_path: `{result.get('worker_log_path')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Raw Input",
            "",
            "```json",
            str(result["raw_input"]),
            "```",
            "",
            "## Raw Output",
            "",
            "```json",
            str(raw_output),
            "```",
            "",
            "## Parsed Output",
            "",
            "```json",
            str(parsed_output),
            "```",
            "",
            "## Details",
            "",
            "This test sends one source language and requests three output languages.",
            "It starts a real Uvicorn worker process and calls `/translate` over HTTP.",
            "It uses the production MLX generation path; no translator stub or fake MLX "
            "module is installed.",
            "",
            "## Worker Log",
            "",
            "```text",
            str(result.get("worker_log", "")),
            "```",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
