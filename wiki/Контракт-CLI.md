# Контракт CLI

## Как выглядит запрос

```text
anchor <domain> <action> [flags]
```

## Правила

- команды неинтерактивны по умолчанию
- JSON идёт в stdout
- debug и ошибки идут в stderr
- envelope должен быть стабильным
- `--view compact|full` управляет глубиной ответа
- `--project` задаёт явную область
- `--limit` управляет пагинацией
- `--projects` включает cross-project search только явно
- `--correlation-id` можно задавать для связывания действий
- `--metatags` и другие структурные поля должны быть типизированы

## Формат ответа

Успех:

```json
{
  "ok": true,
  "command": "notes.search",
  "data": {},
  "meta": {
    "duration_ms": 38,
    "view": "compact"
  }
}
```

Ошибка:

```json
{
  "ok": false,
  "command": "notes.search",
  "error": {
    "code": "INVALID_ARGS",
    "message": "query must not be empty",
    "retryable": false
  }
}
```

## Пагинация

- `notes`, `tasks`, `history` и `files` list-команды возвращают `next_cursor`
- `files list` опирается на UUIDv7 `document_id`
- cross-entity `search` использует opaque cursor на основе `score + entity_type + entity_id`
- cross-project search включается только явно через `--projects`
- list-команды не должны возвращать полный объект по умолчанию

## Поиск

- поиск по умолчанию компактный
- cross-project search не является дефолтом
- `--view full` расширяет доменный объект, если это поддержано
- поиск всегда project-scoped
- при отсутствии vector-слоя поиск должен деградировать в lexical-only
- compact view должен убирать лишние поля, а не только визуально сокращать вывод

## Перекрытие конфигом

- flags имеют приоритет над config
- config задаёт дефолты
- явный ввод важнее скрытой магии
- config хранится в пользовательской папке
