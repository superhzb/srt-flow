# srt-cloud-worker real e2e report

- status: completed
- model: `deepseek-v4-flash`
- api_key_env: `DEEPSEEK_API_KEY`
- started_at_utc: `2026-07-08T03:20:27.418690+00:00`
- finished_at_utc: `2026-07-08T03:20:31.344662+00:00`
- base_url: `http://127.0.0.1:50134`
- source_lang: `fr`
- target_langs: `['zh', 'en', 'es']`
- segment_count: 1
- http_status: 200
- request_seconds: 3.165
- total_seconds: 3.926
- worker_log_path: `/private/var/folders/35/c3z8_p6j5kd8rldz2gf02z_c0000gn/T/pytest-of-brett/pytest-78/test_real_worker_translates_on0/uvicorn.log`

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
{"source_lang":"fr","targets":["zh","en","es"],"segments":[{"id":1,"fr":"Bonjour, comment allez-vous aujourd'hui ?","zh":"您好，今天您怎么样？","en":"Hello, how are you today?","es":"Hola, ¿cómo está usted hoy?"}]}
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
      "zh": "您好，今天您怎么样？",
      "en": "Hello, how are you today?",
      "es": "Hola, ¿cómo está usted hoy?"
    }
  ]
}
```

## Details

This test sends one source language and requests three output languages.
It starts a real Uvicorn worker process and calls `/translate` over HTTP.
It uses the production cloud generation path; no translator stub or fake cloud module is installed.

## Worker Log

```text
INFO:     Started server process [41551]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:50134 (Press CTRL+C to quit)
INFO:     127.0.0.1:50137 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:50138 - "POST /translate HTTP/1.1" 200 OK

```
