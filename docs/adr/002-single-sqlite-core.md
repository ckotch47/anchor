# ADR-002: Single SQLite source of truth

- Status: accepted
- Context: нужно локальное хранилище для памяти, заметок, истории, задач и индексов поиска. Пользователь хочет один инстанс без внешнего сервиса.
- Decision: использовать один SQLite core как source of truth для всех сущностей.
- Alternatives:
  - Separate files per feature
  - PostgreSQL backend
  - Embedded document store
- Trade-offs:
  - Плюсы: переносимость, простые backup/export/import, локальная автономность, прозрачная схема.
  - Минусы: нужно аккуратно проектировать блокировки, миграции и рост индексов.
- Consequences:
  - Нужны migrations и schema versioning.
  - CLI startup should auto-apply pending migrations before dispatch, while `db migrate` remains the explicit bootstrap/repair command.
  - Для длинных текстов потребуются chunks.
  - Для поиска лучше заранее разделить raw content и search indexes.
