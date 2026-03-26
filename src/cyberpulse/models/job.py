"""Job model for tracking async task execution."""

from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, String, Integer, Text, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .source import Source


class JobType(str, PyEnum):
    """Job type enumeration."""
    INGEST = "ingest"
    IMPORT = "import"


class JobStatus(str, PyEnum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base, TimestampMixin):
    """Job tracks async task execution."""
    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True, index=True)
    type = Column(SAEnum(JobType, name="jobtype"), nullable=False)
    status = Column(SAEnum(JobStatus, name="jobstatus"), nullable=False, default=JobStatus.PENDING)

    # For ingest jobs
    source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=True)

    # For import jobs
    file_name = Column(String(255), nullable=True)

    # Results and error info
    result = Column(JSONB, nullable=True)
    error_type = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Tracking
    retry_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    source = relationship("Source", back_populates="jobs")