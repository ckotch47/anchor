# ADR-002: Single SQLite core with shared document spine

- Status: accepted
- Context: нужен локальный production-ready storage layer для памяти, заметок, истории, задач и индексов поиска. Пользователь хочет один инстанс без внешнего сервиса и без последующих rewrites схемы.
- Decision: использовать один SQLite core со shared document spine и доменными таблицами для notes/tasks/history, а derived retrieval data вынести в отдельные таблицы.
- Alternatives:
  - Separate files per feature
  - PostgreSQL backend
  - Embedded document store
- Trade-offs:
  - Плюсы: переносимость, простые backup/export/import, локальная автономность, прозрачная схема.
  - Минусы: сначала сложнее схема, нужно аккуратно проектировать блокировки, миграции и рост индексов.
- Consequences:
  - Нужны migrations и schema versioning.
  - CLI startup should auto-apply pending migrations before dispatch, while `db migrate` remains the explicit bootstrap/repair command.
  - Domain tables should stay separate from derived retrieval tables.
  - Для поиска нужны chunks, embeddings и rerank как first-class retrieval layers.
