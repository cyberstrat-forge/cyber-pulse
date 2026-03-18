from sqlalchemy import Column, String, Integer, Float, Boolean, Text, Enum, DateTime, JSON
from enum import Enum as PyEnum
from ..database import Base
from .base import TimestampMixin


class SourceTier(str, PyEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(str, PyEnum):
    """Source status"""
    ACTIVE = "active"
    FROZEN = "frozen"
    REMOVED = "removed"


class Source(Base, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    connector_type = Column(String(50), nullable=False)
    tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
    score = Column(Float, nullable=False, default=50.0)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    is_in_observation = Column(Boolean, nullable=False, default=False)
    observation_until = Column(DateTime, nullable=True)
    pending_review = Column(Boolean, nullable=False, default=False)
    review_reason = Column(Text, nullable=True)
    fetch_interval = Column(Integer, nullable=True)
    config = Column(JSON, nullable=False, default=dict)

    # Statistics
    last_fetched_at = Column(DateTime, nullable=True)
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)
    total_contents = Column(Integer, nullable=False, default=0)