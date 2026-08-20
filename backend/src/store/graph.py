from typing import Protocol

from loguru import logger

from src.config import ARCADEDB_DATABASE
from src.models import Paper, SearchResult
from src.store.arcadedb import ensure_schema, get_driver


class GraphStore(Protocol):
    def get_related_ids(self, paper_id: str) -> list[str]: ...

    def get_papers_by_ids(self, ids: list[str]) -> list[SearchResult]: ...

    def is_healthy(self) -> bool: ...


class ArcadeDBGraphStore:
    """ArcadeDB-backed graph store.

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

    def __init__(self):
        self._driver = get_driver()
        ensure_schema()

    def _session(self):
        return self._driver.session(database=ARCADEDB_DATABASE)

    def add_paper(self, paper: Paper, entities: dict[str, list[str]]) -> None:
        """Upsert paper node and link it to entity nodes."""
        with self._session() as session:
            session.run(
                "MERGE (p:Paper {id: $id}) SET p.title = $title, p.authors = $authors",
                id=paper.id,
                title=paper.title,
                authors=paper.authors,
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
        with self._session() as session:
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
        with self._session() as session:
            records = session.run(
                """
                MATCH (p:Paper) WHERE p.id IN $ids
                RETURN p.id AS id, p.title AS title, p.authors AS authors
                """,
                ids=ids,
            )
            return [
                SearchResult(
                    id=r["id"],
                    title=r["title"] or "",
                    authors=r["authors"] or [],
                )
                for r in records
            ]

    def get_edges(self, paper_ids: list[str], limit: int = 50) -> list[tuple[str, str, float]]:
        """Return (source, target, weight) edges between papers sharing entities.

        Weight = number of shared entities.
        """
        if not paper_ids:
            return []
        with self._session() as session:
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
        with self._session() as session:
            records = session.run("MATCH (p:Paper) RETURN p.id AS id")
            return {r["id"] for r in records}

    def is_healthy(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"ArcadeDB health check failed: {e}")
            return False


def get_graph_store() -> GraphStore:
    return ArcadeDBGraphStore()
