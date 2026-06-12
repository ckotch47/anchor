# Anchor

Qatoria Anchor is a local CLI tool for agents.

Локальный CLI-инструмент для персональных агентов без веб-API и без обязательного MCP-слоя.

## Главная задача

Сделать стабильный машинный контракт для агентов, который:

- легко вызывается из automation,
- возвращает structured output,
- снижает token burn за счёт компактных локальных retrieval-ответов,
- не требует отдельного сервера для базового сценария.

## Цель

Дать агентам и человеку единый локальный интерфейс для:

- памяти,
- заметок,
- истории,
- задач,
- семантического поиска,
- rerank поверх локального хранилища.

## Принятый подход

- Один локальный инстанс на пользователя.
- Один SQLite-контур как source of truth.
- При старте CLI автоматически применяет pending migrations, чтобы агент не управлял bootstrap вручную.
- CLI как машинный протокол для агентов.
- OpenAI-compatible модели только как внешний provider для embeddings и rerank.

## Документы

- [Naming](./docs/naming.md)
- [Assessment](./docs/assessment.md)
- [ADR index](./docs/adr/README.md)
- [Stack](./docs/stack.md)
- [Implementation plan](./docs/implementation-plan.md)
- [Data model](./docs/data-model.md)
- [Backend architecture checklist](./docs/backend-architecture-conformance-checklist.md)
- [Config](./docs/config.md)
- [CLI contract](./docs/commands.md)
- [Error codes](./docs/error-codes.md)
- [Agent usage](./docs/agent-usage.md)
- [Open questions](./docs/open-questions.md)
- [Changelog](./CHANGELOG.md)

## Границы

- Нет веб-API.
- Нет обязательного сервера.
- Нет общего multi-user backend.
