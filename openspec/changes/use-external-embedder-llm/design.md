## Context

Код уже умеет ходить в remote API для эмбеддера (`EMBEDDING_API_URL`/`EMBEDDING_MODEL`) и LLM (`LLM_API_URL`/`LLM_MODEL`) — `embedder.py` и `llm.py` выбирают remote по непустому `*_API_URL`. Т.е. правки кода-логики не нужны; меняются только env-значения и дефолты.

Текущее рассогласование:

| Файл | Эмбеддер | LLM |
|---|---|---|
| `infra/compose.yml` | ✅ e5-large-instruct | ✅ qwen3.5-4b@q4_k_xl (захардкожено) |
| `infra/app/.env` | ✅ e5-large-instruct | ✅ qwen3.5-4b@q4_k_xl |
| `.env` (корень) | ✅ e5-large-instruct | ✅ qwen3.5-4b@q4_k_xl |
| `backend/.env` (local dev) | ✅ e5-large-instruct | ❌ локальный `LLM_MODEL_PATH`, нет `LLM_API_URL`/`LLM_MODEL` |
| `config.py` (дефолт) | ❌ `text-embedding-qwen3-embedding-4b@q8_0` | ✅ пусто (local) |
| `.env.example` | ❌ bge-m3 (local path) | ❌ секции LLM нет |
| `infra/qdrant/.env` | ✅ e5-large-instruct | ❌ `google/gemma-3-12b` (осиротел) |
| `AGENTS.md`/`README.md`/`memory.md` | ❌ bge-m3 | ❌ qwen3.5-4b / gemma-3-12b |

После миграции на ArcadeDB (архив) остались мёртвые Qdrant-хвосты: `QDRANT_HOST/PORT` в `.env`/`.env.example`/`backend/.env` (никто не читает — `config.py` держит только `ARCADEDB_*`), осиротевшие `infra/qdrant/` и `infra/fly/qdrant/`, broken `backend/src/migrate.py` (импортит `qdrant_client`, которого уже нет в `pyproject.toml`).

## Goals / Non-Goals

**Goals:**
- Один набор env-значений для внешнего эмбеддера + LLM (`http://172.31.61.121:1234/v1`, `text-embedding-multilingual-e5-large-instruct`, `qwen3.5-4b@q4_k_xl`) во всех активных конфигах.
- Local dev (`backend/.env`) снова работает на remote LLM.
- Убрать мёртвые Qdrant-хвосты без изменения поведения.

**Non-Goals:**
- Не трогаем логику `embedder.py`/`llm.py` (remote-ветки уже есть).
- Не трогаем `infra/compose.yml` (значения уже верные; захардкоженное дублирование — вне scope).
- Не меняем reranker (`RERANKER_MODEL_PATH`, локальный) — не относится к change.
- Не трогаем `paper_index.db`/Redis.
- Не добавляем fallback-логику на случай падения внешнего сервиса.

## Decisions

### D1: Меняем только env и дефолты, не код-логику
Remote-ветки в `embedder.py`/`llm.py` уже есть и выбираются по непустому `*_API_URL`. Добавлять новый config-слой или абстракцию — лишнее. Только `backend/.env` (local dev) получает `LLM_API_URL`/`LLM_MODEL`, остальные файлы уже верные.

Альтернатива (захардкодить адрес в `config.py`) — отклонено: инжектить адрес инфраструктуры в код не стоит, env остаётся точкой конфигурации.

### D2: Дефолт `EMBEDDING_MODEL` в `config.py` → `text-embedding-multilingual-e5-large-instruct`
Текущий дефолт `text-embedding-qwen3-embedding-4b@q8_0` устарел. Дефолт работает только в remote-ветке (local `_local_embed` его игнорирует), поэтому правим на актуальную модель. `LLM_MODEL`-дефолт не трогаем: пустая строка = sentinel «local mode», менять семантику не нужно.

### D3: `backend/.env` — remote LLM вместо локального path
`LLM_MODEL_PATH=~/colab/llms/gemma-3-4b-it` закомментировать, добавить `LLM_API_URL` + `LLM_MODEL=qwen3.5-4b@q4_k_xl`. Причина: `load_dotenv()` в `server.py`/`mcp_server.py` грузит `backend/.env`, и сегодня local dev падает на несуществующий локальный Gemma. Оставляем закомментированный `LLM_MODEL_PATH` как документированный путь возврата к local.

### D4: `backend/src/migrate.py` — не удаляем
One-time скрипт (Qdrant+Neo4j → ArcadeDB), миграция выполнена (архив `migrate-to-arcadedb`). Импортит `qdrant_client`, удалённый из `pyproject.toml` → сейчас не запустится. НО: файл **untracked** (часть незакоммиченной миграции), в git-истории его нет — удаление безвозвратно. Не трогаем в этом change; судьбу решить при коммите миграции (commit или удалить после фиксации).

### D5: Удаление `infra/qdrant/`
Осиротел после миграции. Проверено: `compose.yml` использует `env_file: ./app/.env` (не qdrant), `Makefile`/`start-dockers.sh`/`stop-dockers.sh` ссылок на qdrant не имеют. `infra/qdrant/.env` к тому же содержит устаревший `LLM_MODEL=google/gemma-3-12b` — оставлять вредно (вводит в заблуждение). `infra/fly/qdrant/` **не удаляем** — follow-up после подтверждения prod cut-over (см. Open Questions).

### D6: Доки
`AGENTS.md`, `README.md`, `memory.md` — привести имена моделей (bge-m3 → e5-large-instruct; qwen3.5-4b/gemma-3-12b → qwen3.5-4b@q4_k_xl) и убрать Qdrant (UI-адрес, Vector DB, порты, «Qdrant UI → dashboard»). `memory.md` — обновить секцию model locations и порты.

## Risks / Trade-offs

- **Внешний сервис `172.31.61.121:1234` недоступен** → local dev `/ask`/`/search` падают, как уже падает Docker. → Mitigation: закомментированный `LLM_MODEL_PATH`/`EMBEDDING_MODEL_PATH` в env — документированный путь отката на local.
- **Размерность эмбеддера**: e5-large-instruct = 1024-dim, совпадает с `EMBEDDING_DIM=1024` и индексом ArcadeDB. → Mitigation: проверить размерность при приёмке (векторный поиск не ломается).
- **Удаление `infra/qdrant/`** — отслеживается git, откат = `git checkout`. → Mitigation: перед удалением confirm `compose.yml`/скрипты на него не ссылаются (проверено).
- **Расхождение dim при смене модели на будущее** — вне scope.

## Migration Plan

1. Правки env/docs — атомарно, без дата-миграции.
2. Приёмка: `cd backend && uv run poe server`, `/ask` отвечает через remote LLM; `/search` через remote эмбеддер + ArcadeDB; health = ok.
3. Rollback: `git checkout` удалённых файлов / откат env-строк. Данные не трогаются.

## Open Questions

- Прод-выкладка (Fly.io) точно не использует Qdrant? Если ещё использует — `infra/fly/qdrant/` не удалять. Решено: не удаляем сейчас, follow-up после подтверждения prod cut-over.
- `backend/src/migrate.py` — закоммитить как историю или удалить после фиксации миграции? Решено: не в этом change.
