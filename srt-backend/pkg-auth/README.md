# pkg-auth

Internal authentication package.

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

Public names live in `pkg_auth.api`. Keep tests and
downstream imports on that boundary. Do not import public names from the package
root.

## Config And Credentials

This package reads configuration from the process environment. The composing
backend application owns dotenv loading; standalone consumers must inject the
environment themselves. Do not hard-code secrets, commit credentials, or log
secret values.
