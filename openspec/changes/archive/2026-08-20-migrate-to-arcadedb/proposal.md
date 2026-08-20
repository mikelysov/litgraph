## Why

Litgraph сегодня держит данные в двух базах: Qdrant (векторы + метаданные + `related_ids`) и Neo4j (граф: Paper/Entity/USES). Два сервиса = двойной ops, двойная миграция, невозможность склеить векторный и графовый поиск в одном запросе. ArcadeDB закрывает оба: граф + документ + вектор + fulltext в одной базе, Bolt-совместим (переиспользуем `neo4j` драйвер), disk-persistent LSM-Tree, Apache-2.0.

## What Changes

- **BREAKING**: удаляем Qdrant как хранилище векторов и метаданных.
- **BREAKING**: удаляем Neo4j как графовое хранилище.
- Единое хранилище ArcadeDB: `Paper` (метаданные + embedding + related_ids) + `Entity` + ребро `USES`.
- `VectorStore`-бэкенд переписан на ArcadeDB vector index (`vector.neighbors`, COSINE).
- `GraphStore`-бэкенд переписан на ArcadeDB openCypher через существующий `neo4j` драйвер (Bolt).
- Убирается fallback-паттерн `MockStore` / отдельный `VECTOR_STORE`-реестр: ArcadeDB обязателен. При его недоступности сервис unhealthy и операции падают — тихого деградейда больше нет.
- `get_paper` (MCP) переходит с Qdrant HTTP scroll на Cypher `MATCH`.
- infra: убираем сервисы `qdrant` (compose + `infra/fly/qdrant`), добавляем `arcadedb`; обновляем env (`NEO4J_*` → ArcadeDB, `QDRANT_*` → ArcadeDB).
- Единый data-migration скрипт: Qdrant scroll + Neo4j export → ArcadeDB.

## Capabilities

### New Capabilities

- `graph-store`: персистентность графа (Paper/Entity/USES), связанные статьи по пересечению сущностей, рёбра для визуализации.
- `vector-store`: индексация эмбеддингов, поиск ближайших соседей (COSINE), вычисление `related_ids`.

### Modified Capabilities

<!-- нет существующих spec в openspec/specs/ -->

## Impact

- Код: `backend/src/store/vector.py`, `backend/src/store/graph.py`, `backend/src/store/core.py`, `backend/src/store/__init__.py`, `backend/src/mcp_server.py`, `backend/src/config.py`, `backend/src/worker.py` (паттерн MockStore), `backend/pyproject.toml` (зависимости).
- Infra: `infra/compose.yml`, `infra/compose.gpu.yml`, `infra/app/.env(.example)`, `infra/qdrant/.env`, `infra/fly/qdrant/*` (удаление).
- Зависимости: `qdrant-client` уходит; `neo4j` остаётся (граф по Bolt); векторный поиск — HTTP API ArcadeDB через `httpx` (отдельный `arcadedb` client не нужен).
- Данные: нужен экспорт из обоих источников (абстракт только в Qdrant, сущности только в Neo4j).
- Поведение поиска и выдачи не меняется (требования в spec фиксируют текущее поведение).
