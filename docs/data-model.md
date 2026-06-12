# Data Model

## Основные сущности

- `items`
  - общая таблица для memory, notes, history, tasks.
  - поля: `id`, `type`, `title`, `body`, `status`, `source`, `created_at`, `updated_at`, `pinned`.
- `item_chunks`
  - разбиение длинных текстов на чанки для поиска и embeddings.
  - поля: `id`, `item_id`, `chunk_index`, `chunk_text`, `token_count`.
- `item_embeddings`
  - вектора для semantic search.
  - поля: `item_id`, `chunk_id`, `model`, `embedding`, `created_at`.
- `item_tags`
  - теги для фильтрации.
  - поля: `item_id`, `tag`.
- `item_links`
  - связи между задачами, заметками, памятью и историей.
  - поля: `from_item_id`, `to_item_id`, `link_type`, `created_at`.
- `events`
  - audit trail действий.
  - поля: `id`, `entity_type`, `entity_id`, `event_type`, `payload`, `created_at`.
- `settings`
  - runtime config и versioning.
- `schema_migrations`
  - журнал миграций.
  - поля: `version`, `applied_at`, `checksum`, `status`.
- `index_states`
  - lifecycle derived индексов.
  - поля: `entity_type`, `entity_id`, `index_type`, `state`, `indexed_at`, `stale_since`, `last_error`.

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
