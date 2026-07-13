from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from src.llm import generate_rag_answer, rerank
from src.models import (
    IngestEvent,
    Paper,
    PaperNode,
    PaperState,
    GraphData,
    SearchResponse,
)
from src.pipeline import run_pipeline
from src.queuing import enqueue_papers
from src.store import get_paper_index, health_check
from src.store.core import search as vector_search

router = APIRouter()


@router.post("/ingest")
def ingest(body: Paper) -> list[dict]:
    logger.info(f"Ingesting paper {body.id}: {body.title[:60]}...")
    states = enqueue_papers([body])
    return [s.model_dump() for s in states]


@router.get("/pipeline", response_model=list[IngestEvent])
def pipeline(query: str) -> list[IngestEvent]:
    """
    Run the pipeline with the given query and return a list of IngestEvent objects.
    """
    return list(run_pipeline(query))


@router.get("/health")
def health():
    ok: dict[str, bool] = health_check()
    if not all(ok.values()):
        raise HTTPException(status_code=503, detail="One or more components are unhealthy")
    return ok


@router.get("/status")
def status(paper_id: list[str] = Query(...)) -> list[dict[str, str | bool]]:
    """
    Return the status of one or more papers from the PaperIndex.
    """
    index = get_paper_index()
    results: list[dict[str, str | bool]] = []

    for pid in paper_id:
        state: PaperState | None = index.get(pid)
        if not state:
            results.append({"id": pid, "status": "NOT_FOUND", "in_graph": False})
        else:
            results.append(
                {
                    "id": state.id,
                    "status": state.status.value,
                    "in_graph": state.in_graph,
                }
            )

    return results


@router.get("/search", response_model=SearchResponse)
def search(query: str = Query(..., min_length=1)):
    logger.debug(f"Received search query: {query}")
    results = vector_search(query, expand_hops=1)
    nodes = [
        PaperNode(
            id=r.id,
            title=r.title,
            authors=r.authors,
            score=r.score,
            related_ids=r.related_ids,
        )
        for r in results
    ]
    all_ids = {n.id for n in nodes}
    for n in nodes:
        if n.related_ids:
            all_ids.update(n.related_ids)
    graph_nodes = [
        PaperNode(id=pid, title="", authors=[])
        for pid in all_ids
    ]
    return SearchResponse(
        results=nodes,
        graph=GraphData(nodes=graph_nodes, edges=[]),
    )


@router.get("/ask")
def ask(query: str = Query(..., min_length=1), top_k: int = Query(5)):
    logger.info(f"Ask: {query[:80]}")
    raw_results = vector_search(query)
    context = [
        {"id": r.id, "title": r.title, "abstract": r.abstract}
        for r in raw_results[:20]
    ]
    if not context:
        return {"answer": "No relevant papers found.", "sources": [], "confidence": "low"}

    context = rerank(query, context, top_k=top_k)
    answer = generate_rag_answer(query, context)

    raw_sources = answer.get("sources", [])
    if raw_sources and isinstance(raw_sources[0], (int, float)):
        answer["sources"] = [
            {"id": context[idx]["id"], "title": context[idx]["title"]}
            for s in raw_sources
            if isinstance(s, (int, float))
            for idx in ([int(s) - 1] if int(s) > 0 else [int(s)])
            if 0 <= idx < len(context)
        ]
    return answer
