# Tasks

## 1. Модель Paper

- [x] 1.1 В `backend/src/models.py` сделать `Paper.url` опциональным (`url: str = ""`); проверить `uv run pytest tests/ -k models` зелёный (или fallback: `uv run python -c "from src.models import Paper; Paper(id='x', title='t', abstract='a', authors=[])"` без исключения)

## 2. Очередь

- [x] 2.1 В `backend/src/queuing.py` удалить `_ENQUEUE_LUA` и eval-ветку из `_redis_enqueue`, оставить только sadd+rpush; добавить комментарий про потолок (гонка SADD/RPUSH, путь апгрейда — MULTI/EXEC)
- [x] 2.2 Обновить/добавить unit-тест в `backend/tests/test_queuing.py`: повторный `enqueue_papers` той же статьи не увеличивает длину очереди; прогнать `uv run pytest tests/test_queuing.py`
- [x] 2.3 Добавить тест: статья без `url` проходит `enqueue_papers` и `parse_payload` в обе стороны; `uv run pytest tests/test_queuing.py tests/test_worker.py` зелёный

## 3. Контейнеры и E2E

- [x] 3.1 `docker compose --profile app --profile worker --profile redis-local restart worker api` из `infra/`; убедиться, что лог worker'а показывает свежие записи
- [x] 3.2 E2E: `POST /api/ingest` с телом без `url` → HTTP 200, статус `queued` (`GET /api/status?paper_id=...`); в логах worker'а строка `Indexed 1/1`; затем статус `embedded`; очистить тестовый id из `paper_queue_ids` (`SREM`)
