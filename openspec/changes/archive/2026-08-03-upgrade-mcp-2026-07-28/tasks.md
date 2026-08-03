## 1. Зависимости

- [x] 1.1 В `backend/pyproject.toml`: `mcp[cli]>=1.4.1` → `mcp[cli]>=2.0.0,<3`; добавить `httpx>=0.28.1,<1`
- [x] 1.2 Пересобрать lock из `backend/`: `uv lock && uv sync`
- [x] 1.3 Проверить дифф `uv.lock`: `mcp` 2.x + `mcp-types` 2.x присутствуют; проверить транзитивные (httpx2, pyjwt, python-multipart, sse-starlette, uvicorn) не конфликтуют с fastapi/qdrant-client/redis/sentence-transformers; pydantic ≥ 2.12. Откатить несвязанные крупные бампы, если появились
- [x] 1.4 Убедиться, что `fastmcp` удалён из venv (`uv sync` прунит пакеты вне lock): `uv pip list | grep fastmcp` — пусто

## 2. Код сервера

- [x] 2.1 В `backend/src/mcp_server.py:9` заменить импорт: `from mcp.server.fastmcp import FastMCP` → `from mcp.server.mcpserver import MCPServer`
- [x] 2.2 Заменить `FastMCP("Litgraph", json_response=True)` → `MCPServer("Litgraph")` (строка 21)
- [x] 2.3 Переписать `main()` (строки 183-186): `mcp.run(transport="streamable-http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("MCP_PORT", "8888")), streamable_http_path="/mcp", json_response=True, stateless_http=False)`
- [x] 2.4 Сантити-чек импорта: `python -c "from mcp.server.mcpserver import MCPServer; import mcp; print('ok')"`
- [x] 2.5 `uv run poe typecheck` и `uv run poe lint` по `src/mcp_server.py`
- [x] 2.6 Обновить `AGENTS.md` (Stack): «MCP: FastMCP (streamable-http)» → «MCP: mcp-server (MCPServer, streamable-http)»

## 3. Проверка

- [x] 3.1 Запустить `uv run poe mcp` — сервер поднялся без ошибок
- [x] 3.2 Smoke `tools/list` через curl (legacy handshake-путь, два шага):
  - [ ] 3.2.1 `curl -i -X POST http://localhost:8888/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'` — запомнить `Mcp-Session-Id` из ответа
  - [ ] 3.2.2 `curl -X POST http://localhost:8888/mcp -H "Content-Type: application/json" -H "Mcp-Session-Id: <id>" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'` — 6 тулов, стабильный порядок
- [x] 3.3 Вызвать dict-возвращающий тул (`health` или `ask`) через curl с тем же сессионным заголовком — сверить формат ответа с mcp 1.x (проверка json_response-семантики)
- [x] 3.4 opencode-подключение (конфига сейчас нет): временно добавить remote-конфиг в `.opencode/opencode.json` → статус `connected`, тулы видны; после проверки решить — оставить или убрать
- [x] 3.5 `uv run poe test` — существующие тесты зелёные
