## 1. Worker pickup latency (spec: ingest)

- [x] 1.1 Rewrite `get_batch` in `src/worker.py`: tiered timeouts `idle_timeout=5`, `fill_timeout=1` (first blpop idle, subsequent fill); keep default-friendly signature so existing tests can call `get_batch(redis, max_items)`
- [x] 1.2 Rewrite `run_worker_loop`: remove sleep/backoff/`SLEEP_INTERVAL`; loop is `get_batch` → if papers then `process_batch` → repeat
- [x] 1.3 Remove unused `sleep` import and `SLEEP_INTERVAL`
- [x] 1.4 Fix `test_get_batch_with_invalid_paper` to mock `blpop` (not `lpop`); ensure valid-batch and process_batch tests still pass

## 2. Parallel entity extraction (spec: ingest)

- [x] 2.1 In `process_batch`, after embed succeeds, run graph `extract_entities` via `ThreadPoolExecutor(max_workers=min(BATCH_SIZE, n))` while preserving MockStore skip and per-paper try/error handling
- [x] 2.2 Extend or add unit test that multiple papers trigger concurrent extract (mock with barrier/side_effect timing) or at least N extract calls without changing happy-path assertions

## 3. Ask token cap (spec: search)

- [x] 3.1 In `generate_rag_answer`, replace hardcoded `max_new_tokens=4096` with env `LLM_MAX_ASK_TOKENS` (default 1024); document in config or AGENTS if needed
- [x] 3.2 Smoke: single `/ask` still returns parseable JSON answer

## 4. Async remote HTTP + endpoints (spec: search)

- [x] 4.1 Add shared `httpx.AsyncClient` lifecycle (create in FastAPI lifespan, aclose on shutdown) used by embedder and llm remote paths
- [x] 4.2 Add async remote embed helpers; keep sync `embed_query` / `embed_papers` for worker (sync httpx or `httpx.post` as today)
- [x] 4.3 Add async remote `generate` / `generate_rag_answer`; keep sync for worker `extract_entities`
- [x] 4.4 Convert `/ask` and `/search` to `async def`; run `vector_search` and sync `rerank` via `asyncio.to_thread` (do not double-call embed outside `vector_search`)
- [x] 4.5 Optionally convert `/ingest` to `async def` for consistency only; not required for latency

## 5. GPU stack bring-up (spec: search)

- [x] 5.1 Confirm `llm.py` reranker path needs no code change when CUDA present (`_get_device` + `device_map="auto"`)
- [x] 5.2 `USE_GPU=1 make rebuild` then `USE_GPU=1 make up-full-dev` (or `USE_GPU=1 make up`) for api+worker
- [x] 5.3 Verify in api container: `torch.cuda.is_available() is True` and logs show `Reranker device: cuda`

## 6. End-to-end verification

- [x] 6.1 Time `/ask` before/after on GPU (expect large drop vs ~44s CPU baseline; rerank stage no longer ~34s)
- [x] 6.2 Enqueue a paper after worker idle ≥1 min; confirm process starts within ~idle_timeout+fill_timeout, not after multi-minute sleep
- [x] 6.3 Concurrent two `/ask` or `/search` while first is in flight — both complete (no hard serial queue on remote wait)
- [x] 6.4 `cd backend && uv run poe test` green
- [x] 6.5 Align AGENTS.md GPU note with real Makefile targets (`up-full-dev` / `rebuild` + `USE_GPU=1`) if docs still say only `up-full`
