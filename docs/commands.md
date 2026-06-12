# CLI Contract

## Правила

- Команды должны быть неинтерактивными по умолчанию.
- Machine mode возвращает JSON в stdout.
- Ошибки и debug-логи идут в stderr.
- Выходные коды стабильны и задокументированы.

## Request format

- Base shape: `anchor <domain> <action> [flags]`.
- Core flags:
  - `--format json`
  - `--view compact|full`
  - `--fields field1,field2,field3`
  - `--limit N`
  - `--budget tokens|bytes`
  - `--profile <name>`
- Command-specific flags can narrow the request further, but they must not break the shared envelope.
- If a command does not need a knob, it should ignore it rather than failing.

## Response format

- Success envelope:
```json
{
  "ok": true,
  "command": "memory.search",
  "data": {},
  "meta": {
    "duration_ms": 38,
    "db": "sqlite",
    "view": "compact"
  }
}
```
- Error envelope:
```json
{
  "ok": false,
  "command": "memory.search",
  "error": {
    "code": "DB_LOCKED",
    "message": "database is locked",
    "retryable": true
  },
  "meta": {
    "duration_ms": 5
  }
}
```
- `data` must contain the command result only.
- `meta` is for execution details, not business state.
- Default output should be compact unless `--view full` is requested.

## Per-command config

- Global config controls:
  - default provider/base URL,
  - default view,
  - default limits and budgets,
  - retry behavior,
  - offline-only fallback.
- Command-level flags override config for a single invocation.
- The implementation should prefer explicit overrides to hidden magic.

## Config commands

- `anchor config get [--profile <name>]`
- `anchor config set --section <runtime|provider|vector|profiles> --key <field> --value <raw> [--profile <name>]`
- `config get` returns the full effective config plus the resolved config path.
- `config set` writes the updated config back to the user-folder TOML file.

## Команды MVP

- `anchor memory capture`
- `anchor memory search`
- `anchor memory recall`
- `anchor notes add`
- `anchor notes search`
- `anchor tasks add`
- `anchor tasks list`
- `anchor tasks done`
- `anchor history append`
- `anchor history search`
- `anchor db migrate`
- `anchor db reindex`
- `db migrate` creates or updates the local SQLite database at `~/.qatoria/anchor/anchor.sqlite3`.
- `anchor backup export`
- `anchor backup import`
- `anchor health`
- `anchor config get`
- `anchor config set`

## Пример JSON ответа

```json
{
  "ok": true,
  "command": "memory.search",
  "data": {
    "count": 2,
    "results": [
      {
        "id": "mem_123",
        "type": "memory",
        "title": "Embeddings strategy",
        "score": 0.91,
        "snippet": "..."
      }
    ]
  },
  "meta": {
    "duration_ms": 38,
    "db": "sqlite",
    "retrieval": ["fts", "vector", "rerank"],
    "view": "compact"
  }
}
```

## Пример ошибки

```json
{
  "ok": false,
  "command": "memory.search",
  "error": {
    "code": "DB_LOCKED",
    "message": "database is locked",
    "retryable": true
  },
  "meta": {
    "duration_ms": 5
  }
}
```
