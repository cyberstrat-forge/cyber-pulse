from typing import TYPE_CHECKING
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, Enum, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .job import Job


class SourceTier(str, PyEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(str, PyEnum):
    """Source status"""
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    REMOVED = "REMOVED"


class Source(Base, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    connector_type = Column(String(50), nullable=False)
    tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
    score = Column(Float, nullable=False, default=50.0)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    pending_review = Column(Boolean, nullable=False, default=False)
    review_reason = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False, default=dict)

    # Statistics
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)

    # Failure tracking
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error_at = Column(DateTime, nullable=True)

    # Full content fetch configuration
    needs_full_fetch = Column(Boolean, nullable=False, default=False)
    full_fetch_threshold = Column(Float, nullable=True, default=0.7)

    # Source quality markers
    content_type = Column(String(20), nullable=True)  # 'full' | 'summary' | 'mixed'
    avg_content_length = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True, default=50.0)

    # Full fetch statistics
    full_fetch_success_count = Column(Integer, nullable=False, default=0)
    full_fetch_failure_count = Column(Integer, nullable=False, default=0)

    # Scheduling fields
    schedule_interval = Column(Integer, nullable=True)  # seconds, null = not scheduled
    next_ingest_at = Column(DateTime, nullable=True)
    last_ingested_at = Column(DateTime, nullable=True)

    # Error tracking fields
    last_error_message = Column(String(255), nullable=True)
    last_job_id = Column(String(64), nullable=True)

    # Collection statistics
    items_last_7d = Column(Integer, nullable=False, default=0)
    last_ingest_result = Column(String(20), nullable=True)  # success, partial, failed

    # Relationships
    jobs = relationship("Job", back_populates="source")