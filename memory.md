# memory.md — Litgraph project notes

## Embedding backend: remote API

Using `llama-server` on `172.31.61.121:1234` (host machine in local network).
Model: `text-embedding-bge-m3`, dim=1024.
Switched from local SentenceTransformer to remote API 2026-07-14.

To switch back to local: uncomment `EMBEDDING_MODEL_PATH`, comment `EMBEDDING_API_URL`/`EMBEDDING_MODEL`.

## LLM backend: remote API

Using `llama-server` on `172.31.61.121:1234` (host machine in local network).
Model: `qwen3.5-4b`.
Switched from local Gemma 3 4B IT to remote Gemma 3 12B 2026-07-14.

To switch back to local: comment `LLM_API_URL`/`LLM_MODEL`, uncomment `LLM_MODEL_PATH`.

## Model locations (host paths)

- `/mnt/d/colab/llms/jina-reranker-v3` — Reranker (Jina V3, local, still active)
- `/mnt/d/colab/llms/gemma-3-4b-it` — LLM (local, no longer used; kept available)
- `/mnt/d/colab/llms/bge-m3` — Embedder (local, no longer used; kept available)

## Docker DNS

Docker DNS sometimes breaks (can't resolve pypi.org). Workaround:
- Restart Docker daemon
- Or pre-build images before DNS goes down
- Images: `litgraph-local-api`, `litgraph-local-worker`, `litgraph-local-mcp` share same `backend/Dockerfile`

## Port assignments

- 8889 — API (FastAPI)
- 8888 — MCP server
- 5173 — Frontend dev (Vite)
- 6333/6334 — Qdrant
- 6379 — Redis
- 8080 — Frontend prod (nginx)
