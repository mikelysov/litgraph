"""Shared PDF parsing used by the MCP tool and the API upload endpoint."""

import re
from pathlib import Path

from loguru import logger
from pypdf import PdfReader

from src.arxiv import fetch_paper_by_id
from src.models import Paper

ARXIV_ID_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")


def parse_pdf_to_paper(file_path: Path) -> tuple[Paper, int, int]:
    """Parse a PDF file into a Paper plus (page_count, text_len).

    When the filename is an arXiv ID (e.g. ``2203.13790.pdf``), metadata is
    fetched via ``fetch_paper_by_id`` and the extracted text is appended to
    the abstract. Otherwise the filename is used as the paper ID.
    """
    stem = re.sub(r"\.pdf$", "", file_path.name, flags=re.IGNORECASE)

    reader = PdfReader(str(file_path))
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not pdf_text.strip():
        raise ValueError(f"no text extracted from {file_path.name}")

    if ARXIV_ID_RE.match(stem):
        logger.info(f"arXiv ID detected: {stem}, fetching metadata...")
        paper = fetch_paper_by_id(stem)
        if paper is not None:
            paper.abstract = f"{paper.abstract}\n\n{pdf_text[:15000]}"
            logger.info(f"Using arXiv metadata for {paper.id}: {paper.title[:60]}")
            return paper, len(reader.pages), len(pdf_text)

    logger.info(f"No arXiv metadata, using filename as ID: {stem}")
    paper = Paper(id=stem, url="", title=stem, authors=[], abstract=pdf_text[:10000])
    return paper, len(reader.pages), len(pdf_text)
