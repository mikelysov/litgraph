# Proposal

## Why

`POST /api/ingest` полностью сломан: сначала 422 (модель `Paper` требует `url`, которого нет в доке API), а с `url` — 500, потому что `queuing._redis_enqueue` вызывает `eval()` с kwargs, которых нет в upstash-redis 1.4.0 (`eval(script, numkeys, *keys_and_args)`). Ингест через API не работает вообще; работает только обходной путь — ручной `RPUSH` в Redis. Worker при этом жив (heartbeat каждые 5с), но долгоживущий контейнер держит устаревший код в памяти, что маскирует вторую половину бага.

## What Changes

- `queuing._redis_enqueue`: убрать Lua-скрипт с несовместимым вызовом `eval(keys=..., args=...)`; атомарность через `SADD`→`RPUSH` как сейчас в fallback-ветке. Существующий код fallback уже корректен.
- `models.Paper`: поле `url` сделать опциональным (`default=""`) — оно не читается ни одним потребителем (worker, vector store, graph store). Убирать поле не будем, чтобы не сломать `arxiv.py` и MCP-путь без нужды.
- Рестарт worker-контейнера после фикса (код смонтирован volume'ом, но Python держит старые модули в памяти); в tasks добавлен шаг проверки, что worker понимает envelope `{"paper": {...}, "attempts": 0}`.
- API-док (`/docs` FastAPI) станет правдивым автоматически после фикса модели `Paper` — отдельная синхронизация доков не нужна.

## Capabilities

### New Capabilities

- `ingest-queue`: контракт `POST /api/ingest` (какие поля обязаны быть в запросе), поведение постановки в очередь Redis (дедупликация по id, повторные попытки), и разбор payload'а worker'ом — то, что сейчас сломано на всех трёх уровнях.

### Modified Capabilities

None. `openspec/specs/` пуст — capabilities из changes `post-test-fixes` (answer-path, embedding-path, graph-store, mcp-surface, test-harness) ещё не применены и не пересекаются с ingest-путём.

## Impact

- `backend/src/queuing.py` — `_redis_enqueue`, удаление `_ENQUEUE_LUA`.
- `backend/src/models.py` — `Paper.url` становится опциональным.
- `backend/tests/test_queuing.py` — фикстуры уже передают `url`; добавится тест на ingest без `url` и на запись дедупликации.
- `infra/compose.yml` — без изменений; рестарт worker'а операционный шаг.
- Риск: падение между `SADD` и `RPUSH` может оставить id в множестве без payload в списке (тот же потолок, что у текущего fallback — задокументировано в коде).
