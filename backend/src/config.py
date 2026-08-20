import os
from pathlib import Path

from loguru import logger

PAPER_INDEX_PATH = Path(
    os.getenv("LITGRAPH_CACHE", "~/.cache/litgraph/paper_index.db")
).expanduser()
if not PAPER_INDEX_PATH.exists():
    logger.warning(f"Paper index path {PAPER_INDEX_PATH} does not exist. Creating a new one.")
    PAPER_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)

EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-multilingual-e5-large-instruct")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

ARCADEDB_URI = os.getenv("ARCADEDB_URI", "bolt://localhost:7687")
ARCADEDB_HTTP_URL = os.getenv("ARCADEDB_HTTP_URL", "http://localhost:2480")
ARCADEDB_DATABASE = os.getenv("ARCADEDB_DATABASE", "litrag")
ARCADEDB_USER = os.getenv("ARCADEDB_USER", "root")
ARCADEDB_PASSWORD = os.getenv("ARCADEDB_PASSWORD", "")
