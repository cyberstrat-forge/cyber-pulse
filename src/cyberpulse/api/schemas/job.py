"""Job API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Job response."""
    job_id: str
    type: str  # "ingest" or "import"
    status: str  # "pending", "running", "completed", "failed"
    source_id: str | None = None
    source_name: str | None = None
    file_name: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    retry_count: int = 0
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Job list response."""
    data: list[JobResponse]
    count: int
    server_timestamp: datetime


class JobCreate(BaseModel):
    """Job creation request."""
    source_id: str = Field(..., description="Source ID to ingest")


class JobCreatedResponse(BaseModel):
    """Job creation response."""
    job_id: str
    type: str
    status: str
    source_id: str
    source_name: str | None = None
    message: str = "Job created and queued"
