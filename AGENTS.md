# AGENTS.md — Litgraph

## Setup

```bash
make up-full        # Full stack (CPU)
make up-full USE_GPU=1  # With GPU
```

Services:
- API → http://localhost:8889/docs
- MCP Server → http://localhost:8888/mcp (streamable-http)
- Frontend → http://localhost:5173 (dev)
- Qdrant UI → http://localhost:6333/dashboard
- Redis → localhost:6379

## Key Configuration

Embeddings: remote API `http://172.31.61.121:1234/v1`, model `text-embedding-bge-m3`.
LLM: remote API `http://172.31.61.121:1234/v1`, model `google/gemma-3-12b`.
Reranker: local model via filesystem (`/mnt/d/colab/llms/jina-reranker-v3`).

Env files:
- `infra/app/.env` — Docker container vars (Qdrant, Redis, models)
- `infra/qdrant/.env` — Qdrant connection + embedder
- `.env` — local dev (non-Docker)

## Stack

Backend: FastAPI + Pydantic + uv
LLM: llama-server remote API (Google Gemma 3 12B)
Reranker: HuggingFace Transformers (Jina Reranker V3, local)
Embeddings: llama-server remote API (BGE-M3, 1024-dim)
MCP: FastMCP (streamable-http)
Queue: Redis
Vector DB: Qdrant
Frontend: React + Vite + Tailwind
Infra: Docker Compose

## Common Commands

```bash
cd backend && uv run poe server     # Start API directly
cd backend && uv run poe mcp        # Start MCP server directly
cd backend && uv run poe pipeline   # End-to-end pipeline
cd backend && uv run poe test       # Run tests
make logs-api                       # Tail API logs
make logs-worker                    # Tail worker logs
```

## Docker DNS Issues

If containers fail to build with pypi.org DNS errors:
```bash
sudo systemctl restart docker
# Or add DNS to /etc/docker/daemon.json:
# { "dns": ["8.8.8.8", "1.1.1.1"] }
```
