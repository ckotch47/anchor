# Config

Конфиг хранится в user folder в одном файле:

- `~/.qatoria/anchor/config.toml`
- `config.example.toml` in the repo root shows all supported keys and defaults.

## Data store

- `~/.qatoria/anchor/anchor.sqlite3`

## Формат

TOML.

## Структура

```toml
[runtime]
default_view = "compact"
default_limit = 20
default_project = "workspace"
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
- config should carry default project scope, provider URL, model names, and vector settings;
- config should carry default project scope, and CLI `--project` should override it per command;
- provider URL may point to a local OpenAI-compatible endpoint;
- when `runtime.offline_only = true`, generation layers should stay inactive and retrieval should degrade to non-generative paths;
- profiles are optional and live in the same file.

## Bootstrap

- `anchor config init` creates `~/.qatoria/anchor/config.toml` from `config.example.toml`.
- `anchor config init --force` overwrites the user config with the example content.
- `anchor config init` fails with `CONFIG_EXISTS` if the user config already exists and `--force` is not set.
