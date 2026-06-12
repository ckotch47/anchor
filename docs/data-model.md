# Data Model

## MVP schema

Один SQLite-файл, одна доменная таблица `items`, несколько derived-таблиц вокруг неё.

- `items`
  - source of truth для `memory`, `notes`, `history`, `tasks`
  - поля: `id`, `type`, `title`, `body`, `status`, `source`, `created_at`, `updated_at`, `pinned`
- `item_chunks`
  - нормализованные чанки длинного текста для FTS и embedding pipeline
  - поля: `id`, `item_id`, `chunk_index`, `chunk_text`, `token_count`
- `item_embeddings`
  - вектора для semantic search по чанкам
  - поля: `item_id`, `chunk_id`, `model`, `embedding`, `created_at`
- `item_tags`
  - теги для фильтрации и coarse retrieval
  - поля: `item_id`, `tag`
- `item_links`
  - связи между сущностями, чтобы retrieval мог собирать related context
  - поля: `from_item_id`, `to_item_id`, `link_type`, `created_at`
- `events`
  - audit trail и история изменений
  - поля: `id`, `entity_type`, `entity_id`, `event_type`, `payload`, `created_at`
- `settings`
  - runtime settings и служебные ключи
- `schema_migrations`
  - версия схемы и история применённых миграций
  - поля: `version`, `name`, `checksum`, `applied_at`, `status`
- `index_states`
  - lifecycle derived индексов
  - поля: `entity_type`, `entity_id`, `index_type`, `state`, `indexed_at`, `stale_since`, `last_error`

## Retrieval contract

- `items.body` is the canonical text, not the search index.
- `item_chunks.chunk_text` is the unit for chunk-level FTS and embedding generation.
- `item_embeddings.embedding` is derived and can be rebuilt from `items` + `item_chunks`.
- `item_links` are used to pull neighboring context for agent requests.
- `events` are append-only and never replace source of truth rows.
- If derived data is stale, the source row is still valid and retrievable.
- Missing embeddings must degrade to text/FTS retrieval, not fail the command.

## Индексы

- FTS индекс по `title` и `body` или по chunk-таблице.
- Индекс по `type`, `status`, `created_at`.
- Индекс по `item_links.from_item_id` и `item_links.to_item_id`.
- Индекс по `schema_migrations.version`.
- Индекс по `index_states.state` и `index_states.index_type`.

## Нормы хранения

- Raw text хранить отдельно от derived search data.
- Embeddings не считать source of truth.
- Search index можно пересобирать из `items` и `item_chunks`.
- Source-of-truth записи должны сохраняться независимо от состояния derived индексов.
- Derived индексы могут переходить в `pending`, `stale`, `ready`, `error`.
