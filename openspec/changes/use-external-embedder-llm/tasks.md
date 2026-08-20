## 1. Local dev конфиг (remote LLM)

- [x] 1.1 В `backend/.env` добавить `LLM_API_URL=http://172.31.61.121:1234/v1`
- [x] 1.2 В `backend/.env` добавить `LLM_MODEL=qwen3.5-4b@q4_k_xl`
- [x] 1.3 В `backend/.env` закомментировать `LLM_MODEL_PATH=~/colab/llms/gemma-3-4b-it`
- [x] 1.4 В `backend/.env` удалить мёртвые `QDRANT_HOST`/`QDRANT_PORT`

## 2. Дефолты и примеры

- [x] 2.1 В `backend/src/config.py` сменить дефолт `EMBEDDING_MODEL` на `text-embedding-multilingual-e5-large-instruct`
- [x] 2.2 В `.env.example` заменить секцию эмбеддера на remote (`EMBEDDING_API_URL`, `EMBEDDING_MODEL=text-embedding-multilingual-e5-large-instruct`, `EMBEDDING_DIM=1024`)
- [x] 2.3 В `.env.example` добавить секцию LLM (`LLM_API_URL`, `LLM_MODEL=qwen3.5-4b@q4_k_xl`)
- [x] 2.4 В `.env.example` удалить `QDRANT_HOST`/`QDRANT_PORT` и Qdrant-комментарии
- [x] 2.5 В корневом `.env` удалить мёртвые `QDRANT_HOST`/`QDRANT_PORT`

## 3. Удаление Qdrant-хвостов

- [ ] 3.1 Удалить каталог `infra/qdrant/` (`.env` со старым `LLM_MODEL=google/gemma-3-12b` + `.env.example`)
- [ ] 3.2 Убрать Qdrant-упоминания из `.gitignore` / `.dockerignore`, если остались

## 4. Доки

- [x] 4.1 `AGENTS.md`: эмбеддер `text-embedding-multilingual-e5-large-instruct`, LLM `qwen3.5-4b@q4_k_xl`; убрать Qdrant UI / «Vector DB: Qdrant» / строку про `infra/qdrant/.env`
- [x] 4.2 `README.md`: модели (BGE-M3 → e5-large-instruct; Gemma 3 12B → qwen3.5-4b@q4_k_xl), убрать Qdrant-упоминания (UI, архитектурная схема, Vector DB)
- [x] 4.3 `memory.md`: обновить имена моделей и model locations (bge-m3 → e5-large-instruct), убрать Qdrant-порт 6333/6334

## 5. Приёмка

- [x] 5.1 `cd backend && uv run poe server` стартует без ошибок, `llm.preload()` логирует remote LLM
- [x] 5.2 `/ask` отвечает через remote LLM (не падает на локальный Gemma)
- [x] 5.3 `/search` ищет через remote эмбеддер + ArcadeDB (dim 1024 не ломается)
- [x] 5.4 Health endpoint: `vector_store`/`graph` ok
