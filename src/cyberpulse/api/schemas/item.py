"""Item API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceInItem(BaseModel):
    """Source info nested in Item response."""

    source_id: str
    source_name: str
    source_url: str | None = None
    source_tier: str | None = None
    source_score: float | None = None


class ItemResponse(BaseModel):
    """Single item response."""

    id: str = Field(..., description="Item unique identifier")
    title: str = Field(..., description="Normalized title (with fallback to raw title)")
    author: str | None = None
    published_at: datetime | None = None
    body: str | None = None
    url: str | None = None
    completeness_score: float | None = Field(None, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    word_count: int | None = Field(None, description="Word count of normalized body")
    fetched_at: datetime | None = None
    source: SourceInItem | None = None
    # Full content fetch status
    full_fetch_attempted: bool = Field(
        default=False, description="Whether full content fetch was attempted"
    )
    full_fetch_succeeded: bool | None = Field(
        None, description="Whether full content fetch succeeded"
    )


class ItemListResponse(BaseModel):
    """Item list response with pagination."""

    data: list[ItemResponse]
    next_cursor: str | None = None
    has_more: bool = False
    count: int
    server_timestamp: datetime
