# srt-mlx-worker real e2e report

- status: completed
- model_path: `mlx-community/Qwen3-4B-Instruct-2507-4bit`
- started_at_utc: `2026-07-08T03:20:37.666441+00:00`
- finished_at_utc: `2026-07-08T03:20:48.589139+00:00`
- base_url: `http://127.0.0.1:50151`
- source_lang: `fr`
- target_langs: `['zh', 'en', 'es']`
- segment_count: 1
- http_status: 200
- request_seconds: 10.157
- total_seconds: 10.923
- worker_log_path: `/private/var/folders/35/c3z8_p6j5kd8rldz2gf02z_c0000gn/T/pytest-of-brett/pytest-79/test_real_worker_translates_on0/uvicorn.log`

## Raw Input

```json
{
  "source_lang": "fr",
  "targets": [
    "zh",
    "en",
    "es"
  ],
  "segments": [
    {
      "id": 1,
      "fr": "Bonjour, comment allez-vous aujourd'hui ?"
    }
  ]
}
```

## Raw Output

```json
{"source_lang":"fr","targets":["zh","en","es"],"segments":[{"id":1,"fr":"Bonjour, comment allez-vous aujourd'hui ?","zh":"你好，今天你怎么样？","en":"Hello, how are you today?","es":"Buenos días, ¿cómo estáis hoy?"}]}
```

## Parsed Output

```json
{
  "source_lang": "fr",
  "targets": [
    "zh",
    "en",
    "es"
  ],
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

## Details

This test sends one source language and requests three output languages.
It starts a real Uvicorn worker process and calls `/translate` over HTTP.
It uses the production MLX generation path; no translator stub or fake MLX module is installed.

## Worker Log

```text
INFO:     Started server process [41950]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:50151 (Press CTRL+C to quit)
INFO:     127.0.0.1:50154 - "GET /health HTTP/1.1" 200 OK

Fetching 11 files:   0%|          | 0/11 [00:00<?, ?it/s]
Fetching 11 files: 100%|██████████| 11/11 [00:00<00:00, 24725.26it/s]
INFO:     127.0.0.1:50155 - "POST /translate HTTP/1.1" 200 OK

```
