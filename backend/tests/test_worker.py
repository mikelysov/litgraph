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
    mock_redis.lpop.side_effect = ['{"bad": "data"}', None]

    batch = get_batch(mock_redis, max_items=2)

    assert len(batch) == 0  # should skip invalid input


@patch("src.worker.get_redis_conn")
@patch("src.worker.get_vector_store")
@patch("src.worker.get_paper_index")
@patch("src.worker.embed_papers")
def test_process_batch_happy_path(
    mock_embed, mock_get_index, mock_get_store, mock_get_redis, sample_paper
):
    mock_embed.return_value = np.random.rand(1, 384).astype(np.float32)
    mock_index = MagicMock()
    mock_store = MagicMock()
    mock_redis = MagicMock()
    mock_get_store.return_value = mock_store
    mock_get_index.return_value = mock_index
    mock_get_redis.return_value = mock_redis

    process_batch([sample_paper])

    mock_embed.assert_called_once()
    mock_store.index.assert_called_once()
    mock_index.set.assert_called_once_with(
        PaperState(
            id=sample_paper.id,
            status=PaperStatus.EMBEDDED,
            in_graph=False,
        )
    )
    mock_redis.srem.assert_called_once()


def test_process_batch_empty():
    # Should do nothing and not crash
    assert process_batch([]) is None
