"""Item API schemas."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SourceInItem(BaseModel):
    """Source info nested in Item response."""
    source_id: str
    source_name: str
    source_url: Optional[str] = None
    source_tier: Optional[str] = None
    source_score: Optional[float] = None


class ItemResponse(BaseModel):
    """Single item response."""
    id: str = Field(..., description="Item unique identifier")
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    body: Optional[str] = None
    url: Optional[str] = None
    completeness_score: Optional[float] = Field(None, ge=0, le=1)
    tags: List[str] = Field(default_factory=list)
    fetched_at: Optional[datetime] = None
    source: Optional[SourceInItem] = None


class ItemListResponse(BaseModel):
    """Item list response with pagination."""
    data: List[ItemResponse]
    next_cursor: Optional[str] = None
    has_more: bool = False
    count: int
    server_timestamp: datetime