"""Diagnose API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status of a system component."""

    status: str  # "connected", "disconnected", "error"
    message: str | None = None


class SourceStatistics(BaseModel):
    """Source statistics."""

    active: int = 0
    frozen: int = 0
    pending_review: int = 0


class JobStatistics(BaseModel):
    """Job statistics."""

    pending: int = 0
    running: int = 0
    failed_24h: int = 0


class ItemStatistics(BaseModel):
    """Item statistics."""

    total: int = 0
    last_24h: int = 0


class ErrorByType(BaseModel):
    """Error count by type."""

    error_type: str
    count: int


class TopErrorSource(BaseModel):
    """Top source with errors."""

    source_id: str
    source_name: str
    error_count: int


class ErrorStatistics(BaseModel):
    """Error statistics."""

    total_24h: int = 0
    by_type: list[dict[str, Any]] = []
    top_sources: list[dict[str, Any]] = []


class DiagnoseResponse(BaseModel):
    """System diagnose response."""

    status: str = Field(
        ..., description="Overall system status: healthy, degraded, unhealthy"
    )
    version: str
    components: dict[str, str]
    statistics: dict[str, Any]
    server_timestamp: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "1.3.0",
                "components": {
                    "database": "connected",
                    "redis": "connected",
                    "scheduler": "active"
                },
                "statistics": {
                    "sources": {
                        "active": 120,
                        "frozen": 15,
                        "pending_review": 5
                    },
                    "jobs": {
                        "pending": 3,
                        "running": 1,
                        "failed_24h": 12
                    },
                    "items": {
                        "total": 5420,
                        "last_24h": 156
                    },
                    "errors": {
                        "total_24h": 280,
                        "by_type": [
                            {"error_type": "connection", "count": 120},
                            {"error_type": "http_403", "count": 80}
                        ],
                        "top_sources": [
                            {
                                "source_id": "src_xxx",
                                "source_name": "Example Blog",
                                "error_count": 15,
                            }
                        ]
                    }
                },
                "server_timestamp": "2026-03-25T15:00:00Z"
            }
        }
    }
