# ADR-003: Hybrid retrieval and rerank

- Status: accepted
- Context: поиск должен работать не только по точным словам, но и по смыслу. Для этого одного FTS недостаточно.
- Decision: использовать гибридный retrieval pipeline: FTS для lexical search, embeddings для semantic search, rerank для top-k кандидатов.
- Alternatives:
  - Только FTS
  - Только vector search
  - External search engine
- Trade-offs:
  - Плюсы: лучшее качество поиска на коротких и длинных запросах, лучше покрытие разных формулировок.
  - Минусы: дороже по latency и интеграции, нужен provider для embeddings и rerank.
- Consequences:
  - Retrieval должен быть двухэтапным.
  - Нужны score fusion и top-k cutoff.
  - Rerank должен быть optional fallback, если provider недоступен.

