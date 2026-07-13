import json
import os
import re

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP
from httpx import Client, HTTPStatusError

load_dotenv()

API_URL = os.getenv("LITGRAPH_API_URL", "http://localhost:8889/api")
_http = Client(base_url=API_URL, timeout=120.0)

mcp = FastMCP("Litgraph")


@mcp.tool()
def search(query: str, top_k: int = 5) -> str:
    resp = _http.get("/search", params={"query": query})
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])[:top_k]
    return "\n".join(
        f"{r['id']}: {r['title']} (score={r['score']:.3f})" for r in results
    )


@mcp.tool()
def ask(query: str, top_k: int = 5) -> str:
    resp = _http.get("/ask", params={"query": query, "top_k": top_k})
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


@mcp.tool()
def ingest_paper(paper_id: str, title: str, authors: list[str], abstract: str) -> str:
    body = {
        "id": paper_id,
        "url": "",
        "title": title,
        "authors": authors,
        "abstract": abstract,
    }
    resp = _http.post("/ingest", json=body)
    resp.raise_for_status()
    return f"Ingested {paper_id}: {title[:60]}... OK"


@mcp.tool()
def ingest_pdf(file_path: str) -> str:
    """Parse PDF, fetch arXiv metadata if ID in filename, index via API."""
    from src.arxiv import fetch_paper_by_id
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
    if arxiv_match:
        logger.info(f"arXiv ID detected: {stem}, fetching metadata...")
        paper = fetch_paper_by_id(stem)
        if paper:
            paper.abstract = f"{paper.abstract}\n\n{pdf_text[:15000]}"
            logger.info(f"Using arXiv metadata for {paper.id}: {paper.title[:60]}")
        else:
            paper = None

    if not paper:
        from src.models import Paper
        paper = Paper(
            id=stem, url="", title=stem, authors=[], abstract=pdf_text[:10000]
        )
        logger.info(f"No arXiv metadata, using filename as ID: {stem}")

    body = {
        "id": paper.id,
        "url": paper.url,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
    }
    resp = _http.post("/ingest", json=body)
    resp.raise_for_status()
    return (
        f"Ingested {paper.id}: {paper.title[:60]}... "
        f"OK, pages={len(reader.pages)}, text_len={len(pdf_text)}"
    )


@mcp.tool()
def health() -> str:
    try:
        resp = _http.get("/health")
        resp.raise_for_status()
        ok = resp.json()
        return "\n".join(f"{k}: {'OK' if v else 'FAIL'}" for k, v in ok.items())
    except Exception as e:
        return f"API unreachable: {e}"


@mcp.tool()
def shutdown() -> str:
    logger.warning("Shutdown requested via MCP tool")
    os._exit(0)
    return "Shutting down..."


def main() -> None:
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.getenv("MCP_PORT", "8888"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
