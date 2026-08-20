## 1. Spike (ArcadeDB viability)

- [x] 1.1 Поднять `arcadedata/arcadedb`, проверить Bolt-хендшейк (`verify_connectivity`); при несовместимости Bolt 5.x — закрепить `neo4j>=5,<6`
- [x] 1.2 Проверить openCypher MERGE/MATCH/count/ORDER/LIMIT на текущих запросах
- [x] 1.3 Проверить `vector.neighbors` — доступен ли из openCypher (bridge) или только SQL; подтвердить COSINE + 1024-dim
- [x] 1.4 Проверить композитный UNIQUE index `Entity (name, type)`; при отказе — single-property index + дедуп в приложении

## 2. Infra

- [x] 2.1 Добавить сервис `arcadedb` в `infra/compose.yml` (порты 7687/2480, volume данных, healthcheck, `defaultDatabases=litrag[...]`)
- [x] 2.2 Синхронизировать `infra/compose.gpu.yml`
- [x] 2.3 Добавить `ARCADEDB_*` env (вкл. `ARCADEDB_DATABASE=litrag`) в `infra/app/.env` и `.env.example`; убрать `NEO4J_*`
- [x] 2.4 Добавить `ARCADEDB_URI/HTTP_URL/DATABASE/USER/PASSWORD` в `backend/src/config.py`
- [x] 2.5 Обновить `api`/`worker`/`mcp` в compose: `depends_on: arcadedb`, убрать `env_file: ./qdrant/.env`

## 3. Graph store

- [x] 3.1 Переписать `store/graph.py`: `ArcadeDBGraphStore` (Bolt/neo4j драйвер, `session(database="litrag")`), `_init_schema` через UNIQUE indexes
- [x] 3.2 Маппинг запросов: `add_paper`, `get_related_ids`, `get_papers_by_ids`, `get_edges`, `get_all_paper_ids`, `is_healthy`
- [x] 3.3 Удалить `MockStore` и fallback-ветку в `get_graph_store`

## 4. Vector store

- [x] 4.1 Переписать `store/vector.py`: `ArcadeDBVectorStore` (index, search через `vector.neighbors` по HTTP к базе `litrag`, `is_healthy`)
- [x] 4.2 Реализовать расчёт `related_ids` (top-6 без себя) при индексации
- [x] 4.3 Обновить `store/core.py`: убрать MockStore-ветки
- [x] 4.4 Обновить `mcp_server.py` `get_paper`: Cypher/HTTP вместо Qdrant scroll

## 5. Worker / pipeline

- [x] 5.1 Обновить `worker.py`: всегда извлекать сущности (убрать `isinstance(graph, MockStore)`), `add_paper` в новый store

## 6. Migration-скрипт

- [x] 6.1 Экспорт Qdrant (scroll всех точек) → upsert `Paper` (metadata + embedding)
- [x] 6.2 Экспорт Neo4j (сущности + USES) → upsert `Entity` + рёбра
- [x] 6.3 Идемпотентность (MERGE) + контрольные счётчики papers/entities/edges до и после

## 7. Cut-over и очистка

- [x] 7.1 Переключить env на ArcadeDB, проверить `/search`, `/graph`, MCP `get_paper`, health
- [x] 7.2 Удалить сервис `qdrant` из compose, поправить `Makefile` (target `qdrant`) и `start-dockers.sh`; `infra/fly/qdrant/*` — follow-up после prod cut-over
- [x] 7.3 Убрать `qdrant-client` из `backend/pyproject.toml`; если spike 1.1 показал несовместимость Bolt 5.x — закрепить `neo4j>=5,<6`

## 8. Тесты

- [x] 8.1 Обновить тесты (`test_worker` и др.), замокать новые store-классы
- [x] 8.2 Добавить store-level тесты (интеграционные при наличии контейнера; иначе моки)
- [x] 8.3 Прогнать весь test suite (`uv run poe test`)
