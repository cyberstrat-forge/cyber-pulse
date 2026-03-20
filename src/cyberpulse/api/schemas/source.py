"""
Source API schemas.

Pydantic models for Source API request/response validation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceBase(BaseModel):
    """Base schema for Source with common fields."""

    name: str = Field(..., description="Unique source name", min_length=1, max_length=255)
    connector_type: str = Field(
        ...,
        description="Type of connector (rss, api, web_scraper, media_api)",
        min_length=1,
        max_length=50
    )
    tier: Optional[str] = Field(
        None,
        description="Source tier (T0, T1, T2, T3). Derived from score if not provided."
    )
    score: Optional[float] = Field(
        None,
        description="Source quality score (0-100). Derived from tier if not provided.",
        ge=0.0,
        le=100.0
    )
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Connector configuration"
    )
    fetch_interval: Optional[int] = Field(
        None,
        description="Fetch interval in seconds",
        ge=60
    )


class SourceCreate(SourceBase):
    """Schema for creating a new source."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Security Weekly RSS",
                "connector_type": "rss",
                "tier": "T1",
                "score": 70.0,
                "config": {
                    "url": "https://example.com/feed.xml",
                    "categories": ["security"]
                },
                "fetch_interval": 3600
            }
        }
    }


class SourceUpdate(BaseModel):
    """Schema for updating a source. All fields are optional."""

    name: Optional[str] = Field(None, description="Unique source name", min_length=1, max_length=255)
    connector_type: Optional[str] = Field(None, description="Type of connector", min_length=1, max_length=50)
    tier: Optional[str] = Field(None, description="Source tier (T0, T1, T2, T3)")
    score: Optional[float] = Field(None, description="Source quality score (0-100)", ge=0.0, le=100.0)
    status: Optional[str] = Field(None, description="Source status (ACTIVE, FROZEN, REMOVED)")
    is_in_observation: Optional[bool] = Field(None, description="Whether source is in observation period")
    observation_until: Optional[datetime] = Field(None, description="Observation period end date")
    pending_review: Optional[bool] = Field(None, description="Whether source is pending review")
    review_reason: Optional[str] = Field(None, description="Reason for review")
    fetch_interval: Optional[int] = Field(None, description="Fetch interval in seconds", ge=60)
    config: Optional[Dict[str, Any]] = Field(None, description="Connector configuration")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tier": "T0",
                "score": 85.0,
                "fetch_interval": 1800
            }
        }
    }


class SourceResponse(BaseModel):
    """
    Single source response.

    Represents a full source entity with all metadata.
    """

    source_id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Unique source name")
    connector_type: str = Field(..., description="Type of connector")
    tier: str = Field(..., description="Source tier (T0, T1, T2, T3)")
    score: float = Field(..., description="Source quality score (0-100)")
    status: str = Field(..., description="Source status (ACTIVE, FROZEN, REMOVED)")
    is_in_observation: bool = Field(..., description="Whether source is in observation period")
    observation_until: Optional[datetime] = Field(None, description="Observation period end date")
    pending_review: bool = Field(..., description="Whether source is pending review")
    review_reason: Optional[str] = Field(None, description="Reason for review")
    fetch_interval: Optional[int] = Field(None, description="Fetch interval in seconds")
    config: Dict[str, Any] = Field(..., description="Connector configuration")

    # Statistics
    last_fetched_at: Optional[datetime] = Field(None, description="Last fetch timestamp")
    last_scored_at: Optional[datetime] = Field(None, description="Last scoring timestamp")
    total_items: int = Field(..., description="Total items collected")
    total_contents: int = Field(..., description="Total contents produced")

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "source_id": "src_a1b2c3d4",
                "name": "Security Weekly RSS",
                "connector_type": "rss",
                "tier": "T1",
                "score": 70.0,
                "status": "ACTIVE",
                "is_in_observation": True,
                "observation_until": "2026-04-19T00:00:00Z",
                "pending_review": False,
                "review_reason": None,
                "fetch_interval": 3600,
                "config": {
                    "url": "https://example.com/feed.xml",
                    "categories": ["security"]
                },
                "last_fetched_at": "2026-03-19T10:00:00Z",
                "last_scored_at": "2026-03-19T12:00:00Z",
                "total_items": 150,
                "total_contents": 120,
                "created_at": "2026-03-19T08:00:00Z",
                "updated_at": "2026-03-19T12:00:00Z"
            }
        }
    }


class SourceListResponse(BaseModel):
    """
    Paginated list of sources.

    Uses offset-based pagination for simplicity.
    """

    data: List[SourceResponse] = Field(
        default_factory=list,
        description="List of sources"
    )
    count: int = Field(
        ...,
        description="Number of items in this page"
    )
    offset: int = Field(
        ...,
        description="Current offset"
    )
    limit: int = Field(
        ...,
        description="Maximum items per page"
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
                        "source_id": "src_a1b2c3d4",
                        "name": "Security Weekly RSS",
                        "connector_type": "rss",
                        "tier": "T1",
                        "score": 70.0,
                        "status": "ACTIVE",
                        "is_in_observation": True,
                        "observation_until": "2026-04-19T00:00:00Z",
                        "pending_review": False,
                        "review_reason": None,
                        "fetch_interval": 3600,
                        "config": {},
                        "last_fetched_at": None,
                        "last_scored_at": None,
                        "total_items": 0,
                        "total_contents": 0,
                        "created_at": "2026-03-19T08:00:00Z",
                        "updated_at": "2026-03-19T08:00:00Z"
                    }
                ],
                "count": 1,
                "offset": 0,
                "limit": 100,
                "server_timestamp": "2026-03-19T16:00:00Z"
            }
        }
    }