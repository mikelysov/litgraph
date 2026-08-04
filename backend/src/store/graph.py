from typing import Protocol

from loguru import logger
from neo4j import GraphDatabase

from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from src.models import Paper, SearchResult


class GraphStore(Protocol):
    def get_related_ids(self, paper_id: str) -> list[str]: ...

    def get_papers_by_ids(self, ids: list[str]) -> list[SearchResult]: ...

    def is_healthy(self) -> bool: ...


class MockStore(GraphStore):
    def get_related_ids(self, paper_id: str) -> list[str]:
        return []

    def get_papers_by_ids(self, ids: list[str]) -> list[SearchResult]:
        return []

    def is_healthy(self) -> bool:
        return True


class Neo4jGraphStore:
    """Neo4j-backed graph store.

    Node model:
        (:Paper {id, title, authors})        — paper node
        (:Entity {name, type})               — method / dataset / task / model
    Edge:
        (:Paper)-[:USES {role}]->(:Entity)   — paper references entity
    """

    ENTITY_TYPES = ("methods", "datasets", "tasks", "models")
    ROLE_ALIAS = {
        "methods": "method",
        "datasets": "dataset",
        "tasks": "task",
        "models": "model",
    }

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Connected to Neo4j at {uri}")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT paper_id IF NOT EXISTS "
                "FOR (p:Paper) REQUIRE p.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE (e.name, e.type) IS UNIQUE"
            )

    def add_paper(self, paper: Paper, entities: dict[str, list[str]]) -> None:
        """Upsert paper node and link it to entity nodes."""
        authors = ", ".join(paper.authors)
        with self._driver.session() as session:
            session.run(
                """
                MERGE (p:Paper {id: $id})
                SET p.title = $title, p.authors = $authors
                """,
                id=paper.id,
                title=paper.title,
                authors=authors,
            )
            for field in self.ENTITY_TYPES:
                role = self.ROLE_ALIAS[field]
                for name in entities.get(field, []) or []:
                    name = str(name).strip()
                    if not name:
                        continue
                    session.run(
                        """
                        MERGE (e:Entity {name: $name, type: $role})
                        WITH e
                        MATCH (p:Paper {id: $id})
                        MERGE (p)-[:USES {role: $role}]->(e)
                        """,
                        name=name,
                        role=role,
                        id=paper.id,
                    )

    def get_related_ids(self, paper_id: str, limit: int = 10) -> list[str]:
        """Return paper IDs sharing entities with the given paper, ranked by overlap."""
        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (p:Paper {id: $id})-[:USES]->(e:Entity)<-[:USES]-(other:Paper)
                WHERE other.id <> $id
                RETURN other.id AS id, count(*) AS overlap
                ORDER BY overlap DESC
                LIMIT $limit
                """,
                id=paper_id,
                limit=limit,
            )
            return [r["id"] for r in records]

    def get_papers_by_ids(self, ids: list[str]) -> list[SearchResult]:
        if not ids:
            return []
        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (p:Paper) WHERE p.id IN $ids
                RETURN p.id AS id, p.title AS title, p.authors AS authors
                """,
                ids=ids,
            )
            results = []
            for r in records:
                results.append(
                    SearchResult(
                        id=r["id"],
                        title=r["title"] or "",
                        authors=(r["authors"] or "").split(", ") if r["authors"] else [],
                    )
                )
            return results

    def get_edges(self, paper_ids: list[str], limit: int = 50) -> list[tuple[str, str, float]]:
        """Return (source, target, weight) edges between papers sharing entities.

        Weight = number of shared entities.
        """
        if not paper_ids:
            return []
        with self._driver.session() as session:
            records = session.run(
                """
                MATCH (a:Paper)-[:USES]->(e:Entity)<-[:USES]-(b:Paper)
                WHERE a.id IN $ids AND b.id IN $ids AND a.id < b.id
                RETURN a.id AS source, b.id AS target, count(e) AS weight
                ORDER BY weight DESC
                LIMIT $limit
                """,
                ids=paper_ids,
                limit=limit,
            )
            return [(r["source"], r["target"], float(r["weight"])) for r in records]

    def get_all_paper_ids(self) -> set[str]:
        """Return the set of all paper IDs present in the graph."""
        with self._driver.session() as session:
            records = session.run("MATCH (p:Paper) RETURN p.id AS id")
            return {r["id"] for r in records}

    def is_healthy(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"Neo4j health check failed: {e}")
            return False

    def close(self) -> None:
        self._driver.close()


def get_graph_store() -> GraphStore:
    if NEO4J_URI and NEO4J_PASSWORD:
        try:
            return Neo4jGraphStore(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
    return MockStore()
