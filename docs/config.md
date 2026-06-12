# Config

Конфиг хранится в user folder в одном файле:

- `~/.qatoria/anchor/config.toml`

## Data store

- `~/.qatoria/anchor/anchor.sqlite3`

## Формат

TOML.

## Структура

```toml
[runtime]
default_view = "compact"
default_limit = 20
default_budget_tokens = 800
retry_attempts = 3
busy_timeout_ms = 250
offline_only = true

[provider]
base_url = "https://api.example.com/v1"
api_key_env = "OPENAI_API_KEY"
embedding_model = "text-embedding-3-small"
rerank_model = "gpt-5.5"

[vector]
dimension = 1536
distance = "cosine"
chunk_size = 400
chunk_overlap = 50

[profiles.default]
view = "compact"
limit = 20

[profiles.full]
view = "full"
limit = 50
```

## Principles

- one file in the user home directory;
- explicit overrides from CLI flags win over config;
- config should carry provider URL, model names, and vector settings;
- profiles are optional and live in the same file.
