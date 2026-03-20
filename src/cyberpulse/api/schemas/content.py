"""
Content API schemas.

Pydantic models for Content API request/response validation.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ContentResponse(BaseModel):
    """
    Single content item response.

    Represents a deduplicated content entity with normalized text.
    """

    content_id: str = Field(..., description="Unique content identifier")
    canonical_hash: str = Field(..., description="Hash for deduplication")
    normalized_title: str = Field(..., description="Normalized title text")
    normalized_body: str = Field(..., description="Normalized body text")
    first_seen_at: datetime = Field(..., description="When content was first seen")
    last_seen_at: datetime = Field(..., description="When content was last seen")
    source_count: int = Field(..., description="Number of sources for this content")
    status: str = Field(..., description="Content status (active/archived)")

    model_config = {
        "from_attributes": True,  # Enable ORM mode for SQLAlchemy models
        "json_schema_extra": {
            "example": {
                "content_id": "cnt_20260319143052_a1b2c3d4",
                "canonical_hash": "abc123def456...",
                "normalized_title": "Security Update: Critical Vulnerability",
                "normalized_body": "A critical vulnerability has been discovered...",
                "first_seen_at": "2026-03-19T14:30:52Z",
                "last_seen_at": "2026-03-19T15:45:00Z",
                "source_count": 3,
                "status": "ACTIVE",
            }
        },
    }


class ContentListResponse(BaseModel):
    """
    Paginated list of content items.

    Uses cursor-based pagination for efficient large dataset traversal.
    """

    data: List[ContentResponse] = Field(
        default_factory=list,
        description="List of content items"
    )
    next_cursor: Optional[str] = Field(
        None,
        description="Cursor for the next page (last content_id in this page)"
    )
    has_more: bool = Field(
        False,
        description="Whether more results are available"
    )
    count: int = Field(
        ...,
        description="Number of items in this page"
    )
    server_timestamp: datetime = Field(
        ...,
        description="Server timestamp when response was generated"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "data": [
                    {
                        "content_id": "cnt_20260319143052_a1b2c3d4",
                        "canonical_hash": "abc123def456...",
                        "normalized_title": "Security Update: Critical Vulnerability",
                        "normalized_body": "A critical vulnerability has been discovered...",
                        "first_seen_at": "2026-03-19T14:30:52Z",
                        "last_seen_at": "2026-03-19T15:45:00Z",
                        "source_count": 3,
                        "status": "ACTIVE",
                    }
                ],
                "next_cursor": "cnt_20260319120000_xyz789",
                "has_more": True,
                "count": 1,
                "server_timestamp": "2026-03-19T16:00:00Z",
            }
        },
    }