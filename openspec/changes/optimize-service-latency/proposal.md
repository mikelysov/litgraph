## Why

`/ask` takes ~44.5s end-to-end: Jina Reranker V3 (0.6B) runs on CPU in a CPU-only container (~34s of that total). Host has RTX 3090 free and GPU compose/Dockerfile targets already exist but are unused. Separately, ingestion model work starts up to ~70s late: worker sleeps with exponential backoff (up to 60s) between `blpop` cycles even though `blpop` already blocks. Entity extraction inside a worker batch is strictly sequential (N remote LLM calls).

## What Changes

- Run stack with GPU for api+worker (`USE_GPU=1`); rerank uses CUDA when available, CPU fallback otherwise (code path already present).
- Worker pickup: drop sleep/backoff; tiered `blpop` timeouts (idle wait + short batch-fill) so worst-case pickup drops from ~70s to ~6s.
- Parallel entity extraction across a worker batch via thread pool (IO-bound remote LLM calls).
- Cap ask LLM `max_new_tokens` (env-configurable) to bound generation latency.
- Targeted async: remote embed/LLM HTTP via `httpx.AsyncClient`; `/ask` and `/search` as `async def` with sync store/rerank offloaded via `asyncio.to_thread`. Worker stays sync.
- Qdrant/Neo4j clients stay sync (measured ~0.17s, not the bottleneck).

## Capabilities

### New Capabilities
- `search`: Search and ask — GPU-accelerated rerank with CPU fallback, bounded ask generation, non-blocking remote model HTTP under concurrent load.
- `ingest`: Paper ingestion — worker picks queued papers up within a bounded idle delay; batch entity extraction overlaps in time.

### Modified Capabilities
<!-- none — no existing specs under openspec/specs/ -->

## Impact

- `backend/src/worker.py` — pickup loop rewrite; parallel `extract_entities`
- `backend/src/llm.py` — env cap for ask tokens; async HTTP generate helpers; rerank stays local (sync / `to_thread`)
- `backend/src/embedder.py` — async HTTP embed helpers; keep sync API for worker
- `backend/src/api.py` — async `/ask`, `/search` (and `/ingest` only if needed for consistency)
- `infra/compose.gpu.yml`, `backend/Dockerfile` (`gpu` target) — enable via `USE_GPU=1` (already present)
- `Makefile` — `rebuild` / `up-full-dev` with `USE_GPU=1` (no `up-full` target exists)
- Tests: `backend/tests/test_worker.py` — `get_batch` signature stays backward-compatible; process_batch happy path unchanged
- No new external dependencies (httpx already present)
