# mcp-server

## ADDED Requirements

### Requirement: Протокол 2026-07-28 через mcp SDK 2.0.0
MCP-сервер работает на Python SDK `mcp` 2.0.0 с высокоуровневым API `mcp.server.mcpserver.MCPServer` (преемник удалённого `mcp.server.fastmcp.FastMCP`).

#### Scenario: Сервер стартует на новом SDK
- **WHEN** запускается `uv run poe mcp`
- **THEN** сервер поднимается на `mcp` 2.0.0, `tools/list` и вызовы тулов отвечают, ошибок импорта нет

### Requirement: Все 6 тулов сохранены без изменения поведения
`search`, `ask`, `ingest_paper`, `ingest_pdf`, `get_paper`, `health` — синхронные функции, работают в mcp 2.0.0 (sync-вызовы через `anyio.to_thread`), возвращают прежний формат.

#### Scenario: Вызов существующего тула
- **WHEN** клиент вызывает `search` с `query` и `top_k`
- **THEN** результат идентичен поведению на mcp 1.x, ошибки оборачиваются как раньше

#### Scenario: Валидация аргументов
- **WHEN** клиент вызывает тул с невалидными аргументами (например `search` с `top_k` не-числом)
- **THEN** сервер отвечает ошибкой валидации, тул не исполняется

### Requirement: Совместимость с клиентом opencode 1.18.11
Сервер запускается с `stateless_http=False` — legacy handshake-путь mcp 2.0.0 отвечает на `initialize` с версией 2025-11-25. Совместимость forward-looking: на момент миграции конфига opencode, указывающего на сервер, нет.

#### Scenario: opencode подключается при добавлении конфига
- **WHEN** в `.opencode/opencode.json` добавлен remote-конфиг `http://localhost:8888/mcp`
- **THEN** opencode 1.18.11 показывает статус `connected`, 6 тулов сервера видны в каталоге

### Requirement: json_response и endpoint-путь сохранены
`json_response=True` переносится в `run()`, `streamable_http_path="/mcp"` — дефолт, путь не меняется.

#### Scenario: Ответы в JSON-режиме
- **WHEN** тул возвращает строку/dict
- **THEN** ответ сериализуется в формате, совпадающем с json_response-режимом mcp 1.x (проверяется smoke-тестом на `health`/`ask`)

### Requirement: Детерминированный порядок tools/list
`tools/list` возвращает тулы в стабильном порядке (порядок регистрации декораторов).

#### Scenario: Два последовательных tools/list
- **WHEN** клиент дважды запрашивает `tools/list` в рамках одной сессии
- **THEN** порядок тулов одинаковый
