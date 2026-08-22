# Native reranker in Docker

Anchor can call a native `/v1/rerank` endpoint through `provider.rerank_base_url`.
The included `docker-compose.reranker.yml` runs Qwen3-Reranker-0.6B through vLLM
and keeps Ollama available for embeddings and memory extraction.

The compose service requires a Linux host with an NVIDIA GPU and the NVIDIA
Container Toolkit. Start it with:

```bash
docker compose -f docker-compose.reranker.yml --profile gpu up -d --wait
docker compose -f docker-compose.reranker.yml logs -f anchor-reranker
```

Configure Anchor to use the native endpoint:

```toml
[provider]
rerank_base_url = "http://127.0.0.1:8000/v1"
rerank_api_key_env = ""
rerank_model = "Qwen/Qwen3-Reranker-0.6B"
```

Smoke-test the service:

```bash
curl http://127.0.0.1:8000/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen/Qwen3-Reranker-0.6B","query":"database indexing","documents":["database migration","cooking recipe"]}'
```

Docker Desktop on macOS does not provide NVIDIA CUDA passthrough. On a Mac-only
host, run the service on a Linux/NVIDIA machine or keep native rerank disabled;
Anchor will continue using lexical/vector retrieval and its chat fallback.

The shipped image was resolved from the registry and pinned to an immutable
manifest digest on 2026-08-20. Digest updates require a reviewed source diff,
dependency audit, rendered Compose validation, and a Linux/NVIDIA health smoke
before production acceptance. The bundled profile publishes only
to host loopback, does not reuse
`OPENAI_API_KEY`, and intentionally refuses plaintext HTTP for remote hosts.
