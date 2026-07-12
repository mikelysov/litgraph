import os

import numpy as np
import httpx
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_API_URL, EMBEDDING_MODEL
from src.models import Paper

_local_model: SentenceTransformer | None = None


def _get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _remote_embed(texts: list[str]) -> NDArray[np.float32]:
    response = httpx.post(
        f"{EMBEDDING_API_URL}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    embeddings = [item["embedding"] for item in data["data"]]
    return np.array(embeddings, dtype=np.float32)


def _local_embed(texts: list[str]) -> NDArray[np.float32]:
    global _local_model
    if _local_model is None:
        model_path = os.path.expanduser(os.getenv("EMBEDDING_MODEL_PATH", "all-MiniLM-L6-v2"))
        device = _get_device()
        _local_model = SentenceTransformer(model_path, device=device)
    return _local_model.encode(texts, convert_to_numpy=True).astype(np.float32)


def preload() -> None:
    """Preload embedder model into memory."""
    if not EMBEDDING_API_URL:
        _local_embed(["warmup"])


def embed_papers(papers: list[Paper]) -> NDArray[np.float32]:
    texts = [paper.abstract for paper in papers]
    if EMBEDDING_API_URL:
        return _remote_embed(texts)
    return _local_embed(texts)


def embed_query(query: str) -> NDArray[np.float32]:
    if EMBEDDING_API_URL:
        return _remote_embed([query])
    return _local_embed([query])
