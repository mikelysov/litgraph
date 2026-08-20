"""Shared async HTTP client lifecycle for remote model APIs."""

import httpx

_async_client: httpx.AsyncClient | None = None


def get_async_client() -> httpx.AsyncClient:
    """Lazily create a pooled AsyncClient (safe if called outside lifespan)."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=120.0)
    return _async_client


async def close_async_client() -> None:
    """Close the shared AsyncClient on shutdown."""
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
    _async_client = None
