from loguru import logger
from upstash_redis import Redis

from src.models import Paper, PaperState, PaperStatus
from src.store import get_paper_index
from src.store.redis import get_redis_conn

QUEUE_LIST = "paper_queue"
QUEUE_SET = "paper_queue_ids"


def enqueue_papers(papers: list[Paper]) -> list[PaperState]:
    redis_conn: Redis = get_redis_conn()
    index = get_paper_index()
    states: list[PaperState] = []

    for paper in papers:
        logger.debug(f"Enqueuing paper {paper.id} to Redis.")
        redis_conn.rpush(QUEUE_LIST, paper.model_dump_json())
        redis_conn.sadd(QUEUE_SET, paper.url)

        state = PaperState(id=paper.id, status=PaperStatus.QUEUED, in_graph=False)
        states.append(state)

    index.set_many(states)
    logger.info(f"Enqueued {len(papers)} papers to Redis and updated PaperIndex.")
    return states


def enqueue_missing(papers: list[Paper], redis_conn: Redis) -> None:
    """
    Enqueue papers that are missing from the queue.

    Args:
        papers (list[Paper]): List of Paper objects to check and enqueue.
        redis_conn (Redis): Redis connection object.
    """
    logger.info("Enqueuing missing papers...")
    index = get_paper_index()
    to_queue: list[PaperState] = []

    for paper in papers:
        state: PaperState | None = index.get(paper.id)

        # Skip if already embedded or marked as queued
        if state is not None and state.status in (PaperStatus.EMBEDDED, PaperStatus.QUEUED):
            logger.debug(f"Skipping paper {paper.id} - already embedded or queued.")
            continue

        # Check Redis set for already-queued status
        if redis_conn.sismember(QUEUE_SET, paper.url):
            logger.debug(f"Skipping paper {paper.id} - already in Redis set.")
            continue

        # Add to Redis queue and set
        logger.debug(f"Enqueuing paper {paper.id} to Redis.")
        redis_conn.rpush(QUEUE_LIST, paper.model_dump_json())
        redis_conn.sadd(QUEUE_SET, paper.url)

        # Track for PaperIndex update
        to_queue.append(
            PaperState(
                id=paper.id,
                status=PaperStatus.QUEUED,
                in_graph=False,
            )
        )

    if to_queue:
        index.set_many(to_queue)
        logger.info(f"Enqueued {len(to_queue)} papers to Redis and updated PaperIndex.")
