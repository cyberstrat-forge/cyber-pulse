from sqlalchemy import Column, String, Text, DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from ..database import Base
from .base import TimestampMixin


class ItemStatus(str, Enum):
    """Item processing status"""
    NEW = "new"
    NORMALIZED = "normalized"
    MAPPED = "mapped"
    REJECTED = "rejected"


class Item(Base, TimestampMixin):
    """Raw item from source"""
    __tablename__ = "items"

    item_id = Column(String(64), primary_key=True, index=True)
    source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=False, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    url = Column(String(1024), nullable=False, index=True)
    title = Column(String(1024), nullable=False)
    raw_content = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="new")
    raw_metadata = Column(JSONB, nullable=False, default=dict)

    # Quality metrics (filled after normalization)
    meta_completeness = Column(Float, nullable=True)
    content_completeness = Column(Float, nullable=True)
    noise_ratio = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
    )