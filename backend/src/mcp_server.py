import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from httpx import Client
from loguru import logger
from mcp.server.mcpserver import MCPServer

load_dotenv()

API_URL = os.getenv("LITGRAPH_API_URL", "http://localhost:8889/api")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
INGEST_PDF_ROOT = Path(os.getenv("INGEST_PDF_ROOT", "/docs")).resolve()

_http = Client(base_url=API_URL, timeout=120.0)
_qdrant = Client(base_url=f"http://{QDRANT_HOST}:{QDRANT_PORT}", timeout=30.0)

mcp = MCPServer("Litgraph")


def _api_error(action: str, exc: Exception) -> str:
    return f"Error {action}: {exc}"


def _resolve_pdf_path(file_path: str) -> Path | str:
    """Resolve path and ensure it stays under INGEST_PDF_ROOT."""
    try:
        resolved = Path(file_path).resolve()
    except OSError as e:
        return f"Error: invalid path: {e}"
    try:
        resolved.relative_to(INGEST_PDF_ROOT)
    except ValueError:
        return f"Error: path outside allowed root {INGEST_PDF_ROOT}"
    if not resolved.is_file():
        return f"Error: file not found: {resolved}"
    return resolved


@mcp.tool()
def search(query: str, top_k: int = 5) -> str:
    try:
        resp = _http.get("/search", params={"query": query, "top_k": top_k})
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return "\n".join(
            f"{r['id']}: {r['title']} (score={r['score']:.3f})" for r in results
        )
    except Exception as e:
        return _api_error("search", e)


@mcp.tool()
def ask(query: str, top_k: int = 5) -> str:
    try:
        resp = _http.get("/ask", params={"query": query, "top_k": top_k})
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False, indent=2)
    except Exception as e:
        return _api_error("ask", e)


@mcp.tool()
def ingest_paper(paper_id: str, title: str, authors: list[str], abstract: str) -> str:
    body = {
        "id": paper_id,
        "url": f"https://arxiv.org/abs/{paper_id}" if re.match(r"^\d{4}\.\d{4,5}$", paper_id) else "",
        "title": title,
        "authors": authors,
        "abstract": abstract,
    }
    try:
        resp = _http.post("/ingest", json=body)
        resp.raise_for_status()
        return f"Ingested {paper_id}: {title[:60]}... OK"
    except Exception as e:
        return _api_error("ingest", e)


@mcp.tool()
def ingest_pdf(file_path: str) -> str:
    """Parse PDF under INGEST_PDF_ROOT, fetch arXiv metadata if ID in filename, index via API."""
    from pypdf import PdfReader

    from src.arxiv import fetch_paper_by_id
    from src.models import Paper

    resolved = _resolve_pdf_path(file_path)
    if isinstance(resolved, str):
        return resolved

    basename = resolved.name
    stem = re.sub(r"\.pdf$", "", basename, flags=re.IGNORECASE)

    try:
        reader = PdfReader(str(resolved))
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"Error: failed to parse PDF: {e}"

    if not pdf_text.strip():
        return f"Error: no text extracted from {basename}"

    paper: Paper | None = None
    arxiv_match = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", stem)
    if arxiv_match:
        logger.info(f"arXiv ID detected: {stem}, fetching metadata...")
        paper = fetch_paper_by_id(stem)
        if paper:
            paper.abstract = f"{paper.abstract}\n\n{pdf_text[:15000]}"
            logger.info(f"Using arXiv metadata for {paper.id}: {paper.title[:60]}")

    if paper is None:
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
    try:
        resp = _http.post("/ingest", json=body)
        resp.raise_for_status()
    except Exception as e:
        return _api_error("ingest", e)

    return (
        f"Ingested {paper.id}: {paper.title[:60]}... "
        f"OK, pages={len(reader.pages)}, text_len={len(pdf_text)}"
    )


@mcp.tool()
def get_paper(paper_id: str) -> str:
    """Fetch full paper details (title, authors, abstract) by arXiv ID."""
    try:
        resp = _qdrant.post(
            "/collections/papers/points/scroll",
            json={
                "filter": {"must": [{"key": "id", "match": {"value": paper_id}}]},
                "limit": 1,
                "with_payload": True,
            },
        )
        resp.raise_for_status()
        points = resp.json().get("result", {}).get("points", [])
        if not points:
            return f"Paper {paper_id} not found."
        p = points[0]["payload"]
        return json.dumps(
            {
                "id": p.get("id", paper_id),
                "title": p.get("title", ""),
                "authors": p.get("authors", []),
                "abstract": p.get("abstract", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return f"Error fetching paper: {e}"


@mcp.tool()
def health() -> str:
    try:
        resp = _http.get("/health")
        resp.raise_for_status()
        ok = resp.json()
        return "\n".join(f"{k}: {'OK' if v else 'FAIL'}" for k, v in ok.items())
    except Exception as e:
        return f"API unreachable: {e}"


def main() -> None:
    mcp.run(
        transport="streamable-http",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8888")),
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=False,
    )


if __name__ == "__main__":
    main()
