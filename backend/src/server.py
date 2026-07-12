from contextlib import asynccontextmanager
from typing import AsyncGenerator

from colorama import Fore, Style
from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger

from src.api import router
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
        logger.error("Health check failed. Exiting...")
        raise RuntimeError("Health check failed.")
    logger.info("Health check passed.")
    logger.info("Preloading models...")
    preload_embedder()
    preload_llm()
    logger.info("All models loaded.")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api")
