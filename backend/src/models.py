from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestEventType(str, Enum):
    STEP = "step"
    PROGRESS = "progress"
    WARNING = "warning"
    ERROR = "error"
    RESULT = "result"


class IngestEvent(BaseModel):
    """
    Represents an event in the ingestion pipeline.

    Attributes:
        type (IngestEventType): The type of the event (e.g., step, progress, warning, error, result).
        step (str): The name of the step in the pipeline.
        message (str): A message describing the event.
        progress (float): A float representing the progress percentage (0.0 to 1.0).
        paper_id (str): The ID of the paper being processed.
        data (Any): Additional data related to the event.
    """

    type: IngestEventType | None = Field(
        default=None,
        description="Type of the event (e.g., step, progress, warning, error, result)",
    )
    step: str | None = Field(
        default=None,
        description="Name of the step in the pipeline",
    )
    message: str | None = Field(
        default=None,
        description="Message describing the event",
    )
    progress: float | None = Field(
        default=None,
        description="Progress percentage (0.0 to 1.0)",
    )
    paper_id: str | None = Field(
        default=None,
        description="ID of the paper being processed",
    )
    data: Any = Field(
        default=None,
        description="Additional data related to the event",
    )


class Paper(BaseModel):
    id: str
    url: str
    title: str
    abstract: str
    authors: list[str]


class PaperStatus(str, Enum):
    QUEUED = "queued"
    EMBEDDED = "embedded"
    SEEN = "seen"
    ERROR = "error"


class PaperState(BaseModel):
    """
    Represents the state of a paper in the ingestion pipeline.
    """

    model_config = ConfigDict(
        from_attributes=True,
        coerce_numbers_to_str=True,
    )
    id: str
    status: PaperStatus
    in_graph: bool = Field(
        default=False,
        description="Whether the paper is in the graph",
    )
    last_seen: datetime | None = Field(
        default=None,
        description="Timestamp of the last time the paper was seen",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the paper failed to process",
    )


class SearchResult(BaseModel):
    id: str
    title: str
    authors: list[str]
    abstract: str = ""
    score: float | None = Field(
        default=None,
        description="Score of the search result",
    )
    related_ids: list[str] | None = Field(
        default=None,
        description="List of related paper IDs",
    )
    model_config = ConfigDict(coerce_numbers_to_str=True)


class PaperNode(BaseModel):
    id: str
    title: str
    authors: list[str]
    score: float | None = None  # set for top search hits
    related_ids: list[str] | None = None
    centrality: float | None = None  # set for graph metrics


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    type: str


class GraphData(BaseModel):
    nodes: list[PaperNode]
    edges: list[GraphEdge]


class SearchResponse(BaseModel):
    results: list[PaperNode]  # subset of nodes
    graph: GraphData
