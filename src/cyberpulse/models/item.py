from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .source import Source


class ItemStatus(StrEnum):
    """Item processing status"""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PENDING_FULL_FETCH = "PENDING_FULL_FETCH"  # Waiting for full content fetch
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"


class Item(Base, TimestampMixin):
    """Raw item from source with normalized content"""

    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sources.source_id"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(1024), index=True)
    title: Mapped[str] = mapped_column(String(1024))

    # Raw content from source
    raw_content: Mapped[str | None] = mapped_column(Text)

    # Normalized content (filled after normalization)
    normalized_title: Mapped[str | None] = mapped_column(String(1024))
    normalized_body: Mapped[str | None] = mapped_column(Text)
    canonical_hash: Mapped[str | None] = mapped_column(String(64))  # For deduplication

    # Metadata
    published_at: Mapped[datetime] = mapped_column(index=True)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[ItemStatus] = mapped_column(default=ItemStatus.NEW)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Quality metrics (filled after quality check)
    meta_completeness: Mapped[float | None] = mapped_column()
    content_completeness: Mapped[float | None] = mapped_column()
    noise_ratio: Mapped[float | None] = mapped_column()
    word_count: Mapped[int | None] = mapped_column()

    # Full content fetch status
    full_fetch_attempted: Mapped[bool] = mapped_column(default=False)
    full_fetch_succeeded: Mapped[bool | None] = mapped_column()

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
        Index("ix_items_canonical_hash", "canonical_hash"),
    )

    # Relationships
    source: Mapped["Source"] = relationship(backref="items", lazy="select")
