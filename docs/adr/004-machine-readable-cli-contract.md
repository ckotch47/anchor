# ADR-004: Machine-readable CLI contract

- Status: accepted
- Context: CLI будет вызываться агентами, поэтому человеческий текст недостаточен. Если output не ограничивать, агент быстро начнет тратить лишние токены на разбор и перенос полных контекстов.
- Decision: стандартный output для machine mode - JSON. Логи и ошибки идут отдельно в stderr.
- Alternatives:
  - Human-only text output
  - Mixed text + JSON
  - RPC over stdin/stdout without schema
- Trade-offs:
  - Плюсы: агенты могут надежно парсить ответы, проще автоматизировать chained workflows.
  - Минусы: нужно дисциплинированно поддерживать schema и error codes.
- Consequences:
  - stdout только structured data.
  - Нужны стабильные error codes.
  - Команды должны отдавать минимально достаточный payload, а не весь объект целиком.
  - Для интерактивного UX можно иметь отдельный presentation layer, но не в core contract.
  - MCP over stdio, including the `anchor-mcp` entrypoint, uses the same structured contract as a transport wrapper поверх core use-cases.
