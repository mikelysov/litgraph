"""Store-level integration tests against a live ArcadeDB (skipped if unreachable).

Requires ARCADEDB_* env (or defaults: bolt://localhost:7687, root / no password).
"""

import os

import numpy as np
import pytest

from src.models import Paper
from src.store.graph import ArcadeDBGraphStore
from src.store.vector import ArcadeDBVectorStore


def _arcadedb_reachable() -> bool:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.getenv("ARCADEDB_URI", "bolt://localhost:7687"),
            auth=(os.getenv("ARCADEDB_USER", "root"), os.getenv("ARCADEDB_PASSWORD", "")),
        )
        try:
            driver.verify_connectivity()
            return True
        finally:
            driver.close()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _arcadedb_reachable(),
    reason="ArcadeDB not reachable",
)


def test_index_and_search():
    vs = ArcadeDBVectorStore()
    paper = Paper(id="itest-1", url="", title="ITest", abstract="abs", authors=["a"])
    vs.index([paper], np.random.rand(1, 1024).astype(np.float32))

    results = vs.search(np.random.rand(1, 1024).astype(np.float32), top_k=3)
    assert results
    assert all(r.id and r.title for r in results)
    assert all(r.score is not None for r in results)


def test_graph_add_and_related():
    gs = ArcadeDBGraphStore()
    paper = Paper(id="itest-2", url="", title="ITest2", abstract="", authors=["b"])
    gs.add_paper(paper, {"models": ["BERT-itest"]})

    related = gs.get_related_ids("itest-2")
    assert isinstance(related, list)

    fetched = gs.get_papers_by_ids(["itest-2"])
    assert fetched and fetched[0].id == "itest-2"
    assert fetched[0].authors == ["b"]
