"""Direct tests for ``orchestration.default_worker_client`` (Phase B).

Replaces ``test_worker_client.py`` (the deleted HTTP NDJSON client's direct
tests). ``translate_segments`` is monkeypatched so these drive the real
progress-folding + error-wrapping logic in ``default_worker_client`` without
touching ``pkg_translator``'s batching internals or any network endpoint.

The progress-denominator-folds-across-targets case mirrors the old NDJSON
test input/expected-fraction-sequence exactly, so it doubles as the
"folded-progress values match the pre-merge aggregation" check from the
migration plan.
"""

from __future__ import annotations

from typing import Any

import pkg_job_orch.orchestration as orchestration
import pytest
from pkg_job_orch.orchestration import StreamOutcome, WorkerStreamError, default_worker_client
from pkg_translator.api import BatchProgress, NoBackendError, UnsupportedLanguageError


def _fake_translate_segments(
    progress_events: list[BatchProgress],
    result: tuple[list[str], list[dict[str, Any]]],
) -> Any:
    def fake(
        source_lang: str,
        targets: list[str],
        segments: list[dict[str, Any]],
        config: Any,
        translator: Any,
        on_progress: Any,
        backend: Any,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        del source_lang, targets, segments, config, translator, backend
        if on_progress is not None:
            for event in progress_events:
                on_progress(event)
        return result

    return fake


async def test_progress_denominator_folds_across_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Progress fraction uses Σ batch_total across targets, learned as seen.

    Same shape as the pre-merge NDJSON aggregation test: target 0 batch_total=2,
    target 1 batch_total=3 → denominator 5 once both are seen.
    """
    monkeypatch.setenv("LLM_BACKENDS", "mlx")
    events = [
        BatchProgress(target="es", target_index=0, target_total=2, batch_index=0, batch_total=2),
        BatchProgress(target="es", target_index=0, target_total=2, batch_index=1, batch_total=2),
        BatchProgress(target="fr", target_index=1, target_total=2, batch_index=0, batch_total=3),
        BatchProgress(target="fr", target_index=1, target_total=2, batch_index=1, batch_total=3),
        BatchProgress(target="fr", target_index=1, target_total=2, batch_index=2, batch_total=3),
    ]
    result = (["es", "fr"], [{"id": 0, "es": "hola", "fr": "bonjour"}])
    monkeypatch.setattr(
        orchestration, "translate_segments", _fake_translate_segments(events, result)
    )

    fractions: list[float] = []
    outcome = await default_worker_client(
        "mlx", "en", ["es", "fr"], [{"id": 0, "en": "hello"}], fractions.append
    )

    assert isinstance(outcome, StreamOutcome)
    assert outcome.targets == ["es", "fr"]
    assert outcome.segments == [{"id": 0, "es": "hola", "fr": "bonjour"}]
    final_progress: Any = fractions[-1]
    assert final_progress.by_target == {
        "es": {"done": 2, "total": 2},
        "fr": {"done": 3, "total": 3},
    }
    # 5 progress folds + the terminal 1.0 emitted after translate_segments returns.
    assert fractions == [0.5, 1.0, 0.6, 0.8, 1.0, 1.0]


async def test_unknown_worker_id_raises_worker_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    with pytest.raises(WorkerStreamError, match="unknown worker id"):
        await default_worker_client("ghost", "en", ["fr"], [{"id": 0, "en": "hi"}], None)


async def test_backend_failure_raises_worker_stream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    def fake(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("mlx-platform generation failed: boom")

    monkeypatch.setattr(orchestration, "translate_segments", fake)

    with pytest.raises(WorkerStreamError, match="boom"):
        await default_worker_client("mlx", "en", ["fr"], [{"id": 0, "en": "hi"}], None)


@pytest.mark.parametrize(
    ("exc", "expected_kind"),
    [
        (UnsupportedLanguageError("Unsupported source language: xx"), "unsupported_language"),
        (NoBackendError("No LLM backend configured"), "worker_config"),
        (TimeoutError("read timed out"), "backend_unavailable"),
        (ConnectionError("connection reset"), "backend_unavailable"),
        (RuntimeError("upstream 503 unavailable"), "backend_unavailable"),
        (RuntimeError("rate limit exceeded"), "backend_unavailable"),
        (RuntimeError("mlx-platform generation failed: boom"), "worker_stream"),
    ],
)
async def test_backend_failure_classified_into_kind(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected_kind: str
) -> None:
    """Each raised backend exception maps to its expected error_kind."""
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    def fake(*_args: Any, **_kwargs: Any) -> Any:
        raise exc

    monkeypatch.setattr(orchestration, "translate_segments", fake)

    with pytest.raises(WorkerStreamError) as excinfo:
        await default_worker_client("mlx", "en", ["fr"], [{"id": 0, "en": "hi"}], None)
    assert excinfo.value.kind == expected_kind
    # error_detail carries the exception class + repr, not a flattened str.
    assert excinfo.value.detail is not None
    assert type(exc).__name__ in excinfo.value.detail


async def test_unknown_worker_id_classified_worker_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    with pytest.raises(WorkerStreamError) as excinfo:
        await default_worker_client("ghost", "en", ["fr"], [{"id": 0, "en": "hi"}], None)
    assert excinfo.value.kind == "worker_config"


async def test_failed_target_threaded_from_last_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """failed_target reflects the target in flight when the backend raised."""
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    def fake(
        source_lang: str,
        targets: list[str],
        segments: list[dict[str, Any]],
        config: Any,
        translator: Any,
        on_progress: Any,
        backend: Any,
    ) -> Any:
        del source_lang, targets, segments, config, translator, backend
        on_progress(
            BatchProgress(target="fr", target_index=0, target_total=1, batch_index=0, batch_total=2)
        )
        raise RuntimeError("boom mid-target")

    monkeypatch.setattr(orchestration, "translate_segments", fake)

    with pytest.raises(WorkerStreamError) as excinfo:
        await default_worker_client("mlx", "en", ["fr"], [{"id": 0, "en": "hi"}], lambda _f: None)
    assert excinfo.value.failed_target == "fr"


async def test_no_progress_events_yields_zero_then_terminal_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No batches observed (e.g. empty input) still terminates at 1.0."""
    monkeypatch.setenv("LLM_BACKENDS", "mlx")
    result: tuple[list[str], list[dict[str, Any]]] = (["fr"], [])
    monkeypatch.setattr(orchestration, "translate_segments", _fake_translate_segments([], result))

    fractions: list[float] = []
    outcome = await default_worker_client("mlx", "en", ["fr"], [], fractions.append)

    assert outcome.segments == []
    assert fractions == [1.0]
