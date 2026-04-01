"""Job API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ...models.job import JobTrigger


class JobResponse(BaseModel):
    """Job response."""
    job_id: str
    type: str  # "INGEST" or "IMPORT"
    status: str  # "PENDING", "RUNNING", "COMPLETED", "FAILED"
    source_id: str | None = None
    source_name: str | None = None
    trigger: JobTrigger | None = None  # Trigger source (manual/scheduler/create)
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


class JobDeleteResponse(BaseModel):
    """Job deletion response."""
    deleted: str
    message: str = "Job deleted successfully"


class JobRetryResponse(BaseModel):
    """Job retry response."""
    job_id: str
    status: str
    retry_count: int
    message: str = "Job queued for retry"


class JobCleanupResponse(BaseModel):
    """Job cleanup response."""
    deleted_count: int
    threshold_days: int
    message: str = "Jobs cleaned up successfully"


class SourceCleanupResponse(BaseModel):
    """Source cleanup response."""
    deleted_sources: int
    deleted_items: int
    deleted_jobs: int
    message: str = "REMOVED sources cleaned up successfully"
