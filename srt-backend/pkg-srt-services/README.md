# pkg-srt-services

Internal SRT services package.

## Development

```bash
python -m pip install -e .
python -m pip install build pytest ruff pyright

python -m pytest
ruff check .
pyright
python -m build
```

## Public API

Public names live in `pkg_srt_services.api`. Keep tests and
downstream imports on that boundary. Do not import public names from the package
root.

## Config And Credentials

This package may own config/env loading and credential discovery when needed for
internal use. Load config/env at explicit runtime boundaries. Do not hard-code
secrets, commit credentials, or log secret values.
