"""
Worker script for processing papers from a Redis queue.
This script continuously fetches batches of papers from a Redis queue,
embeds them using a pre-trained model, and updates the vector store and paper index.
"""

from time import sleep, time

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
SLEEP_INTERVAL = 1.0  # seconds


def get_batch(redis_conn: Redis, max_items: int, timeout: int = 5) -> list[Paper]:
    """
    Fetch up to max_items papers from Redis using blocking pop.
    Waits up to `timeout` seconds for each item before giving up.
    """
    batch: list[Paper] = []
    for _ in range(max_items):
        logger.debug("Waiting for paper in queue...")
        raw = redis_conn.blpop("paper_queue", timeout=timeout)
        if raw is None:
            break  # no new item in `timeout` seconds
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

    # Index papers in vector store and update paper index
    for paper, vector in zip(papers, vectors):
        try:
            vector_store.index([paper], vector[np.newaxis, :])
            # Extract entities and build Neo4j graph (skipped for MockStore)
            if not isinstance(graph, MockStore):
                try:
                    entities = extract_entities(paper.abstract)
                    graph.add_paper(paper, entities)
                    in_graph = True
                except Exception as e:
                    logger.warning(f"Graph enrichment failed for {paper.id}: {e}")
                    in_graph = False
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

    backoff = SLEEP_INTERVAL

    while True:
        start_time = time()

        papers = get_batch(redis_conn, BATCH_SIZE)

        if not papers:
            logger.debug(f"No papers found, sleeping for {backoff:.1f}s...")
            sleep(backoff)
            backoff = min(backoff * 2, 60.0)  # Cap at 1 min
            continue

        backoff = SLEEP_INTERVAL  # reset backoff
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
