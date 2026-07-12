from src.embedder import embed_query
from src.models import SearchResult
from src.store.graph import get_graph_store, MockStore
from src.store.vector import get_vector_store


def search(query: str, expand_hops: int = 1) -> list[SearchResult]:
    vector = get_vector_store()
    graph = get_graph_store()

    embedding = embed_query(query)
    top_results = vector.search(embedding)

    # Skip enrichment if graph is mock (no graph backend configured)
    if isinstance(graph, MockStore):
        return top_results

    all_ids = {r.id for r in top_results}
    for r in top_results:
        related = graph.get_related_ids(r.id)
        all_ids.update(related)

    enriched = graph.get_papers_by_ids(list(all_ids))
    return enriched
