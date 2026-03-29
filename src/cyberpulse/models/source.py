from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .job import Job


class SourceTier(StrEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(StrEnum):
    """Source status"""
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    REMOVED = "REMOVED"


class Source(Base, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    connector_type: Mapped[str] = mapped_column(String(50))
    tier: Mapped[SourceTier] = mapped_column(default=SourceTier.T2)
    score: Mapped[float] = mapped_column(default=50.0)
    status: Mapped[SourceStatus] = mapped_column(default=SourceStatus.ACTIVE)
    pending_review: Mapped[bool] = mapped_column(default=False)
    review_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Statistics
    last_scored_at: Mapped[datetime | None] = mapped_column()
    total_items: Mapped[int] = mapped_column(default=0)

    # Failure tracking
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error_at: Mapped[datetime | None] = mapped_column()

    # Full content fetch configuration
    needs_full_fetch: Mapped[bool] = mapped_column(default=False)
    full_fetch_threshold: Mapped[float | None] = mapped_column(default=0.7)

    # Source quality markers
    content_type: Mapped[str | None] = mapped_column(String(20))
    # 'full' | 'summary' | 'mixed'
    avg_content_length: Mapped[int | None] = mapped_column()
    quality_score: Mapped[float | None] = mapped_column(default=50.0)

    # Full fetch statistics
    full_fetch_success_count: Mapped[int] = mapped_column(default=0)
    full_fetch_failure_count: Mapped[int] = mapped_column(default=0)

    # Scheduling fields
    # seconds, null = not scheduled
    schedule_interval: Mapped[int | None] = mapped_column()
    next_ingest_at: Mapped[datetime | None] = mapped_column()
    last_ingested_at: Mapped[datetime | None] = mapped_column()

    # Error tracking fields
    last_error_message: Mapped[str | None] = mapped_column(String(255))
    last_job_id: Mapped[str | None] = mapped_column(String(64))

    # Collection statistics
    items_last_7d: Mapped[int] = mapped_column(default=0)
    last_ingest_result: Mapped[str | None] = mapped_column(String(20))
    # success, partial, failed

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(back_populates="source")
