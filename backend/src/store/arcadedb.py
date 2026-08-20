"""Shared ArcadeDB access: Bolt driver (graph/opencypher) + HTTP SQL (vector / DDL)."""

import httpx
from loguru import logger
from neo4j import GraphDatabase

from src.config import (
    ARCADEDB_DATABASE,
    ARCADEDB_HTTP_URL,
    ARCADEDB_PASSWORD,
    ARCADEDB_URI,
    ARCADEDB_USER,
    EMBEDDING_DIM,
)

_driver = None
_schema_ensured = False


def get_driver():
    """Return a shared Bolt driver (process-wide singleton)."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(ARCADEDB_URI, auth=(ARCADEDB_USER, ARCADEDB_PASSWORD))
        _driver.verify_connectivity()
        logger.info(f"Connected to ArcadeDB at {ARCADEDB_URI} (db={ARCADEDB_DATABASE})")
    return _driver


def _auth() -> tuple[str, str]:
    return (ARCADEDB_USER, ARCADEDB_PASSWORD)


def sql(command: str) -> list:
    """Run an SQL command via the HTTP API and return the result rows."""
    resp = httpx.post(
        f"{ARCADEDB_HTTP_URL}/api/v1/command/{ARCADEDB_DATABASE}",
        json={"language": "sql", "command": command},
        auth=_auth(),
        timeout=120,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcadeDB SQL error: {data.get('detail') or data.get('error')}")
    return data.get("result") or []


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def ensure_database() -> None:
    """Create the database if it does not exist yet."""
    resp = httpx.get(f"{ARCADEDB_HTTP_URL}/api/v1/databases", auth=_auth(), timeout=60)
    resp.raise_for_status()
    if ARCADEDB_DATABASE not in (resp.json().get("result") or []):
        r = httpx.post(
            f"{ARCADEDB_HTTP_URL}/api/v1/server",
            json={"command": f"create database {ARCADEDB_DATABASE}"},
            auth=_auth(),
            timeout=60,
        )
        r.raise_for_status()


SCHEMA_DDL = [
    "CREATE VERTEX TYPE Paper",
    "CREATE PROPERTY Paper.id STRING",
    "CREATE PROPERTY Paper.title STRING",
    "CREATE PROPERTY Paper.authors LIST",
    "CREATE PROPERTY Paper.abstract STRING",
    "CREATE PROPERTY Paper.embedding ARRAY_OF_FLOATS",
    "CREATE PROPERTY Paper.related_ids LIST",
    "CREATE VERTEX TYPE Entity",
    "CREATE PROPERTY Entity.name STRING",
    "CREATE PROPERTY Entity.type STRING",
    "CREATE EDGE TYPE USES",
    "CREATE PROPERTY USES.role STRING",
    "CREATE INDEX ON Paper (id) UNIQUE",
    "CREATE INDEX ON Entity (name, type) UNIQUE",
    f"CREATE INDEX ON Paper (embedding) LSM_VECTOR METADATA "
    f"{{dimensions: {EMBEDDING_DIM}, similarity: 'COSINE'}}",
]


def ensure_schema() -> None:
    """Create the schema (types, properties, indexes). Idempotent."""
    global _schema_ensured
    if _schema_ensured:
        return
    ensure_database()
    for ddl in SCHEMA_DDL:
        try:
            sql(ddl)
        except RuntimeError as e:
            if "already exist" not in str(e).lower():
                raise
    _schema_ensured = True
