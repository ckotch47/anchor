# Stack

## Primary runtime

- Python 3.11+

## Canonical product name

- Product: `Qatoria Anchor`
- CLI binary: `anchor`
- Package/module: `anchor`
- Config dir: `~/.qatoria/anchor`

## Core libraries

- `typer` for CLI entrypoint and subcommands
- `pydantic` for config and structured schemas
- `openai` official SDK for embeddings and rerank provider calls against an OpenAI-compatible endpoint
- `sqlite-vector` for in-database vector search
- built-in `sqlite3` for local storage

## Optional helpers

- `numpy` for local cosine similarity and vector math if needed
- `rich` for human-friendly TTY output

## Why this stack

- Python is fast to generate, easy to read, and easy to patch in an agent-assisted workflow.
- SQLite stays local and simple.
- Typer keeps the CLI contract explicit without a heavy framework.
- Pydantic gives a strong schema boundary for config and machine output.
- The official OpenAI SDK keeps provider integration aligned with documented client behavior.

## Notes

- The stack is intentionally small but production-oriented.
- Packaging/distribution remains a separate decision.
- `sqlite-rag`, `sqlite-memory`, and `sqlite-ai` are useful references and future extension candidates, but not mandatory runtime dependencies for the first production slice.
- If the search pipeline later needs a faster native path, the storage contract should stay unchanged.
