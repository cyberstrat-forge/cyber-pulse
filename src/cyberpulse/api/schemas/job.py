"""Job API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Job response."""
    job_id: str
    type: str  # "ingest" or "import"
    status: str  # "pending", "running", "completed", "failed"
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    file_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Job list response."""
    data: List[JobResponse]
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
    source_name: Optional[str] = None
    message: str = "Job created and queued"