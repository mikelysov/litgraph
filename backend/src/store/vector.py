import json
from typing import Protocol

from loguru import logger
from numpy.typing import NDArray

from src.config import ARCADEDB_DATABASE
from src.models import Paper, SearchResult
from src.store.arcadedb import ensure_schema, get_driver, sql, sql_quote

VECTOR_INDEX = "Paper[embedding]"
TOP_K = 5


class VectorStore(Protocol):
    def index(self, papers: list[Paper], vectors: NDArray) -> None: ...

    def search(self, query_vector: NDArray, top_k: int = 5) -> list[SearchResult]: ...

    def is_healthy(self) -> bool: ...


class ArcadeDBVectorStore:
    def __init__(self):
        self._driver = get_driver()
        ensure_schema()

    def index(self, papers: list[Paper], vectors: NDArray) -> None:
        """Upsert paper metadata + embedding, then compute vector-derived related_ids."""
        with self._driver.session(database=ARCADEDB_DATABASE) as session:
            for paper, vector in zip(papers, vectors):
                session.run(
                    "MERGE (p:Paper {id: $id}) "
                    "SET p.title = $title, p.authors = $authors, p.abstract = $abstract",
                    id=paper.id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                )
                # embedding is ARRAY_OF_FLOATS: set via SQL (Bolt sends generic LIST).
                emb = [float(x) for x in vector.flatten()]
                sql(f"UPDATE Paper SET embedding = {json.dumps(emb)} WHERE id = {sql_quote(paper.id)}")

        for paper, vector in zip(papers, vectors):
            emb = [float(x) for x in vector.flatten()]
            related = self._nearest_ids(emb, paper.id)
            if related:
                sql(
                    f"UPDATE Paper SET related_ids = {json.dumps(related)} "
                    f"WHERE id = {sql_quote(paper.id)}"
                )
        logger.info(f"Indexed {len(papers)} papers into ArcadeDB")

    def _nearest_ids(self, emb: list[float], exclude_id: str) -> list[str]:
        rows = sql(f"SELECT vector.neighbors('{VECTOR_INDEX}', {json.dumps(emb)}, {TOP_K + 1}) AS n")
        if not rows or not rows[0].get("n"):
            return []
        out: list[str] = []
        for e in rows[0]["n"]:
            eid = e.get("id")
            if eid and eid != exclude_id and len(out) < TOP_K:
                out.append(eid)
        return out

    def search(self, query_vector: NDArray, top_k: int = 5) -> list[SearchResult]:
        emb = [float(x) for x in query_vector[0]]
        rows = sql(f"SELECT vector.neighbors('{VECTOR_INDEX}', {json.dumps(emb)}, {top_k}) AS n")
        results: list[SearchResult] = []
        for e in (rows[0].get("n") or []) if rows else []:
            results.append(
                SearchResult(
                    id=e.get("id", ""),
                    title=e.get("title", "") or "",
                    authors=e.get("authors", []) or [],
                    abstract=e.get("abstract", "") or "",
                    score=1.0 - float(e.get("distance", 1.0)),
                    related_ids=e.get("related_ids", []) or [],
                )
            )
        return results

    def is_healthy(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning(f"ArcadeDB health check failed: {e}")
            return False


def get_vector_store() -> VectorStore:
    return ArcadeDBVectorStore()
