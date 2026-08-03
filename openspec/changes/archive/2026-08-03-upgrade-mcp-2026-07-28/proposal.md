## Why

MCP-сервер `backend/src/mcp_server.py` сидит на протоколе 2025-11-25:
- `mcp` SDK 1.x (в lock 1.9.0, в venv 1.29.0) — только handshake-эра
- отдельный пакет `fastmcp` 3.4.5 требует `mcp<2.0` и не используется проектом (импорт идёт из `mcp.server.fastmcp`)

Спек 2026-07-28 — крупнейшая ревизия протокола: stateless, без `initialize`, MRTR, `resultType`, `server/discover`, `subscriptions/listen`, `ttlMs`/`cacheScope`, extensions. Реализует её только Python SDK `mcp` 2.0.0 (mcp-types 2.0.0). В mcp 2.0.0 высокоуровневый FastMCP-API переименован в `mcp.server.mcpserver.MCPServer`.

Решение принято: мигрировать на mcp 2.0.0. Ограничение — клиент opencode 1.18.11 (TS SDK 1.29.0) говорит только на 2025-11-25 через `initialize`, поэтому `stateless_http=False` (legacy handshake-путь в mcp 2.0.0). Stateless переключим одной строкой, когда opencode подтянет TS SDK с 2026-07-28.

## What Changes

- `pyproject.toml`: `mcp[cli]>=1.4.1` → `mcp[cli]>=2.0.0` (extra `cli` в 2.0.0 есть: typer + python-dotenv)
- Закрепить `httpx>=0.28.1,<1` явно: 3 файла (`src/llm.py`, `src/embedder.py`, `src/mcp_server.py`) импортируют его напрямую; mcp 2.0 тянет отдельный пакет `httpx2` — без явного pin'а httpx 1.x живёт только транзитивно через qdrant-client
- `fastmcp` 3.4.5 удалится автоматически при `uv sync` (вне lock, uv прунит несогласованные пакеты)
- `backend/src/mcp_server.py`:
  - импорт: `from mcp.server.fastmcp import FastMCP` → `from mcp.server.mcpserver import MCPServer`
  - `FastMCP("Litgraph", json_response=True)` → `MCPServer("Litgraph")` (json_response нет в ctor)
  - `mcp.settings.host/port` → аргументы `run()`
  - `run(transport="streamable-http", host=..., port=..., streamable_http_path="/mcp", json_response=True, stateless_http=False)`
- 6 тулов (`search`, `ask`, `ingest_paper`, `ingest_pdf`, `get_paper`, `health`) — синхронные, переносятся без изменений (mcp 2.0 гоняет sync через `anyio.to_thread`)
- `uv.lock` пересобрать (`uv lock` + `uv sync`) — сейчас рассинхрон: lock 1.9.0 vs venv 1.29.0
- AGENTS.md: раздел Stack («MCP: FastMCP (streamable-http)») → «MCP: mcp-server (MCPServer, streamable-http)»

## Acceptance Criteria

- [ ] `uv run poe mcp` поднимает сервер на mcp 2.0.0 без ошибок импорта
- [ ] `tools/list` возвращает 6 тулов в стабильном порядке; вызов тула (health/search) даёт прежний формат
- [ ] opencode подключается к `http://localhost:8888/mcp` (при добавлении remote-конфига) — статус `connected`
- [ ] `uv run poe test` — существующие тесты зелёные
- [ ] `fastmcp` отсутствует в venv, `uv.lock` синхронен с pyproject

## Capabilities

### New Capabilities
- `mcp-server`: MCP-сервер на протоколе 2026-07-28 (mcp SDK 2.0.0, MCPServer), обратная совместимость с клиентами 2025-11-25 через legacy handshake-путь

### Modified Capabilities
- (нет — спецификаций в `openspec/specs/` ещё нет)

## Impact

- `backend/pyproject.toml` — зависимости
- `backend/uv.lock` — пересборка (транзитивные: mcp-types 2.0.0, httpx2>=2.5, pydantic>=2.12, pyjwt, python-multipart, sse-starlette, uvicorn)
- `backend/src/mcp_server.py` — импорт, ctor, main()
- `AGENTS.md` — секция Stack
- `.venv` — fastmcp удаляется при `uv sync`
- Конфиг клиента: ни в `.opencode/opencode.json`, ни в глобальном конфиге сервер не подключён — существующего подключения не ломается; совместимость opencode проверяется при добавлении конфига
- MCP endpoint: путь `/mcp` сохраняется (дефолт mcp 2.0)
- Тесты: MCP-тестов нет (`tests/test_index.py`, `test_queuing.py`, `test_worker.py`) — ломать нечего
