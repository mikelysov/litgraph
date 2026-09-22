# memory.md — Litgraph project notes

## Embedding backend: remote API

Using `llama-server` on `172.31.61.121:1234` (host machine in local network).
Model: `text-embedding-qwen3-embedding-0.6b`, dim=1024, ctx=32k.
Switched from `text-embedding-multilingual-e5-large-instruct` (1024-dim, 512 ctx) 2026-09-20 — same dim, no DB reindex needed on dim, but vectors must match model.
Switched from local SentenceTransformer to remote API 2026-07-14.

To switch back to local: uncomment `EMBEDDING_MODEL_PATH`, comment `EMBEDDING_API_URL`/`EMBEDDING_MODEL`.

## LLM backend: remote API

Using `llama-server` on `172.31.61.121:1234` (host machine in local network).
Model: `qwen3.5-4b@q4_k_xl`.
Switched from local Gemma 3 4B IT to remote llama-server 2026-07-14.

To switch back to local: comment `LLM_API_URL`/`LLM_MODEL`, uncomment `LLM_MODEL_PATH`.

## Model locations (host paths)

- `/mnt/d/colab/llms/jina-reranker-v3` — Reranker (Jina V3, local, still active)
- `/mnt/d/colab/llms/gemma-3-4b-it` — LLM (local, no longer used; kept available)
- `/mnt/d/colab/llms/e5-large-instruct` — Embedder (local, no longer used; kept available)

## Docker DNS

Docker DNS sometimes breaks (can't resolve pypi.org). Workaround:
- Restart Docker daemon
- Or pre-build images before DNS goes down
- Images: `litgraph-local-api`, `litgraph-local-worker`, `litgraph-local-mcp` share same `backend/Dockerfile`

## Port assignments

- 8889 — API (FastAPI)
- 8888 — MCP server
- 5173 — Frontend dev (Vite)
- 6379 — Redis
- 8080 — Frontend prod (nginx)

## Ingest queue: gotchas (2026-09-22)

- `Paper.url` is optional (`default=""`). Do not re-add `url: str` as required —
  it broke `POST /api/ingest` with 422 (nobody in the pipeline reads url).
- `queuing._redis_enqueue` uses plain `sadd`→`rpush`. Lua eval removed:
  upstash-redis 1.4.0 signature is `eval(script, numkeys, *keys_and_args)` —
  kwargs `keys=`/`args=` raise TypeError. Known ceiling: crash between sadd and
  rpush strands the id in the set (fix: `SREM paper_queue_ids <id>`).
- Worker runs old code until restarted: code is volume-mounted, but Python keeps
  imported modules in memory. After any ingest-path change → `docker restart
  litgraph-local-worker-1 litgraph-local-api-1`. (`docker compose restart`
  fails: project built with profiles, depends_on `arcadedb` profile `core`.)
- "Worker молчит" ≠ worker сломан: heartbeat `Waiting for paper in queue...`
  каждые 5с при пустой очереди (DEBUG). Real signal: `Indexed N/M papers`.
- LM Studio latency myth: 30s embedding / 35s ask not reproducible. Measured
  from host and containers: embed 0.03–0.63s, /ask 1.6–2.6s (top_k=20).
  If slow again — check LM Studio load state, not our code.
- OpenSpec change `fix-ingest-queue-worker` — fixed all three (e2e verified:
  ingest 200 → queued → Indexed 1/1 → embedded). Unit tests: 20 passed, 2 skipped.
