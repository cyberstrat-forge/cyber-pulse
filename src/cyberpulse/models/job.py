"""Job model for tracking async task execution."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .source import Source


class JobType(StrEnum):
    """Job type enumeration."""
    INGEST = "INGEST"
    IMPORT = "IMPORT"


class JobStatus(StrEnum):
    """Job status enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base, TimestampMixin):
    """Job tracks async task execution."""
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    type: Mapped[JobType] = mapped_column()
    status: Mapped[JobStatus] = mapped_column(default=JobStatus.PENDING)

    # For ingest jobs
    source_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sources.source_id")
    )

    # For import jobs
    file_name: Mapped[str | None] = mapped_column(String(255))

    # Results and error info
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_type: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Tracking
    retry_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()

    # Relationships
    source: Mapped["Source | None"] = relationship(back_populates="jobs")
