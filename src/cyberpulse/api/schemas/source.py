"""
Source API schemas.

Pydantic models for Source API request/response validation.
"""

from datetime import datetime
from typing import Any

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
    tier: str | None = Field(
        None,
        description="Source tier (T0, T1, T2, T3). Derived from score if not provided."
    )
    score: float | None = Field(
        None,
        description="Source quality score (0-100). Derived from tier if not provided.",
        ge=0.0,
        le=100.0
    )
    config: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Connector configuration"
    )


class SourceCreate(SourceBase):
    """Schema for creating a new source."""

    needs_full_fetch: bool | None = Field(None, description="Whether full text fetch is needed for summary-only content")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Security Weekly RSS",
                "connector_type": "rss",
                "tier": "T1",
                "score": 70.0,
                "needs_full_fetch": True,
                "config": {
                    "feed_url": "https://example.com/feed.xml",
                    "categories": ["security"]
                }
            }
        }
    }


class SourceUpdate(BaseModel):
    """Schema for updating a source. All fields are optional."""

    name: str | None = Field(None, description="Unique source name", min_length=1, max_length=255)
    connector_type: str | None = Field(None, description="Type of connector", min_length=1, max_length=50)
    tier: str | None = Field(None, description="Source tier (T0, T1, T2, T3)")
    score: float | None = Field(None, description="Source quality score (0-100)", ge=0.0, le=100.0)
    status: str | None = Field(None, description="Source status (ACTIVE, FROZEN, REMOVED)")
    pending_review: bool | None = Field(None, description="Whether source is pending review")
    review_reason: str | None = Field(None, description="Reason for review")
    schedule_interval: int | None = Field(None, description="Ingest interval in seconds", ge=300)
    config: dict[str, Any] | None = Field(None, description="Connector configuration")
    needs_full_fetch: bool | None = Field(None, description="Whether full text fetch is needed for summary-only content")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tier": "T0",
                "score": 85.0,
                "schedule_interval": 1800,
                "needs_full_fetch": True
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
    pending_review: bool = Field(..., description="Whether source is pending review")
    review_reason: str | None = Field(None, description="Reason for review")
    config: dict[str, Any] = Field(..., description="Connector configuration")

    # Statistics
    last_scored_at: datetime | None = Field(None, description="Last scoring timestamp")
    total_items: int = Field(..., description="Total items collected")

    # Scheduling fields (from design doc)
    schedule_interval: int | None = Field(None, description="Ingest interval in seconds")
    next_ingest_at: datetime | None = Field(None, description="Next ingest scheduled time")
    last_ingested_at: datetime | None = Field(None, description="Last ingest timestamp")
    last_ingest_result: str | None = Field(None, description="Last ingest result status")

    # Collection statistics (from design doc)
    items_last_7d: int = Field(0, description="Items collected in last 7 days")

    # Error tracking (from design doc)
    consecutive_failures: int = Field(0, description="Consecutive failure count")
    last_error_at: datetime | None = Field(None, description="Last error timestamp")
    last_error_message: str | None = Field(None, description="Last error message summary")
    last_job_id: str | None = Field(None, description="Last job ID")

    # Full fetch configuration (from design doc)
    needs_full_fetch: bool = Field(False, description="Whether full text fetch is needed")
    full_fetch_threshold: float | None = Field(None, description="Full text fetch threshold")
    content_type: str | None = Field(None, description="Content type")
    avg_content_length: int | None = Field(None, description="Average content length")
    quality_score: float | None = Field(None, description="Source quality score")
    full_fetch_success_count: int = Field(0, description="Full text fetch success count")
    full_fetch_failure_count: int = Field(0, description="Full text fetch failure count")

    # Warnings (computed field)
    warnings: list[str] = Field(default_factory=list, description="Warning messages")

    # Timestamps
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")

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
                "pending_review": False,
                "review_reason": None,
                "config": {
                    "url": "https://example.com/feed.xml",
                    "categories": ["security"]
                },
                "last_scored_at": "2026-03-19T12:00:00Z",
                "total_items": 150,
                "schedule_interval": 3600,
                "next_ingest_at": "2026-03-19T11:00:00Z",
                "last_ingested_at": "2026-03-19T10:00:00Z",
                "last_ingest_result": "success",
                "items_last_7d": 25,
                "consecutive_failures": 0,
                "last_error_at": None,
                "last_error_message": None,
                "last_job_id": None,
                "needs_full_fetch": True,
                "full_fetch_threshold": 0.7,
                "content_type": "summary",
                "avg_content_length": 150,
                "quality_score": 75.0,
                "full_fetch_success_count": 10,
                "full_fetch_failure_count": 2,
                "warnings": [],
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

    data: list[SourceResponse] = Field(
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
                        "pending_review": False,
                        "review_reason": None,
                        "config": {},
                        "last_scored_at": None,
                        "total_items": 0,
                        "schedule_interval": 3600,
                        "next_ingest_at": None,
                        "last_ingested_at": None,
                        "last_ingest_result": None,
                        "items_last_7d": 0,
                        "consecutive_failures": 0,
                        "last_error_at": None,
                        "last_error_message": None,
                        "last_job_id": None,
                        "needs_full_fetch": False,
                        "full_fetch_threshold": None,
                        "content_type": None,
                        "avg_content_length": None,
                        "quality_score": None,
                        "full_fetch_success_count": 0,
                        "full_fetch_failure_count": 0,
                        "warnings": [],
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


class ScheduleRequest(BaseModel):
    """Schedule configuration request."""

    interval: int = Field(..., ge=300, description="Ingest interval in seconds, minimum 300 (5 minutes)")


class ScheduleResponse(BaseModel):
    """Schedule configuration response."""

    source_id: str
    schedule_interval: int
    next_ingest_at: datetime | None = None
    message: str = "Schedule updated"


class TestResult(BaseModel):
    """Source test result."""

    source_id: str
    test_result: str  # "success" or "failed"
    response_time_ms: int | None = None
    items_found: int | None = None
    last_modified: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    suggestion: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DefaultsResponse(BaseModel):
    """Default configuration response."""

    default_fetch_interval: int
    updated_at: datetime | None = None


class DefaultsUpdate(BaseModel):
    """Default configuration update."""

    default_fetch_interval: int = Field(..., ge=300, description="Default fetch interval in seconds")


class ImportResponse(BaseModel):
    """Batch import response."""

    job_id: str
    status: str = "pending"
    message: str = "Import job created"


class ValidationResponse(BaseModel):
    """Source quality validation response."""

    source_id: str = Field(..., description="Source identifier")
    is_valid: bool = Field(..., description="Whether source passes quality validation")
    content_type: str = Field(
        ...,
        description="Content type: 'article', 'summary_only', 'empty', or 'unknown'"
    )
    sample_completeness: float = Field(
        ...,
        description="Sample completeness score (0.0-1.0)"
    )
    avg_content_length: int = Field(
        ...,
        description="Average content length in characters"
    )
    rejection_reason: str | None = Field(
        None,
        description="Reason for rejection if validation failed"
    )
    samples_analyzed: int = Field(
        0,
        description="Number of samples analyzed"
    )
