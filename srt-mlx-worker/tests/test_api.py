from collections.abc import Sequence

from srt_mlx_worker import api

public_names = api.__all__

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:02,000
Bonjour

2
00:00:02,500 --> 00:00:03,500
Au revoir
"""


def test_public_api_all_names_are_resolvable() -> None:
    for name in public_names:
        assert hasattr(api, name), f"{name} in __all__ but not defined in api"


def test_translate_srt_text_outputs_two_text_lines_per_segment() -> None:
    def fake_translator(prompt: str, config: api.TranslationConfig) -> str:
        assert config.batch_size == 10
        assert "Bonjour" in prompt
        return '[{"id": 1, "zh": "你好"}, {"id": 2, "zh": "再见"}]'

    translated = api.translate_srt_text(SAMPLE_SRT, translator=fake_translator)

    assert translated == (
        "1\n"
        "00:00:01,000 --> 00:00:02,000\n"
        "Bonjour\n"
        "你好\n"
        "\n"
        "2\n"
        "00:00:02,500 --> 00:00:03,500\n"
        "Au revoir\n"
        "再见\n"
    )


def test_create_app_exposes_health_endpoint() -> None:
    app = api.create_app()

    assert app.title == "SRT MLX Worker"
    assert _route_paths(app.routes) >= {"/health", "/translate"}


def _route_paths(routes: Sequence[object]) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths
