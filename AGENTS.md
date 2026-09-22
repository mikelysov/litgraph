# AGENTS.md — Litgraph

## Setup

```bash
make up-full-dev    # Full stack (CPU)
USE_GPU=1 make rebuild   # With GPU (rebuild + up)
```

Services:
- API → http://localhost:8889/docs
- MCP Server → http://localhost:8888/mcp (streamable-http)
- Frontend → http://localhost:5173 (dev)
- Redis → localhost:6379

Venv: `backend/.venv` (managed by uv; `uv run` из `backend/`).

## Key Configuration

Embeddings: remote API `http://172.31.61.121:1234/v1`, model `text-embedding-qwen3-embedding-0.6b`.
LLM: remote API `http://172.31.61.121:1234/v1`, model `qwen3.5-4b@q4_k_xl`.
Reranker: local model via filesystem (`/mnt/d/colab/llms/jina-reranker-v3`).

Env files:
- `infra/app/.env` — Docker container vars (ArcadeDB, Redis, models)
- `.env` — local dev (non-Docker)

## Stack

Backend: FastAPI + Pydantic + uv
LLM: llama-server remote API (qwen3.5-4b@q4_k_xl)
Reranker: HuggingFace Transformers (Jina Reranker V3, local)
Embeddings: llama-server remote API (text-embedding-qwen3-embedding-0.6b, 1024-dim, 32k ctx)
MCP: mcp SDK 2.0.0 (MCPServer, streamable-http; proto 2026-07-28, handshake 2025-11-25)
MCP client: opencode (global `~/.config/opencode/opencode.json`) → http://localhost:8888/mcp
Queue: Redis
Vector DB: ArcadeDB
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

## Gotchas

- `Paper.url` optional (`default=""`) — required `url` broke `POST /api/ingest` (422).
- Queue enqueue: plain `sadd`→`rpush` (no Lua — upstash-redis 1.4.0 eval signature incompatible with kwargs).
- Code is volume-mounted, but worker keeps old modules in memory: restart worker+api containers after ingest-path changes (`docker compose restart` fails on profiles — restart containers directly).
- Empty queue = `Waiting for paper in queue...` heartbeat every 5s in worker log — это норма, не зависание.
- Env details and history: see `memory.md`.
