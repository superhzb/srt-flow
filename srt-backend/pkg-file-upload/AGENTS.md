# AGENTS

Rules for AI agents working inside this package:

- Public API lives in `api.py`; the package root is not a public API surface.
- Interfaces are defined as `Protocol` types.
- Tests import only from `package.api`, never internal modules.
- Imports must have no side effects; load config/env at explicit runtime boundaries.
- Never write to stdout or stderr.
- Logging uses `logging.getLogger(__name__)` only, with no handlers configured in library code.
- Packages may own config/env loading and credential discovery when needed for internal use.
- Never hard-code secrets, commit credentials, or log secret values; keep env/config behavior explicit and testable.
- Keep `ruff`, `pyright --strict`, and `pytest` passing at all times.
