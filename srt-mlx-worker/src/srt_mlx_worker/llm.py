"""MLX-backed text generation."""

import importlib
import logging
from collections.abc import Callable
from typing import Any, Protocol, cast

logger = logging.getLogger(__name__)

_model: Any | None = None
_tokenizer: "_Tokenizer | None" = None
_loaded_path: str | None = None


class _Tokenizer(Protocol):
    def apply_chat_template(
        self,
        conversation: list[dict[str, str]],
        *,
        add_generation_prompt: bool,
        tokenize: bool,
    ) -> str: ...


type _Generate = Callable[..., object]
type _Load = Callable[[str], tuple[object, object]]
type _MakeSampler = Callable[[float], object]


def ensure_model_available(model_path: str) -> None:
    _load(model_path)


def generate_text(
    prompt: str,
    model_path: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> str:
    _load(model_path)

    try:
        generate = cast(_Generate, _load_symbol("mlx_lm", "generate"))
        make_sampler = cast(
            _MakeSampler,
            _load_symbol("mlx_lm.sample_utils", "make_sampler"),
        )

        if _tokenizer is None:
            raise RuntimeError("Tokenizer was not loaded")

        messages = [{"role": "user", "content": prompt}]
        formatted = _tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
        )
        logger.debug("Sending %d chars to MLX model", len(formatted))
        response = generate(  # pyright: ignore[reportUnknownVariableType]
            _model,
            _tokenizer,
            prompt=formatted,
            max_tokens=max_tokens,
            sampler=make_sampler(temperature),
            verbose=False,
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"MLX generation failed: {exc}") from exc

    return str(response)


def _load(model_path: str) -> None:
    global _loaded_path, _model, _tokenizer

    if _loaded_path == model_path:
        return

    load = cast(_Load, _load_symbol("mlx_lm", "load"))

    logger.info("Loading MLX model: %s", model_path)
    try:
        loaded_model, loaded_tokenizer = load(model_path)
    except Exception as exc:
        raise RuntimeError(f"Unable to load MLX model {model_path!r}: {exc}") from exc
    _model = loaded_model
    _tokenizer = cast(_Tokenizer, loaded_tokenizer)
    _loaded_path = model_path


def _load_symbol(module_name: str, attribute: str) -> object:
    try:
        module = importlib.import_module(module_name)
        return getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            f"Unable to load MLX dependency {module_name}.{attribute}; "
            "install a compatible srt-mlx-worker[mlx] environment"
        ) from exc
