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
- Shared document spine + domain tables for notes, tasks, and history.
- Retrieval-ready from day one: FTS, vector search, embeddings, rerank.
- При старте CLI автоматически применяет pending migrations, чтобы агент не управлял bootstrap вручную.
- CLI как машинный протокол для агентов.
- OpenAI-compatible модели как внешний provider для embeddings и rerank, preferably local.

## Документы

- [Naming](./docs/naming.md)
- [Assessment](./docs/assessment.md)
- [Production architecture](./docs/production-architecture.md)
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
- [Wiki export](./wiki/README.md)
- [Changelog](./CHANGELOG.md)

## Быстрый старт

```bash
make venv
make install
make run
```

Если нужен релизный пакет:

```bash
make build
pip install dist/*.whl
```

Или вручную:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/anchor --help
```

Нативное SQLite vector-ускорение опционально. Базовая установка использует
ограниченный Python fallback; extension можно включить явно:

```bash
.venv/bin/pip install -e '.[vector]'
```

`sqliteai-vector` распространяется по отдельным условиям. Перед коммерческим,
закрытым или managed-service использованием extra `vector` нужно отдельно
подтвердить совместимость лицензии зависимости; базовая установка её не тянет.

## Границы

- Нет веб-API.
- Нет обязательного сервера.
- Нет общего multi-user backend.
