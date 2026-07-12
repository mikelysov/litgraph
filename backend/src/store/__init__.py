from .index import PaperIndex
from .vector import VectorStore, get_vector_store

__all__ = ["get_vector_store", "VectorStore", "health_check", "PaperIndex"]

_paper_index = None


def get_paper_index() -> PaperIndex:
    global _paper_index
    if _paper_index is None:
        _paper_index = PaperIndex()
    return _paper_index


def is_redis_available() -> bool:
    try:
        from .redis import is_redis_healthy
        return is_redis_healthy()
    except Exception:
        return False


def health_check() -> dict[str, bool]:
    """
    Check the health of the paper index and vector store.
    Returns a dictionary with the health status of each component.
    """
    return {
        "paper_index": get_paper_index().is_healthy(),
        "vector_store": get_vector_store().is_healthy(),
        "redis": is_redis_available(),
    }
