# ADR-005: OpenAI-compatible provider integration

- Status: accepted
- Context: embeddings и rerank должны работать локально как клиентская интеграция, без hard dependency на конкретный hosted provider.
- Decision: использовать OpenAI-compatible client с настраиваемым `base_url` и модельными переменными окружения для embeddings/rerank.
- Alternatives:
  - Fixed OpenAI-only integration
  - Local-only ML stack
  - Custom HTTP client per provider
- Trade-offs:
  - Плюсы: проще подменять backend, проще тестировать, можно подключать совместимые API без изменения core.
  - Минусы: совместимость моделей и поведения нужно проверять отдельно.
- Consequences:
  - Нужны env variables для `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_RERANK_MODEL`.
  - Client должен поддерживать graceful fallback при отсутствии сети или provider errors.
  - Нужно явно логировать model/version used for each index rebuild.

