"""Log API schemas."""

from datetime import datetime

from pydantic import BaseModel


class LogEntry(BaseModel):
    """Single log entry."""

    timestamp: datetime
    level: str  # "ERROR", "WARNING", "INFO"
    module: str
    source_id: str | None = None
    source_name: str | None = None
    error_type: str | None = None
    message: str
    retry_count: int = 0
    suggestion: str | None = None

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    """Log list response."""

    data: list[LogEntry]
    count: int
    server_timestamp: datetime


class ErrorTypeSummary(BaseModel):
    """Error type summary for statistics."""

    error_type: str
    count: int


class ErrorStatistics(BaseModel):
    """Error statistics."""

    total_24h: int
    by_type: list[ErrorTypeSummary]
    top_sources: list[dict]
