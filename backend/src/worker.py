"""
Worker script for processing papers from a Redis queue.
This script continuously fetches batches of papers from a Redis queue,
embeds them using a pre-trained model, and updates the vector store and paper index.
"""

from concurrent.futures import ThreadPoolExecutor
from time import time

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from upstash_redis import Redis

from src.embedder import embed_papers
from src.llm import extract_entities
from src.models import Paper, PaperState, PaperStatus
from src.queuing import QUEUE_SET
from src.store import get_paper_index, get_vector_store
from src.store.graph import MockStore, get_graph_store
from src.store.redis import get_redis_conn

BATCH_SIZE = 8
IDLE_TIMEOUT = 5  # seconds; idle wait for first item
FILL_TIMEOUT = 1  # seconds; batch-fill wait for subsequent items


def get_batch(
    redis_conn: Redis,
    max_items: int,
    idle_timeout: int = IDLE_TIMEOUT,
    fill_timeout: int = FILL_TIMEOUT,
) -> list[Paper]:
    """
    Fetch up to max_items papers from Redis using blocking pop.
    The first item waits up to `idle_timeout` seconds (idle wait);
    subsequent items wait up to `fill_timeout` seconds to fill the batch.
    """
    batch: list[Paper] = []
    for i in range(max_items):
        timeout = idle_timeout if i == 0 else fill_timeout
        logger.debug("Waiting for paper in queue...")
        raw = redis_conn.blpop("paper_queue", timeout=timeout)
        if raw is None:
            break  # no new item within the timeout
        try:
            _, value = raw  # (queue name, payload)
            paper = Paper.model_validate_json(value)
            batch.append(paper)
            logger.debug(f"Fetched paper {paper.id} from queue")
        except Exception as e:
            logger.warning(f"Invalid paper format: {e}")
    return batch


def process_batch(papers: list[Paper]) -> None:
    """
    Process a batch of papers by embedding them and updating the vector store and paper index.

    Args:
        papers (list[Paper]): List of Paper objects to process.
    """
    if not papers:
        return

    # Get vector store and paper index
    vector_store = get_vector_store()
    paper_index = get_paper_index()
    graph = get_graph_store()

    redis_conn = get_redis_conn()

    # Embed papers
    try:
        vectors: NDArray[np.float32] = embed_papers(papers)
    except Exception as e:
        logger.error(f"Failed to embed batch: {e}")
        for paper in papers:
            paper_index.set(
                PaperState(
                    id=paper.id,
                    status=PaperStatus.ERROR,
                    in_graph=False,
                    error_message=str(e),
                )
            )
            redis_conn.srem(QUEUE_SET, paper.id)
        return

    successes = 0

    # Extract entities in parallel (skipped for MockStore)
    entities_by_id: dict[str, dict] = {}
    if not isinstance(graph, MockStore):
        def _extract(paper: Paper) -> tuple[str, dict | None]:
            try:
                return paper.id, extract_entities(paper.abstract)
            except Exception as e:
                logger.warning(f"Graph enrichment failed for {paper.id}: {e}")
                return paper.id, None

        with ThreadPoolExecutor(max_workers=min(BATCH_SIZE, len(papers))) as executor:
            for pid, entities in executor.map(_extract, papers):
                if entities is not None:
                    entities_by_id[pid] = entities

    # Index papers in vector store and update paper index
    for paper, vector in zip(papers, vectors):
        try:
            vector_store.index([paper], vector[np.newaxis, :])
            # Add to graph only if entity extraction succeeded (skipped for MockStore)
            entities = entities_by_id.get(paper.id)
            if entities is not None:
                graph.add_paper(paper, entities)
                in_graph = True
            else:
                in_graph = False
            paper_index.set(
                PaperState(
                    id=paper.id,
                    status=PaperStatus.EMBEDDED,
                    in_graph=in_graph,
                )
            )
            redis_conn.srem(QUEUE_SET, paper.id)
            successes += 1
        except Exception as e:
            logger.warning(f"Failed to index paper {paper.id}: {e}")
            paper_index.set(
                PaperState(
                    id=paper.id,
                    status=PaperStatus.ERROR,
                    in_graph=False,
                    error_message=str(e),
                )
            )
            redis_conn.srem(QUEUE_SET, paper.id)

    logger.info(f"Indexed {successes}/{len(papers)} papers")


def run_worker_loop() -> None:
    """
    Main loop for the worker process. Continuously fetches batches of papers from Redis,
    processes them, and updates the vector store and paper index.
    """
    logger.info("Starting worker loop...")
    redis_conn: Redis = get_redis_conn()

    while True:
        start_time = time()

        papers = get_batch(redis_conn, BATCH_SIZE)

        if not papers:
            # blpop already blocked for `idle_timeout`; loop back immediately
            continue

        process_batch(papers)

        duration = time() - start_time
        logger.info(f"Batch processed in {duration:.2f} seconds")


def run_worker_once() -> int:
    """
    Run a single batch of the worker. Returns number of papers processed.
    """
    redis_conn: Redis = get_redis_conn()
    papers = get_batch(redis_conn, BATCH_SIZE)
    process_batch(papers)
    return len(papers)


if __name__ == "__main__":
    processed = run_worker_once()
    if processed == 0:
        logger.info("No papers in queue — exiting.")
