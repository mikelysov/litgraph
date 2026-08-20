from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from src.worker import get_batch, process_batch

from src.models import Paper, PaperState, PaperStatus


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def sample_paper():
    return Paper(
        id="paper-123",
        title="Sample Paper",
        abstract="A sample abstract.",
        authors=["Author A", "Author B"],
        url="https://somesite.com",
    )


def test_get_batch_valid_papers(mock_redis, sample_paper):
    raw = sample_paper.model_dump_json()
    mock_redis.blpop.side_effect = [("paper_queue", raw), None]

    batch = get_batch(mock_redis, max_items=5)

    assert len(batch) == 1
    assert batch[0].id == "paper-123"
    mock_redis.blpop.assert_called()


def test_get_batch_with_invalid_paper(mock_redis):
    mock_redis.blpop.side_effect = [("paper_queue", '{"bad": "data"}'), None]

    batch = get_batch(mock_redis, max_items=2)

    assert len(batch) == 0  # should skip invalid input


@patch("src.worker.get_redis_conn")
@patch("src.worker.get_vector_store")
@patch("src.worker.get_paper_index")
@patch("src.worker.get_graph_store")
@patch("src.worker.extract_entities")
@patch("src.worker.embed_papers")
def test_process_batch_happy_path(
    mock_embed, mock_extract, mock_get_graph, mock_get_index, mock_get_store, mock_get_redis, sample_paper
):
    mock_embed.return_value = np.random.rand(1, 384).astype(np.float32)
    mock_extract.return_value = {"methods": [], "datasets": [], "tasks": [], "models": []}
    mock_index = MagicMock()
    mock_store = MagicMock()
    mock_graph = MagicMock()
    mock_redis = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_index.return_value = mock_index
    mock_get_graph.return_value = mock_graph
    mock_get_redis.return_value = mock_redis

    process_batch([sample_paper])

    mock_embed.assert_called_once()
    mock_store.index.assert_called_once()
    mock_graph.add_paper.assert_called_once()
    mock_index.set.assert_called_once_with(
        PaperState(
            id=sample_paper.id,
            status=PaperStatus.EMBEDDED,
            in_graph=True,
        )
    )
    mock_redis.srem.assert_called_once()


def test_process_batch_empty():
    # Should do nothing and not crash
    assert process_batch([]) is None


def test_process_batch_parallel_extract():
    import threading

    import src.worker as worker_module

    papers = [
        Paper(id="p1", title="T1", abstract="A1", authors=["X"], url=""),
        Paper(id="p2", title="T2", abstract="A2", authors=["Y"], url=""),
    ]
    barrier = threading.Barrier(2, timeout=5)

    def slow_extract(text):
        barrier.wait(timeout=5)  # both calls must arrive concurrently
        return {"methods": [], "datasets": [], "tasks": [], "models": []}

    with (
        patch.object(worker_module, "embed_papers") as mock_embed,
        patch.object(worker_module, "get_vector_store") as mock_get_store,
        patch.object(worker_module, "get_paper_index") as mock_get_index,
        patch.object(worker_module, "get_graph_store") as mock_get_graph,
        patch.object(worker_module, "get_redis_conn") as mock_get_redis,
        patch.object(worker_module, "extract_entities", side_effect=slow_extract) as mock_extract,
    ):
        mock_embed.return_value = np.random.rand(2, 384).astype(np.float32)
        mock_get_store.return_value = MagicMock()
        index = MagicMock()
        mock_get_index.return_value = index
        mock_get_graph.return_value = MagicMock()  # real graph store
        mock_get_redis.return_value = MagicMock()

        process_batch(papers)

    assert mock_extract.call_count == 2
    # in_graph=True for both => both extractions succeeded concurrently
    calls = [c.args[0] for c in index.set.call_args_list]
    assert all(c.in_graph for c in calls)
