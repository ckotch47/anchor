# Error Codes

Список стабильных кодов ошибок для machine mode.

## Base set

- `INVALID_ARGS` - invalid CLI arguments or unsupported flags.
- `CONFIG_EXISTS` - config init was requested but the user config already exists.
- `NOT_FOUND` - requested entity does not exist.
- `DB_LOCKED` - SQLite is temporarily locked.
- `DB_MIGRATION_FAILED` - migration could not be applied safely.
- `INDEX_STALE` - derived index is stale or missing.
- `PROVIDER_OFFLINE` - embeddings/rerank provider is unavailable.
- `PROVIDER_ERROR` - provider returned an unexpected failure.
- `OFFLINE_ONLY` - command requested generation, but only offline mode is available.
- `RETRY_EXHAUSTED` - retry attempts were exhausted.
- `INTERNAL_ERROR` - unexpected local failure.

## Rules

- `error.code` must be stable and machine-readable.
- `retryable` must be explicit when retry makes sense.
- user-facing text can change, code names should not.
