from src.embedder import embed_query
from src.models import SearchResult
from src.store.graph import get_graph_store, MockStore
from src.store.vector import get_vector_store


def search(query: str, expand_hops: int = 1, top_k: int = 5) -> list[SearchResult]:
    vector = get_vector_store()
    graph = get_graph_store()

    embedding = embed_query(query)
    top_results = vector.search(embedding, top_k=top_k)

    # Skip enrichment if graph is mock (no graph backend configured)
    if isinstance(graph, MockStore):
        return top_results

    # Enrich top results with graph-derived related papers (Qdrant remains source of truth)
    enriched: list[SearchResult] = []
    seen: set[str] = set()
    for r in top_results:
        seen.add(r.id)
        enriched.append(r)
        for hop in range(expand_hops):
            if hop == 0:
                related = graph.get_related_ids(r.id)
                related_meta = {p.id: p for p in graph.get_papers_by_ids(related)}
                for rid in related:
                    if rid in seen:
                        continue
                    seen.add(rid)
                    meta = related_meta.get(rid)
                    enriched.append(
                        SearchResult(
                            id=rid,
                            title=meta.title if meta else "",
                            authors=meta.authors if meta else [],
                            score=0.0,
                            related_ids=[r.id],
                        )
                    )
    return enriched
