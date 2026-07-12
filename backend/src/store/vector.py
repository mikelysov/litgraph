import os
import uuid
from typing import Callable, Protocol

import numpy as np
from dotenv import load_dotenv
from loguru import logger
from numpy.typing import NDArray
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, ScoredPoint, VectorParams

from src.config import EMBEDDING_DIM
from src.models import Paper, SearchResult

load_dotenv()

COLLECTION_NAME = "papers"
VECTOR_DIM = EMBEDDING_DIM

host = os.getenv("QDRANT_HOST", "localhost")
port = int(os.getenv("QDRANT_PORT", 6333))


class VectorStore(Protocol):
    def index(self, papers: list[Paper], vectors: NDArray[np.float32]) -> None: ...

    def search(self, query_vector: NDArray[np.float32], top_k: int = 5) -> list[SearchResult]: ...

    def is_healthy(self) -> bool: ...


class QdrantVectorStore(VectorStore):
    def __init__(self, host: str = host, port: int = port):
        self.client = QdrantClient(host=host, port=port, check_compatibility=False)
        self.is_healthy()

    def ensure_collection(self) -> None:
        """
        Ensure the collection exists with correct vector dimension.
        Recreates if dimension doesn't match EMBEDDING_DIM.
        """
        existing: list[str] = [
            c.name for c in self.client.get_collections().collections
        ]
        logger.info(
            f"Existing Qdrant collections: {[c.name for c in self.client.get_collections().collections]}"
        )
        if COLLECTION_NAME in existing:
            info = self.client.get_collection(COLLECTION_NAME)
            current_dim = info.config.params.vectors.size
            if current_dim != VECTOR_DIM:
                logger.warning(
                    f"Collection '{COLLECTION_NAME}' dim {current_dim} != expected {VECTOR_DIM}. "
                    "Recreating..."
                )
                self.client.delete_collection(COLLECTION_NAME)
                existing.remove(COLLECTION_NAME)
        if COLLECTION_NAME not in existing:
            logger.info(f"Creating collection '{COLLECTION_NAME}' (dim={VECTOR_DIM})...")
            self.client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            logger.success(f"Collection '{COLLECTION_NAME}' created.")

    def _to_point_id(self, paper_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, paper_id))

    def index(self, papers: list[Paper], vectors: NDArray[np.float32]) -> None:
        """
        Index the papers and their corresponding vectors into Qdrant.
        """
        # Ensure the collection exists
        self.ensure_collection()

        points: list[PointStruct] = []
        for _, (paper, vector) in enumerate(zip(papers, vectors)):
            points.append(
                PointStruct(
                    id=self._to_point_id(paper.id),
                    vector=vector.flatten().tolist(),
                    payload={
                        "id": paper.id,
                        "title": paper.title,
                        "authors": paper.authors,
                        "abstract": paper.abstract[:10000],
                    },
                )
            )
        logger.info(f"Indexing {len(papers)} papers into Qdrant...")
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.success(f"Successfully upserted {len(points)} points into '{COLLECTION_NAME}'")
        count = self.client.count(COLLECTION_NAME, exact=True).count
        logger.debug(f"Collection now contains {count} vectors")

        # Compute and store related_ids for each newly indexed paper
        TOP_K = 5
        updates: list[PointStruct] = []
        for _, (paper, vector) in enumerate(zip(papers, vectors)):
            point_id = self._to_point_id(paper.id)
            neighbors = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector.flatten().tolist(),
                limit=TOP_K + 1,
                with_payload=True,
            ).points

            related = []
            for n in neighbors:
                if n.id == point_id:
                    continue
                nid = (n.payload or {}).get("id", "")
                if nid and len(related) < TOP_K:
                    related.append(nid)

            if related:
                payload = {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract": paper.abstract[:10000],
                    "related_ids": related,
                }
                updates.append(
                    PointStruct(id=point_id, vector=vector.flatten().tolist(), payload=payload)
                )

        if updates:
            self.client.upsert(collection_name=COLLECTION_NAME, points=updates)
            logger.debug(f"Updated related_ids for {len(updates)} papers")

    def search(self, query_vector: NDArray[np.float32], top_k: int = 5) -> list[SearchResult]:
        self.ensure_collection()
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector[0].tolist(),
            limit=top_k,
        ).points
        logger.info(f"Searching Qdrant for top {top_k} matches...")
        return [
            SearchResult(
                id=(point.payload or {}).get("id", str(point.id)),
                title=(point.payload or {}).get("title", ""),
                authors=(point.payload or {}).get("authors", []),
                abstract=(point.payload or {}).get("abstract", ""),
                score=point.score,
                related_ids=(point.payload or {}).get("related_ids", []),
            )
            for point in results
        ]

    def is_healthy(self) -> bool:
        """
        Check if the Qdrant instance is healthy.
        """
        try:
            self.client.get_collections()
            logger.info("Qdrant is healthy.")
            return True
        except Exception as e:
            logger.error(f"Qdrant is not healthy: {e}")
            return False


VECTOR_STORE: dict[str, Callable[[], VectorStore]] = {
    "qdrant": QdrantVectorStore,
}


def get_vector_store(backend: str = "qdrant") -> VectorStore:
    """
    Get the vector store instance based on the backend specified.
    """
    if backend not in VECTOR_STORE:
        raise ValueError(f"Unsupported vector store backend: {backend}")
    return VECTOR_STORE[backend]()
