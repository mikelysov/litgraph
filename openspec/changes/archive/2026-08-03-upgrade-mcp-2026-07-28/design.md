## Context

MCP-сервер (`backend/src/mcp_server.py`, 190 строк, 6 тулов) работает через `mcp.server.fastmcp.FastMCP` на SDK mcp 1.x (протокол 2025-11-25). Новый спек 2026-07-28 реализует только mcp 2.0.0, где:
- `mcp.server.fastmcp` удалён → заменён на `mcp.server.mcpserver.MCPServer` (тот же API: декоратор `@tool`, менеджеры tools/resources/prompts)
- протокол stateless, `initialize` убран; для старых клиентов сохранён legacy handshake-путь (`stateless_http=False`), который отвечает на `initialize` версией 2025-11-25
- клиент opencode 1.18.11 говорит только на 2025-11-25 (TS SDK 1.29.0, `LATEST_PROTOCOL_VERSION='2025-11-25'`, `connect()` всегда шлёт `initialize`) — поэтому stateless включать нельзя

Проверено при планировании:
- `mcp[cli]>=2.0.0` валиден (extra `cli` существует)
- pydantic в venv 2.13.4 ≥ 2.12 — удовлетворяет требованию mcp 2.0
- sync-тулы поддерживаются: `is_async_callable` → `anyio.to_thread.run_sync` (без изменений кода тулов)

## Goals / Non-Goals

**Goals:**
- Перейти на mcp SDK 2.0.0 + `MCPServer`, сохранив поведение 6 тулов
- opencode 1.18.11 подключается без правок клиента (совместимость на будущее — конфига сейчас нет)
- Навести порядок в зависимостях: убрать неиспользуемый `fastmcp`, закрепить `httpx`, пересобрать `uv.lock`, обновить AGENTS.md

**Non-Goals:**
- Включать `stateless_http=True` сейчас (сломает opencode; trigger — см. D5)
- Добавлять новые фичи спека 2026-07-28 (`cache_hints`, `subscriptions`, `extensions`, MRTR) — доступны автоматически, потребителей нет
- Добавлять OAuth/auth — в проекте нет, скоуп другой
- Менять тулы, API, endpoint-путь, конфиг opencode

## Decisions

**D1. `from mcp.server.mcpserver import MCPServer`** — замена `FastMCP`. Импорт в `mcp_server.py:9`. Декоратор `@tool` совместим; sync-функции не трогаем.

**D2. Параметры из ctor/settings переезжают в `run()`:**
```
mcp.run(
    transport="streamable-http",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8888")),
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=False,
)
```
`json_response` в ctor mcp 2.0 нет — только в `run()`. `mcp.settings.host/port` нет — host/port аргументы `run()`. Семантика `json_response` (тул возвращает dict → JSON-ответ) не гарантирована идентичной mcp 1.x — подтвердить smoke-тестом (T3.3), при расхождении — отдельный тикет.

**D3. Зависимости:**
- `mcp[cli]>=2.0.0` (пока <3: `>=2.0.0,<3`)
- `httpx>=0.28.1,<1` — явный pin, app-код юзает `httpx` (1.x); mcp 2.0 тянет `httpx2` (отдельный пакет, не конфликтует)
- `fastmcp` удаляется автоматически `uv sync` (вне lock — uv прунит)
- pydantic уже ≥2.12 — ограничение mcp 2.0 удовлетворено

**D4. Lock пересобрать через `uv lock` + `uv sync`** — не `uv pip install` (так venv и lock разъехались: 1.9.0 vs 1.29.0). После пересборки проверить дифф lock: транзитивные (mcp-types 2.0.0, httpx2, pyjwt, python-multipart, sse-starlette, uvicorn) не должны конфликтовать с существующими (fastapi, qdrant-client, redis, sentence-transformers).

**D5. Stateless — отложен, trigger:** включать `stateless_http=True` только когда opencode перейдёт на TS SDK с поддержкой `2026-07-28` (сейчас даже latest TS SDK 1.30.0 — `LATEST='2025-11-25'`). Флип — одна строка в `main()`, отдельный change.

## Risks / Trade-offs

- **Нельзя включить stateless сейчас**: opencode 1.18.11 (TS SDK 1.29.0) шлёт `initialize` → stateless-путь 2026-07-28 отвергнет (нет обработчика initialize). Даже последний TS SDK 1.30.0 — всё ещё 2025-11-25. D5 фиксирует trigger.
- **json_response-семантика**: mcp 1.x FastMCP vs 2.0 MCPServer могут отличаться в сериализации результатов. Митигация: smoke-тест с dict-возвращающим тулом (`health`, `ask`).
- **mcp 2.0.0 свежий** (мажор из недавнего): мелкие поведенческие отличия возможны. Митигация: полный smoke по acceptance-критериям proposal.
- **httpx2 vs httpx**: два пакета сосуществуют; если в будущем убрать qdrant-client (источник httpx 1.x) — app-код останется без httpx. Потому явный pin (D3).
- **uv.lock рассинхрон**: пересборка подтянет транзитивные обновления — проверить дифф, откатить несвязанные крупные бампы.
