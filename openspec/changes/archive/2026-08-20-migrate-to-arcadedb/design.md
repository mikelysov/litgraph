## Context

Сегодня два хранилища (см. proposal.md):

- **Qdrant** (`backend/src/store/vector.py`): collection `papers`, COSINE, dim 1024. Payload = id/title/authors/abstract. При индексации считается kNN top-5 → `related_ids` в payload. `mcp_server.py` ходит в Qdrant HTTP напрямую (`scroll`).
- **Neo4j** (`backend/src/store/graph.py`): `(:Paper)-[:USES {role}]->(:Entity)`, сущности из LLM-экстракции. Вне compose (ручной контейнер), host-gateway IP в `.env.example`. Fallback `MockStore` при отсутствии конфига.

Ограничения: эмбеддинги 1024-dim, драйвер `neo4j>=5.0.0` (lock 6.2.0), `paper_index.db` (SQLite) и Redis **не трогаем**, сущности живут только в Neo4j, абстракт — только в Qdrant.

## Goals / Non-Goals

**Goals:**
- Одна база ArcadeDB: граф + вектор + метаданные.
- Поведение поиска/выдачи без изменений (см. specs/).
- Переиспользовать `neo4j` драйвер через Bolt для графа.
- Один идемпотентный migration-скрипт (Qdrant + Neo4j → ArcadeDB).
- Убрать qdrant/neo4j из compose и `infra/fly/qdrant`.

**Non-Goals:**
- Гибридный ранжинг через `vector.fuse` (будущее, не в этом change).
- Замена Redis / `paper_index.db` / reranker / LLM.
- ArcadeDB document/key-value/time-series сверх Paper-метаданных.
- HA/репликация ArcadeDB.

## Decisions

### D1: ArcadeDB вместо Memgraph
ArcadeDB: disk-persistent LSM-Tree (нет окна потери как у in-memory снапшотов Memgraph), `EXTERNAL` embedding property (traversal не пейджит вектора), INT8 quantization, `vector.fuse` на будущее, Apache-2.0, Bolt (v26.2.1+). Альтернатива Memgraph отклонена: RAM-bound + снапшоты.

### D2: Транспорт — Bolt (neo4j драйвер) для графа, HTTP SQL для вектора и DDL
- Граф: существующий `neo4j` драйвер, openCypher строки почти без изменений (MERGE/MATCH/count — в 97.8% TCK). `verify_connectivity()` работает через Bolt.
- **Spike подтвердил**: Bolt 5.x работает с драйвером 6.2.0 → pin `neo4j>=5,<6` не нужен.
- Вектор: `vector.neighbors('Paper[embedding]', $q, k)` — **только SQL**, из openCypher недоступен → идёт через HTTP API (`POST /api/v1/command/<db>`, `language: sql`) через `httpx`.
- **DDL тоже SQL**: openCypher не умеет `CREATE VERTEX TYPE`/`CREATE INDEX`/`CREATE CONSTRAINT` → `_init_schema` идёт через HTTP SQL (`ensure_schema()` в `store/arcadedb.py`).
- Альтернатива: `arcadedb` Python client на всё — отклонён (больше churn в `graph.py`).

### D3: Схема и маппинг

```
CREATE VERTEX TYPE Paper;
CREATE PROPERTY Paper.id STRING;
CREATE PROPERTY Paper.title STRING;
CREATE PROPERTY Paper.authors LIST;
CREATE PROPERTY Paper.abstract STRING;
CREATE PROPERTY Paper.embedding ARRAY_OF_FLOATS;
CREATE PROPERTY Paper.related_ids LIST;

CREATE VERTEX TYPE Entity;
CREATE PROPERTY Entity.name STRING;
CREATE PROPERTY Entity.type STRING;

CREATE EDGE TYPE USES;
CREATE PROPERTY USES.role STRING;

CREATE INDEX ON Paper (id) UNIQUE;
CREATE INDEX ON Entity (name, type) UNIQUE;   -- композитный UNIQUE — работает
CREATE INDEX ON Paper (embedding) LSM_VECTOR METADATA {dimensions: 1024, similarity: 'COSINE'};
```

Маппинг запросов:
- `MERGE (p:Paper {id}) SET ...` → openCypher MERGE (идемпотентно через UNIQUE index). Метаданные (id/title/authors/abstract) — по Bolt.
- `MERGE (e:Entity {name,type})` → MERGE + композитный UNIQUE (работает, проверено).
- `get_related_ids` / `get_edges` / `get_all_paper_ids` / `get_papers_by_ids` → те же openCypher строки.
- `authors` хранится как `LIST` (не строка) → `get_papers_by_ids` возвращает список напрямую.
- **embedding (`ARRAY_OF_FLOATS`) задаётся только SQL `UPDATE`**: Bolt `SET embedding=[...]` шлёт generic `LIST` → попытка смены типа индексированного свойства → `not allowed to update schema`.
- `vector.neighbors` возвращает записи с полем `distance` (COSINE: 0 = идентично) → `score = 1 - distance`.
- `related_ids` = top-(k+1) соседей без себя, сохраняется SQL `UPDATE` (LIST).
- Два разных `related`-механизма не путать: `Paper.related_ids` (векторный kNN, сохраняется при индексации) vs графовый overlap (вычисляется в `get_related_ids` запросом по `USES`, нигде не хранится).

### D4: Конфигурация
`NEO4J_URI/USER/PASSWORD` и `QDRANT_HOST/PORT` → `ARCADEDB_URI` (bolt://), `ARCADEDB_HTTP_URL`, `ARCADEDB_DATABASE` (`litrag`), `ARCADEDB_USER`, `ARCADEDB_PASSWORD`. `EMBEDDING_DIM` остаётся. `config.py` держит всё.

Выбор базы: Bolt-сессии `session(database="litrag")`, HTTP-пути `<host>:2480/api/v1/command/<db>`. Provisioning в compose — `arcadedb.server.defaultDatabases=litrag[]` (**пустые скобки**: `litrag[root:pass]` вызывает `root.addDatabase(db, [null])` и роняет права root на schema; пустые скобки только создают БД). Конфиг передавать через `-e` env (`environment:` в compose), НЕ через `JAVA_OPTS -D` — иначе root теряет права schema.

### D5: Убираем fallback-паттерн
ArcadeDB обязателен. `MockStore` удаляется; `worker.py` перестаёт пропускать LLM-экстракцию (`isinstance(graph, MockStore)`), `core.py`/`api.py` — ветки MockStore. При недоступности ArcadeDB — health = unhealthy, search/ingest падают с ошибкой; тихого деградейда нет.

## Risks / Trade-offs

- **Bolt-версия** → снято spike'ом: Bolt v5.0–5.4 поддерживается, драйвер 6.2.0 работает, pin не нужен.
- **Композитный UNIQUE index `(name,type)`** → снято: работает.
- **`vector.neighbors` только в SQL** → подтверждено; HTTP SQL-путь (httpx) в `store/arcadedb.py`.
- **Точка отказа** (нет MockStore) → health-check + документация; degraded-режим — вне scope.
- **JVM footprint** → буферный кэш ArcadeDB, `EXTERNAL` embedding снижает пейджинг; RAM подбирать по масштабу.
- **Миграция двух источников** → скрипт с контрольными счётчиками (papers/entities/edges до и после), идемпотентный (MERGE).

## Migration Plan

1. Spike: поднять `arcadedata/arcadedb`, проверить Bolt + `vector.neighbors` (Cypher vs SQL) + композитный UNIQUE.
2. Добавить `arcadedb` сервис в `compose.yml` (+ `compose.gpu.yml`), env-файлы.
3. Реализовать `ArcadeDBGraphStore` (graph.py) и `ArcadeDBVectorStore` (vector.py), убрать MockStore-ветки.
4. Migration-скрипт: Qdrant scroll (все точки) + Neo4j export (сущности/рёбра) → ArcadeDB (MERGE).
5. Cut-over: переключить env на ArcadeDB, проверить `/search`, `/graph`, MCP `get_paper`, health.
6. Удалить `qdrant` из compose, `infra/fly/qdrant/*`, зависимости `qdrant-client`.
7. Rollback: держать qdrant/neo4j контейнеры до верификации; откат = вернуть env.

## Open Questions

- Деплой ArcadeDB на Fly/Cloud (prod) — отложено; сейчас local compose. `infra/fly/qdrant` удаляется follow-up'ом после prod cut-over, не в этом change.
- `related_ids` хранить как property vs считать на лету — оставляем как property (паритет с текущим поведением).
