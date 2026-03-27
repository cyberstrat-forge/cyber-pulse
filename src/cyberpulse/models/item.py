from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin


class ItemStatus(StrEnum):
    """Item processing status"""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"


class Item(Base, TimestampMixin):
    """Raw item from source with normalized content"""

    __tablename__ = "items"

    item_id = Column(String(64), primary_key=True, index=True)
    source_id = Column(
        String(64), ForeignKey("sources.source_id"), nullable=False, index=True
    )
    external_id = Column(String(255), nullable=False, index=True)
    url = Column(String(1024), nullable=False, index=True)
    title = Column(String(1024), nullable=False)

    # Raw content from source
    raw_content = Column(Text, nullable=True)

    # Normalized content (filled after normalization)
    normalized_title = Column(String(1024), nullable=True)
    normalized_body = Column(Text, nullable=True)
    canonical_hash = Column(String(64), nullable=True)  # For deduplication

    # Metadata
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
    status = Column(
        SAEnum(ItemStatus, name="itemstatus"),
        nullable=False,
        default=ItemStatus.NEW,
    )
    raw_metadata = Column(JSONB, nullable=False, default=dict)

    # Quality metrics (filled after quality check)
    meta_completeness = Column(Float, nullable=True)
    content_completeness = Column(Float, nullable=True)
    noise_ratio = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)
    language = Column(String(10), nullable=True)

    # Full content fetch status
    full_fetch_attempted = Column(Boolean, nullable=False, default=False)
    full_fetch_succeeded = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
        Index("ix_items_canonical_hash", "canonical_hash"),
    )

    # Relationships
    source = relationship("Source", backref="items", lazy="select")
