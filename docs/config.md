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
memory_auto_extract = false
memory_external_send = false
memory_external_projects = []
embedding_external_send = false
embedding_external_projects = []
rerank_external_send = false
rerank_external_projects = []
memory_extract_batch_size = 10
memory_extract_max_facts = 20
memory_extract_min_interval_seconds = 60

# Use ["*"] only for an explicit all-projects external-send policy.

[provider]
base_url = "https://api.example.com/v1"
rerank_base_url = ""
rerank_api_key_env = ""
api_key_env = "OPENAI_API_KEY"
embedding_model = "text-embedding-3-small"
rerank_model = "gpt-5.5"
memory_model = ""
rerank_max_response_bytes = 1048576
max_batch_items = 100
max_batch_characters = 200000

`provider.rerank_base_url` is optional. When set, Anchor calls the native
rerank endpoint. `provider.rerank_api_key_env` is independent from the OpenAI
key and empty by default; remote endpoints require HTTPS.
`POST /rerank` endpoint (for example, a llama.cpp server started with
`--reranking`) instead of asking a chat model to return JSON scores. Leave it
empty for the OpenAI-compatible chat fallback.

Plain HTTP provider URLs are accepted only for loopback. Remote embedding and
rerank endpoints additionally require their purpose-specific `*_external_send`
flag and an exact project entry in the matching allowlist; an empty allowlist is
always deny. Multi-project search is sent only when every requested project is
allowed. Provider responses are bounded and diagnostics never persist raw
provider exception bodies. Embedding calls are split into batches bounded by
`max_batch_items` and `max_batch_characters`; rerank requests exceeding either
bound fail locally and retrieval falls back to its non-reranked ordering.

[metadata]
enabled = true

[metadata.entities.notes]
allow_extra = true

[metadata.entities.notes.fields.topic]
type = "string"
required = false

[metadata.entities.tasks]
allow_extra = true

[metadata.entities.tasks.fields.priority]
type = "integer"
required = false

[metadata.entities.history]
allow_extra = true

[metadata.entities.history.fields.correlation_id]
type = "string"
required = false

[links]
relation_types = ["references", "blocks", "duplicates", "implements", "related", "caused_by", "derived_from"]

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
- config should carry typed metadata schemas for entities that need validated metatags;
- config should carry the canonical relation types for the document graph;
- config should carry default project scope, and CLI `--project` should override it per command;
- provider URL may point to a local OpenAI-compatible endpoint;
- `provider.memory_model` enables explicit `memory extract` L1/L2 generation when `offline_only = false`;
- when `runtime.offline_only = true`, generation layers should stay inactive and retrieval should degrade to non-generative paths;
- profiles are optional and live in the same file.

## Bootstrap

- `anchor config init` creates `~/.qatoria/anchor/config.toml` from `config.example.toml`.
- `anchor config init --force` overwrites the user config with the example content.
- `anchor config init` fails with `CONFIG_EXISTS` if the user config already exists and `--force` is not set.
