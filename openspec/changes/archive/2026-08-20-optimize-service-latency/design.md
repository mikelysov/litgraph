## Context

See proposal.md — Why. Current stack: CPU-only containers (`USE_GPU` unset), sync FastAPI endpoints in threadpool, sync `httpx.post` for remote embed/LLM, worker `blpop(5s)×BATCH_SIZE → sleep(backoff≤60s)`. Host: RTX 3090 (~17GB free). `infra/compose.gpu.yml` + Dockerfile `gpu` target exist. Reranker preloads at API startup (`llm.preload()`); load path already GPU-aware (`_get_device()`, `device_map="auto"` when cuda). Embed lives inside sync `store.core.search` via `embed_query` — `/ask` does not call embed separately today.

Makefile targets: `up-full-dev`, `up-full-prod`, `rebuild` honor `USE_GPU=1`. There is no `up-full` phony target (docs/AGENTS.md name is informal).

## Goals / Non-Goals

**Goals:**
- Cut `/ask` wall time: GPU rerank + token cap (target order-of-magnitude drop vs CPU baseline ~44s).
- Bound ingest→process start delay (worst case seconds, not tens of seconds).
- Overlap concurrent remote LLM entity extraction within a worker batch.
- Make remote embed/LLM HTTP non-blocking under concurrent `/ask`/`/search` (async client + async endpoints).

**Non-Goals:**
- Async Qdrant/Neo4j drivers.
- Async Redis blpop / asyncio worker process.
- Changing rerank model or ranking quality contract.
- Changes to remote llama-server (already fast: embed tens of ms, LLM sub-second to few seconds).
- Making local `model.rerank` truly async (CPU/GPU bound; use `to_thread`).

## Decisions

**D1: GPU via existing compose override (infra-first)**  
Reranker device selection already in `llm.py`. Enable with `USE_GPU=1` on `make rebuild` / `make up-full-dev` (compose.gpu.yml: `runtime: nvidia`, device reservation, Dockerfile `gpu` installs torch cu121).  
*Alternatives*: manual `--gpus` — rejected (Makefile path exists). Separate remote rerank service — rejected (overkill for one 0.6B model).

**D2: Targeted async HTTP + async endpoints; worker stays sync**  
Add `httpx.AsyncClient` (module singleton, timeouts matching current 60s/120s) for remote embed and chat completions. Expose `async` helpers; keep sync wrappers for worker (`embed_papers`, `extract_entities`, `generate`). Convert `/ask` and `/search` to `async def`. Local rerank and sync `store.core.search` (embed+Qdrant+graph) run via `await asyncio.to_thread(...)` so the event loop is not blocked by GPU/CPU or sync clients.  
`/ingest` is Redis enqueue only (~ms); converting it is optional consistency, not a latency win.  
*Alternatives*: full asyncio worker — rejected (blpop + batch design fits threads). Dual AsyncQdrantClient — rejected (0.17s path).  
*Important*: do **not** wire “async embed then to_thread(vector_search)” as a separate embed step — that would double-embed. Either (a) to_thread entire `vector_search`, or (b) split search into async embed + sync vector/graph without calling `embed_query` twice. Prefer (a) for minimal surface; optional later split for finer concurrency.

**D3: Worker pickup — blpop is idle wait, tiered timeouts**  
`get_batch(..., idle_timeout=5, fill_timeout=1)`: first pop uses idle_timeout; further pops use fill_timeout. Drop `sleep`/`backoff`/`SLEEP_INTERVAL`. Empty batch → immediate next `get_batch` (next idle blpop). Worst-case single-paper delay ≈ idle_timeout + fill_timeout if arrival races timeout; typical = near-immediate while blocked in blpop.  
*Alternatives*: long single timeout (30s) — worse single-paper fill wait if misapplied to every pop. Keep backoff — causes the 70s gap.

**D4: Parallel entity extraction via ThreadPoolExecutor**  
In `process_batch`, after successful embed, run `extract_entities` for papers needing graph via `ThreadPoolExecutor(max_workers=min(BATCH_SIZE, n))`, then index/update state as today. Keep MockStore skip path. Preserve per-paper error handling (one failure must not mark whole batch ERROR).  
*Alternatives*: `asyncio.gather` in worker — rejected (sync process, thread pool is enough for IO-bound HTTP).

**D5: LLM token cap for ask only**  
`generate_rag_answer` uses `max_new_tokens` from env `LLM_MAX_ASK_TOKENS` (default **1024**, down from hardcoded 4096). Entity extraction and other callers keep their own caps.  
*Alternatives*: SSE streaming — out of scope. Cap 512 — may hurt answer quality; 1024 is first default, tunable.

**D6: Rerank stays sync function**  
`async def rerank` is unnecessary; call existing `rerank` under `to_thread` from async endpoints. Avoids fake-async around transformers.

## Risks / Trade-offs

- **GPU image rebuild (torch cu121 wheel size)** → one-time; CPU compose path unchanged. Rollback: rebuild/up without `USE_GPU=1`.
- **Host CUDA 13.x vs wheel cu121** → container CUDA runtime from wheel; sm_86 (3090) supported. Verify `torch.cuda.is_available()` after GPU bring-up.
- **GPU OOM if other processes hold VRAM** → risk if host VRAM fills; mitigation: check free memory before deploy; reranker ~0.6B fits in free ~17GB today.
- **Concurrent `/ask` on one GPU** → serializes on GPU lock inside process; async still helps HTTP wait, not multi-rerank throughput. Acceptable for expected concurrency.
- **ThreadPoolExecutor × BATCH_SIZE LLM calls** → may overload remote llama-server; bound by BATCH_SIZE=8. If remote queues, wall time still ≤ sequential worst case.
- **`to_thread` for whole search** → still uses default threadpool; fine at modest concurrency. Do not also hold event-loop with sync httpx.
- **AsyncClient lifecycle** → must create/close in FastAPI lifespan (or lazy + aclose on shutdown); leaking clients under reload is a footgun. Task: wire lifespan.
- **Worker tests** → `test_get_batch_with_invalid_paper` mocks `lpop` but code uses `blpop` (pre-existing flaky/wrong mock); fix mock when touching worker tests.
- **Makefile naming** → AGENTS.md says `make up-full`; real targets are `up-full-dev` / `up` / `rebuild`. Tasks must use real targets.

## Migration Plan

1. Code: worker pickup + parallel extract + token cap + async HTTP/endpoints (works on CPU path).
2. Infra: `USE_GPU=1 make rebuild` then `USE_GPU=1 make up-full-dev` (or `up`) for api+worker GPU images.
3. Verify: `torch.cuda.is_available()` in api; time `/ask`; enqueue paper and check worker log lag; `uv run poe test`.
4. Rollback: `make down` + up without `USE_GPU=1`; code still CPU-correct via `_get_device()`.

## Open Questions

None blocking. Optional later: split `store.core.search` embed for true async embed without `to_thread` on the whole path.
