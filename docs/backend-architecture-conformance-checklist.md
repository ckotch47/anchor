# Backend Architecture Conformance Checklist

- `main` only assembles wiring and invokes the CLI.
- `api` layer contains transport logic only.
- `services` layer contains use-cases and orchestration.
- `ports` define dependencies on external systems.
- `adapters` implement ports for filesystem, SQLite, and provider calls.
- CLI commands return structured output and do not expose business logic in transport.
- Config loading is centralized and lives in the Qatoria Anchor config repository.
- Health command is a thin use-case with no direct infrastructure leakage.
- Tests cover config loading and health contract without external dependencies.
