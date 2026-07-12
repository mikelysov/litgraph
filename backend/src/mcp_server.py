import json
import os
import re

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP

load_dotenv()

from src.arxiv import fetch_paper_by_id
from src.embedder import embed_papers, preload as preload_embedder
from src.llm import generate_rag_answer
from src.llm import preload as preload_llm
from src.models import Paper
from src.store import health_check
from src.store.core import search as vector_search
from src.store.vector import get_vector_store


def _embed_and_index(paper: Paper) -> None:
    """Embed a single paper and index into Qdrant synchronously."""
    store = get_vector_store()
    vectors = embed_papers([paper])
    store.index([paper], vectors)
    logger.info(f"Indexed {paper.id}: {paper.title[:60]}")


mcp = FastMCP("Litgraph")


@mcp.tool()
def search(query: str, top_k: int = 5) -> str:
    results = vector_search(query)
    return "\n".join(
        f"{r.id}: {r.title} (score={r.score:.3f})" for r in results[:top_k]
    )


def _rerank_if_available(query: str, context: list[dict], top_k: int) -> list[dict]:
    """Rerank via cross-encoder if model is configured, else return top_k as-is."""
    reranker_path = os.getenv("RERANKER_MODEL_PATH", "")
    if not reranker_path:
        return context[:top_k]
    try:
        from src.llm import rerank
        return rerank(query, context, top_k=top_k)
    except Exception as e:
        logger.warning(f"Reranker failed, using raw search: {e}")
        return context[:top_k]


@mcp.tool()
def ask(query: str, top_k: int = 5) -> str:
    """Search papers and generate a structured answer using LLM + reranker."""
    raw_results = vector_search(query)
    context = [
        {"id": r.id, "title": r.title, "abstract": r.abstract}
        for r in raw_results[:20]
    ]
    if not context:
        return json.dumps({
            "answer": "No relevant papers found.",
            "sources": [],
            "confidence": "low",
        }, ensure_ascii=False)

    context = _rerank_if_available(query, context, top_k)

    if not os.getenv("LLM_MODEL_PATH", ""):
        return json.dumps({
            "answer": "LLM not configured — returning raw search results.",
            "sources": [
                {"id": d["id"], "title": d["title"]} for d in context
            ],
            "confidence": "low",
        }, ensure_ascii=False, indent=2)

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
    return json.dumps(answer, ensure_ascii=False, indent=2)


@mcp.tool()
def ingest_paper(paper_id: str, title: str, authors: list[str], abstract: str) -> str:
    paper = Paper(id=paper_id, url="", title=title, authors=authors, abstract=abstract)
    _embed_and_index(paper)
    return f"Ingested {paper_id}: {title[:60]}... OK"


@mcp.tool()
def ingest_pdf(file_path: str) -> str:
    """Parse a PDF file, extract metadata, and index into Qdrant.

    If filename contains an arXiv ID (e.g. '2203.13790.pdf'), fetches
    title/authors/abstract from arXiv API. Otherwise uses filename as ID
    and PDF text as content.

    Args:
        file_path: Absolute path to PDF file on the server filesystem.
    """
    from pypdf import PdfReader

    if not os.path.isfile(file_path):
        return f"Error: file not found: {file_path}"

    basename = os.path.basename(file_path)
    stem = re.sub(r"\.pdf$", "", basename)

    try:
        reader = PdfReader(file_path)
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"Error: failed to parse PDF: {e}"

    if not pdf_text.strip():
        return f"Error: no text extracted from {basename}"

    arxiv_match = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", stem)
    paper = None
    if arxiv_match:
        logger.info(f"arXiv ID detected: {stem}, fetching metadata...")
        paper = fetch_paper_by_id(stem)

    if paper:
        paper.abstract = f"{paper.abstract}\n\n{pdf_text[:15000]}"
        logger.info(f"Using arXiv metadata for {paper.id}: {paper.title[:60]}")
    else:
        paper = Paper(
            id=stem,
            url="",
            title=stem,
            authors=[],
            abstract=pdf_text[:10000],
        )
        logger.info(f"No arXiv metadata, using filename as ID: {stem}")

    _embed_and_index(paper)
    return (
        f"Ingested {paper.id}: {paper.title[:60]}... "
        f"OK, pages={len(reader.pages)}, text_len={len(pdf_text)}"
    )


@mcp.tool()
def health() -> str:
    ok = health_check()
    return "\n".join(f"{k}: {'OK' if v else 'FAIL'}" for k, v in ok.items())


@mcp.tool()
def shutdown() -> str:
    """Stop the MCP server."""
    logger.warning("Shutdown requested via MCP tool")
    import os
    os._exit(0)
    return "Shutting down..."  # never reached


def main() -> None:
    preload_embedder()
    preload_llm()
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.getenv("MCP_PORT", "8888"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
