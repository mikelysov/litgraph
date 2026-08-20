"""One-time migration: Qdrant (vectors + metadata) + Neo4j (entities) → ArcadeDB.

Run BEFORE removing qdrant-client / the old containers:
    cd backend && uv run python -m src.migrate

Requires the legacy services to be reachable:
    QDRANT_HOST / QDRANT_PORT   (default localhost:6333)
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD   (default bolt://localhost:7687)
ArcadeDB connection comes from ARCADEDB_* (see src/config.py).
"""

import json
import os

from loguru import logger
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from src.config import ARCADEDB_DATABASE
from src.store.arcadedb import ensure_schema, get_driver, sql, sql_quote

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "papers")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def _arcade_count(query: str) -> int:
    with get_driver().session(database=ARCADEDB_DATABASE) as s:
        return s.run(query).single()[0]


def migrate_qdrant() -> int:
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, check_compatibility=False)
    total = client.count(QDRANT_COLLECTION, exact=True).count
    logger.info(f"Qdrant papers to migrate: {total}")

    points, offset = [], None
    while True:
        batch, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=200,
            with_vectors=True,
            with_payload=True,
            offset=offset,
        )
        points.extend(batch)
        if offset is None:
            break

    with get_driver().session(database=ARCADEDB_DATABASE) as session:
        for pt in points:
            payload = pt.payload or {}
            pid = payload.get("id", str(pt.id))
            session.run(
                "MERGE (p:Paper {id: $id}) "
                "SET p.title = $title, p.authors = $authors, p.abstract = $abstract",
                id=pid,
                title=payload.get("title", ""),
                authors=payload.get("authors", []) or [],
                abstract=payload.get("abstract", ""),
            )
            vec = pt.vector
            if vec:
                sql(f"UPDATE Paper SET embedding = {json.dumps(list(vec))} WHERE id = {sql_quote(pid)}")
            rel = payload.get("related_ids") or []
            if rel:
                sql(f"UPDATE Paper SET related_ids = {json.dumps(list(rel))} WHERE id = {sql_quote(pid)}")

    logger.info(f"Migrated {len(points)} papers from Qdrant")
    return total


def migrate_neo4j() -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as s:
            rows = list(
                s.run(
                    "MATCH (p:Paper)-[r:USES]->(e:Entity) "
                    "RETURN p.id AS paper, r.role AS role, e.name AS name"
                )
            )
    finally:
        driver.close()

    with get_driver().session(database=ARCADEDB_DATABASE) as session:
        for r in rows:
            session.run(
                """
                MERGE (e:Entity {name: $name, type: $role})
                WITH e
                MATCH (p:Paper {id: $id})
                MERGE (p)-[:USES {role: $role}]->(e)
                """,
                name=r["name"],
                role=r["role"],
                id=r["paper"],
            )

    logger.info(f"Migrated {len(rows)} USES edges from Neo4j")
    return len(rows)


def main() -> None:
    ensure_schema()
    qdrant_total = migrate_qdrant()
    neo4j_edges = migrate_neo4j()

    papers = _arcade_count("MATCH (p:Paper) RETURN count(p)")
    entities = _arcade_count("MATCH (e:Entity) RETURN count(e)")
    edges = _arcade_count("MATCH ()-[r:USES]->() RETURN count(r)")

    logger.info(f"ArcadeDB after migration: papers={papers}, entities={entities}, edges={edges}")
    print(
        f"Qdrant papers migrated: {qdrant_total}\n"
        f"Neo4j edges migrated:   {neo4j_edges}\n"
        f"ArcadeDB now: papers={papers}, entities={entities}, edges={edges}"
    )


if __name__ == "__main__":
    main()
