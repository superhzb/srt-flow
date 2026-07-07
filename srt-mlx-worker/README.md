# srt-mlx-worker

API service for translating subtitle segments with a local MLX model.

The service accepts already-parsed subtitle/text segments as JSON and returns
flat JSON segments keyed by language. SRT parsing, preprocessing, timestamps,
and final SRT formatting live upstream in `srt-backend`.

## API

```bash
python -m pip install -e ".[mlx]"
srt-mlx-worker
```

```bash
curl -X POST http://127.0.0.1:5732/translate \
  -H 'content-type: application/json' \
  -d '{
    "source_lang": "fr",
    "targets": ["zh", "en", "es"],
    "segments": [
      {"id": 1, "fr": "Bonjour, comment allez-vous aujourd'hui ?"}
    ]
  }'
```

The response shape is:

```json
{
  "source_lang": "fr",
  "targets": ["zh", "en", "es"],
  "segments": [
    {
      "id": 1,
      "fr": "Bonjour, comment allez-vous aujourd'hui ?",
      "zh": "你好，今天你怎么样？",
      "en": "Hello, how are you today?",
      "es": "Buenos días, ¿cómo estáis hoy?"
    }
  ]
}
```

Use `/health` for readiness checks. Use `/languages` to list the languages
configured in `languages.yaml` (as `{code, name}` entries). Any configured
language may be the source or a target; the source must differ from each target.

Each input segment must contain exactly `id` and the `source_lang` key. An
unknown source language is rejected (400). Requested targets that are not
configured languages (or equal the source) are skipped. If a supported target
fails validation for a segment after retries, that target-language key is absent
from that segment while the request still succeeds.

Multiple target languages are sent in one HTTP request. Internally, the worker
translates each supported source-target pair separately, so one request with
three targets runs three MLX generations for each input batch.

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
