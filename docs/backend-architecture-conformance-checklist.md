# Backend Architecture Conformance Checklist

- `main` only assembles wiring and invokes the CLI.
- `api` layer contains transport logic only.
- `services` layer contains use-cases and orchestration.
- `ports` define dependencies on external systems.
- `adapters` implement ports for filesystem, SQLite, vector search, and provider calls.
- CLI commands return structured output and do not expose business logic in transport.
- Config loading is centralized and lives in the Qatoria Anchor config repository.
- Health command is a thin use-case with no direct infrastructure leakage.
- Notes/tasks/history use separate domain tables with a shared retrieval spine.
- Retrieval combines lexical search, vector search, and rerank through shared services.
- MCP over stdio, when added, must call the same services as CLI.
- Tests cover config loading, migration startup, and agent-facing error contracts without external dependencies.
