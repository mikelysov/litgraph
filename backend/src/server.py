from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colorama import Fore, Style
from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger

from src.api import router
from src.http_client import close_async_client, get_async_client
from src.store import health_check
from src.embedder import preload as preload_embedder
from src.llm import preload as preload_llm

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Health check
    logger.info("Performing health check...")
    health: dict[str, bool] = health_check()
    # Log results
    parts = [
        f"{key}: {Style.BRIGHT}{Fore.GREEN}OK{Style.RESET_ALL}"
        if value
        else f"{key}: {Style.BRIGHT}{Fore.RED}FAIL{Style.RESET_ALL}"
        for key, value in health.items()
    ]
    logger.debug(" | ".join(parts))

    if not all(health.values()):
        failed = [k for k, v in health.items() if not v]
        logger.error(f"Health check failed for: {failed}. Continuing boot.")
    else:
        logger.info("Health check passed.")
    logger.info("Preloading models...")
    preload_embedder()
    preload_llm()
    logger.info("All models loaded.")
    get_async_client()  # eagerly create pooled client for remote model APIs
    yield
    await close_async_client()


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api")
