# AGENTS

Rules for AI agents working inside this package:

- Public API lives in `api.py`; the package root is not a public API surface.
- Interfaces are defined as `Protocol` types (see `pkg_translator.api.LLMBackend`,
  which `Backend` in this package implements).
- Tests import only from `package.api`, never internal modules.
- Imports must have no side effects; load config/env at explicit runtime boundaries
  (`load_backends()` reads env fresh on every call — no caching — so tests can
  `monkeypatch.setenv` and see the change immediately).
- Never write to stdout or stderr.
- Logging uses `logging.getLogger(__name__)` only, with no handlers configured in library code.
- Never hard-code secrets, commit credentials, or log secret values; keep env/config behavior explicit and testable.
- Keep `ruff`, `pyright --strict`, and `pytest` passing at all times.
