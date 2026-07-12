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
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b@q8_0")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
