from unittest.mock import MagicMock, create_autospec

import pytest
from upstash_redis import Redis

from src.models import Paper, PaperState, PaperStatus
from src.queuing import enqueue_missing
from src.store import PaperIndex


@pytest.fixture
def mock_redis() -> MagicMock:
    mock = create_autospec(Redis, instance=True, spec_set=True)
    mock.sismember.return_value = False
    return mock


@pytest.fixture
def mock_paper_index() -> MagicMock:
    mock_index = create_autospec(PaperIndex, instance=True, spec_set=True)
    mock_index.get.return_value = None
    mock_index.set_many.return_value = None
    return mock_index


@pytest.fixture
def mock_get_paper_index(monkeypatch: pytest.MonkeyPatch, mock_paper_index: MagicMock) -> None:
    monkeypatch.setattr("src.queuing.get_paper_index", lambda: mock_paper_index)


@pytest.fixture
def sample_papers() -> list[Paper]:
    return [
        Paper(
            id="1",
            url="http://example.com/1",
            title="Title 1",
            abstract="Abstract 1",
            authors=["Author A"],
        ),
        Paper(
            id="2",
            url="http://example.com/2",
            title="Title 2",
            abstract="Abstract 2",
            authors=["Author B"],
        ),
        Paper(
            id="3",
            url="http://example.com/3",
            title="Title 3",
            abstract="Abstract 3",
            authors=["Author C"],
        ),
    ]


def test_enqueue_missing_empty_list(
    mock_redis: MagicMock, mock_get_paper_index: None, mock_paper_index: MagicMock
):
    enqueue_missing([], mock_redis)
    mock_redis.rpush.assert_not_called()
    mock_redis.sadd.assert_not_called()
    mock_paper_index.set_many.assert_not_called()


def test_enqueue_missing_all_new_papers(
    mock_redis: MagicMock,
    mock_get_paper_index: None,
    mock_paper_index: MagicMock,
    sample_papers: list[Paper],
):
    # Mock PaperIndex to return None for all papers
    mock_paper_index.get.side_effect = lambda paper_id: None
    mock_redis.sismember.return_value = False

    # Call the function
    enqueue_missing(sample_papers, mock_redis)

    # Assert Redis operations
    assert mock_redis.rpush.call_count == len(sample_papers)
    assert mock_redis.sadd.call_count == len(sample_papers)

    # Assert PaperIndex updates
    assert mock_paper_index.set_many.call_count == 1
    queued_states = mock_paper_index.set_many.call_args[0][0]
    assert len(queued_states) == len(sample_papers)
    for state in queued_states:
        assert state.status == PaperStatus.QUEUED


def test_enqueue_missing_some_already_queued(
    mock_redis: MagicMock,
    mock_get_paper_index: None,
    mock_paper_index: MagicMock,
    sample_papers: list[Paper],
):
    mock_redis.sismember.return_value = False
    # Mock PaperIndex to return some papers as already queued
    mock_paper_index.get.side_effect = lambda paper_id: (
        PaperState(id=paper_id, status=PaperStatus.QUEUED, in_graph=False)
        if paper_id == "1"
        else None
    )

    # Call the function
    enqueue_missing(sample_papers, mock_redis)

    # Assert Redis operations
    assert mock_redis.rpush.call_count == len(sample_papers) - 1
    assert mock_redis.sadd.call_count == len(sample_papers) - 1

    # Assert PaperIndex updates
    assert mock_paper_index.set_many.call_count == 1
    queued_states = mock_paper_index.set_many.call_args[0][0]
    assert len(queued_states) == len(sample_papers) - 1


def test_enqueue_missing_already_in_redis(
    mock_redis: MagicMock,
    mock_get_paper_index: None,
    mock_paper_index: MagicMock,
    sample_papers: list[Paper],
):
    # Mock Redis to indicate some papers are already in the set (keyed by paper id)
    mock_redis.sismember.side_effect = lambda queue_set, paper_id: paper_id == "2"

    # Call the function
    enqueue_missing(sample_papers, mock_redis)

    # Assert Redis operations
    assert mock_redis.rpush.call_count == len(sample_papers) - 1
    assert mock_redis.sadd.call_count == len(sample_papers) - 1

    # Assert PaperIndex updates
    assert mock_paper_index.set_many.call_count == 1


def test_enqueue_missing_no_papers_to_enqueue(
    mock_redis: MagicMock,
    mock_get_paper_index: None,
    mock_paper_index: MagicMock,
    sample_papers: list[Paper],
):
    # Mock PaperIndex and Redis to indicate all papers are already queued or embedded
    mock_paper_index.get.side_effect = lambda paper_id: PaperState(
        id=paper_id, status=PaperStatus.EMBEDDED, in_graph=True
    )
    mock_redis.sismember.return_value = True

    # Call the function
    enqueue_missing(sample_papers, mock_redis)

    # Assert no Redis operations
    mock_redis.rpush.assert_not_called()
    mock_redis.sadd.assert_not_called()

    # Assert no PaperIndex updates
    mock_paper_index.set_many.assert_not_called()
