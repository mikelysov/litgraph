import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import httpx
from httpx import Client
from mcp.server.mcpserver import MCPServer

from src.models import Paper

load_dotenv()

API_URL = os.getenv("LITGRAPH_API_URL", "http://localhost:8889/api")
ARCADEDB_HTTP_URL = os.getenv("ARCADEDB_HTTP_URL", "http://localhost:2480")
ARCADEDB_DATABASE = os.getenv("ARCADEDB_DATABASE", "litrag")
ARCADEDB_USER = os.getenv("ARCADEDB_USER", "root")
ARCADEDB_PASSWORD = os.getenv("ARCADEDB_PASSWORD", "")
INGEST_PDF_ROOT = Path(os.getenv("INGEST_PDF_ROOT", "/docs")).resolve()

_http = Client(base_url=API_URL, timeout=120.0)
_arcadedb = Client(base_url=ARCADEDB_HTTP_URL, timeout=30.0)

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


def _resolve_pdf_url(url: str) -> str | None:
    """Map an arXiv ID / abs-link to a downloadable PDF URL; pass http(s) through."""
    stripped = url.strip()
    abs_match = re.match(r"^https?://arxiv\.org/abs/(\d{4}\.\d{4,5})(?:v\d+)?$", stripped)
    if abs_match:
        return f"https://arxiv.org/pdf/{abs_match.group(1)}"
    if re.match(r"^https?://", stripped):
        return stripped
    if re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", stripped):
        return f"https://arxiv.org/pdf/{stripped}"
    return None


def _download_pdf(url: str) -> Path | str:
    """Stream-download a PDF into the staging directory; return path or error string."""
    from src.staging import ensure_staging

    name = Path(url.split("?", 1)[0]).name or "paper.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    dest = ensure_staging() / name
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    except Exception as e:
        dest.unlink(missing_ok=True)
        return f"Error: download failed: {e}"
    return dest


def _ingest_paper(paper: Paper, pages: int, text_len: int) -> str:
    """POST a parsed paper to /ingest; return the result message."""
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
        f"OK, pages={pages}, text_len={text_len}"
    )


@mcp.tool()
def ingest_pdf(url: str | None = None, file_path: str | None = None) -> str:
    """Ingest a PDF from a URL (server downloads) or from a path under INGEST_PDF_ROOT."""
    if (url is None) == (file_path is None):
        return "Error: provide exactly one of url or file_path"

    from src.pdf import parse_pdf_to_paper
    from src.staging import sweep_staging

    sweep_staging()

    if file_path is not None:
        resolved = _resolve_pdf_path(file_path)
        if isinstance(resolved, str):
            return resolved
        try:
            paper, pages, text_len = parse_pdf_to_paper(resolved)
        except Exception as e:
            return f"Error: failed to parse PDF: {e}"
        return _ingest_paper(paper, pages, text_len)

    assert url is not None
    download_url = _resolve_pdf_url(url)
    if download_url is None:
        return f"Error: cannot parse source: {url}"

    local = _download_pdf(download_url)
    if isinstance(local, str):
        return local
    try:
        paper, pages, text_len = parse_pdf_to_paper(local)
    except Exception as e:
        return f"Error: failed to parse PDF: {e}"
    finally:
        local.unlink(missing_ok=True)
    return _ingest_paper(paper, pages, text_len)


@mcp.tool()
def get_paper(paper_id: str) -> str:
    """Fetch full paper details (title, authors, abstract) by arXiv ID."""
    try:
        escaped = paper_id.replace("'", "''")
        resp = _arcadedb.post(
            f"/api/v1/command/{ARCADEDB_DATABASE}",
            json={
                "language": "sql",
                "command": (
                    f"SELECT id, title, authors, abstract FROM Paper WHERE id = '{escaped}'"
                ),
            },
            auth=(ARCADEDB_USER, ARCADEDB_PASSWORD),
        )
        resp.raise_for_status()
        rows = resp.json().get("result", [])
        if not rows:
            return f"Paper {paper_id} not found."
        p = rows[0]
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
