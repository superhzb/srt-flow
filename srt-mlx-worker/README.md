# srt-mlx-worker

API service for translating SRT subtitles with a local MLX model.

The service accepts SRT text and returns translated SRT text where every cue has
exactly two text lines: the normalized source subtitle line followed by the
translated line.

## API

```bash
python -m pip install -e ".[mlx]"
srt-mlx-worker
```

```bash
curl -X POST http://127.0.0.1:8000/translate \
  -H 'content-type: application/json' \
  -d '{"srt":"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"}'
```

The response shape is:

```json
{"translated_srt":"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n你好\n"}
```

Use `/health` for readiness checks.

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

Public names live in `srt_mlx_worker.api`. Keep tests and
downstream imports on that boundary. Do not import public names from the package
root.

## Config And Credentials

This package may own config/env loading and credential discovery when needed for
internal use. Load config/env at explicit runtime boundaries. Do not hard-code
secrets, commit credentials, or log secret values.
