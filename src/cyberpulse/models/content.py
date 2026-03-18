from sqlalchemy import Column, String, Text, DateTime, Integer, Index
from enum import Enum
from ..database import Base
from .base import TimestampMixin


class ContentStatus(str, Enum):
    """Content status"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class Content(Base, TimestampMixin):
    """Deduplicated content entity"""
    __tablename__ = "contents"

    content_id = Column(String(64), primary_key=True, index=True)
    canonical_hash = Column(String(64), nullable=False, index=True, unique=True)
    normalized_title = Column(String(1024), nullable=False)
    normalized_body = Column(Text, nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    source_count = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="active")

    __table_args__ = (
        Index("ix_contents_first_seen", "first_seen_at"),
    )