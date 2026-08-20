"""Bounded staging directory for PDF ingestion with TTL cleanup."""

import os
import time
from pathlib import Path

from loguru import logger

INGEST_STAGING_DIR = Path(os.getenv("INGEST_STAGING_DIR", "/staging")).resolve()
STAGING_TTL = int(os.getenv("STAGING_TTL", "3600"))  # seconds


def ensure_staging() -> Path:
    """Create (if needed) and return the staging directory."""
    INGEST_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return INGEST_STAGING_DIR


def sweep_staging() -> None:
    """Delete staging files older than STAGING_TTL (orphans from crashed processes)."""
    ensure_staging()
    now = time.time()
    removed = 0
    for path in INGEST_STAGING_DIR.glob("*"):
        try:
            if path.is_file() and (now - path.stat().st_mtime) > STAGING_TTL:
                path.unlink()
                removed += 1
        except OSError:
            logger.debug(f"staging sweep: skip {path}")
    if removed:
        logger.info(f"staging sweep removed {removed} orphan file(s)")
