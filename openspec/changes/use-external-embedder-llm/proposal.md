## Why

Локальный dev-конфиг (`backend/.env`) потерял внешние модели: эмбеддер ходит в remote API, а LLM упал на локальный `LLM_MODEL_PATH=~/colab/llms/gemma-3-4b-it`, которого нет → LLM не работает без Docker. Плюс после миграции на ArcadeDB в репо остались мёртвые Qdrant-хвосты (env-переменные, осиротевшие `infra/qdrant/*`, `infra/fly/qdrant/*`, broken `migrate.py`) и устаревшие имена моделей в доках.

## What Changes

- Использовать внешний сервис эмбеддера и LLM: адрес `http://172.31.61.121:1234/v1`, эмбеддер `text-embedding-multilingual-e5-large-instruct`, LLM `qwen3.5-4b@q4_k_xl`.
- `backend/.env`: добавить `LLM_API_URL` + `LLM_MODEL=qwen3.5-4b@q4_k_xl`, закомментировать локальный `LLM_MODEL_PATH` (дефолт на remote).
- `backend/src/config.py`: исправить устаревший дефолт `EMBEDDING_MODEL` → `text-embedding-multilingual-e5-large-instruct`.
- `.env.example`: привести к remote-конфигу (эмбеддер + LLM), убрать `QDRANT_*`.
- Убрать мёртвые `QDRANT_HOST`/`QDRANT_PORT` из `.env`, `.env.example`, `backend/.env`.
- Удалить осиротевший `infra/qdrant/` (в т.ч. `.env` со старым `LLM_MODEL=google/gemma-3-12b`).
- `infra/fly/qdrant/` — не удаляем (follow-up: прод cut-over не подтверждён).
- `backend/src/migrate.py` — не трогаем (untracked, часть незакоммиченной миграции; решение отдельно).
- Обновить доки (`AGENTS.md`, `README.md`, `memory.md`): имена моделей + убрать упоминания Qdrant.

## Capabilities

### New Capabilities

<!-- нет: изменения только конфиг/доки/чистка, поведение не меняется -->

### Modified Capabilities

<!-- нет: spec-level поведение не меняется, remote API path уже существует в коде -->

Поведение системы не меняется — только конфигурация и чистка. Изменение помечено `skip_specs: true`.

## Impact

- Код: `backend/src/config.py` (дефолт модели).
- Конфиги: `.env`, `.env.example`, `backend/.env`, удаление `infra/qdrant/`.
- Доки: `AGENTS.md`, `README.md`, `memory.md`.
- Зависимости: без изменений (`qdrant-client` уже удалён; `migrate.py` — единственный оставшийся импорт).
- Поведение поиска/индексации/выдачи не меняется.
