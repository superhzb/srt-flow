# srt-cloud-worker real e2e report

- status: completed
- model: `deepseek-v4-flash`
- api_key_env: `DEEPSEEK_API_KEY`
- started_at_utc: `2026-07-08T00:36:10.448259+00:00`
- finished_at_utc: `2026-07-08T00:36:14.410959+00:00`
- base_url: `http://127.0.0.1:59958`
- source_lang: `fr`
- target_langs: `['zh', 'en', 'es']`
- segment_count: 1
- http_status: 200
- request_seconds: 3.255
- total_seconds: 3.963
- worker_log_path: `/private/var/folders/35/c3z8_p6j5kd8rldz2gf02z_c0000gn/T/pytest-of-brett/pytest-68/test_real_worker_translates_on0/uvicorn.log`

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
{"source_lang":"fr","targets":["zh","en","es"],"segments":[{"id":1,"fr":"Bonjour, comment allez-vous aujourd'hui ?","zh":"你好，今天您怎么样？","en":"Hello, how are you today?","es":"Hola, ¿cómo está usted hoy?"}]}
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
      "zh": "你好，今天您怎么样？",
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
INFO:     Started server process [23246]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:59958 (Press CTRL+C to quit)
INFO:     127.0.0.1:59961 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:59962 - "POST /translate HTTP/1.1" 200 OK

```
