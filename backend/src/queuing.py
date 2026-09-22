import json

from loguru import logger
from upstash_redis import Redis

from src.models import Paper, PaperState, PaperStatus
from src.store import get_paper_index
from src.store.redis import get_redis_conn

QUEUE_LIST = "paper_queue"
QUEUE_SET = "paper_queue_ids"
MAX_ATTEMPTS = 3


def dump_payload(paper: Paper, attempts: int = 0) -> str:
    return json.dumps({"paper": paper.model_dump(), "attempts": attempts})


def parse_payload(raw: str) -> tuple[Paper, int] | None:
    """Bare Paper JSON (already queued) or {paper, attempts}. None if invalid."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        if isinstance(data, dict) and "paper" in data:
            return Paper.model_validate(data["paper"]), int(data.get("attempts") or 0)
        return Paper.model_validate(data), 0
    except Exception:
        return None


def _redis_enqueue(redis_conn: Redis, paper: Paper) -> bool:
    """Add id+payload together. True if this call enqueued the paper."""
    # Ceiling: crash between sadd and rpush leaves the id in the set with no
    # payload in the list (manual fix: SREM paper_queue_ids <id>).
    # Upgrade path: MULTI/EXEC (or pipeline) when a second worker appears.
    payload = dump_payload(paper)
    # sadd return 1 means the id was new; then rpush.
    added = redis_conn.sadd(QUEUE_SET, paper.id)
    if added is None or int(added) != 1:
        return False
    redis_conn.rpush(QUEUE_LIST, payload)
    return True


def enqueue_papers(papers: list[Paper], redis_conn: Redis | None = None) -> list[PaperState]:
    redis_conn = redis_conn or get_redis_conn()
    index = get_paper_index()
    states: list[PaperState] = []
    to_index: list[PaperState] = []

    for paper in papers:
        existing: PaperState | None = index.get(paper.id)
        if existing is not None and existing.status in (
            PaperStatus.EMBEDDED,
            PaperStatus.QUEUED,
        ):
            logger.debug(f"Skipping paper {paper.id} - already {existing.status.value}.")
            states.append(existing)
            continue

        if not _redis_enqueue(redis_conn, paper):
            logger.debug(f"Skipping paper {paper.id} - already in Redis set.")
            states.append(PaperState(id=paper.id, status=PaperStatus.QUEUED, in_graph=False))
            continue

        logger.debug(f"Enqueuing paper {paper.id} to Redis.")
        state = PaperState(id=paper.id, status=PaperStatus.QUEUED, in_graph=False)
        states.append(state)
        to_index.append(state)

    if to_index:
        index.set_many(to_index)
        logger.info(f"Enqueued {len(to_index)} papers to Redis and updated PaperIndex.")
    return states


def enqueue_missing(papers: list[Paper], redis_conn: Redis) -> None:
    """Enqueue papers that are not already embedded or queued."""
    logger.info("Enqueuing missing papers...")
    enqueue_papers(papers, redis_conn=redis_conn)
