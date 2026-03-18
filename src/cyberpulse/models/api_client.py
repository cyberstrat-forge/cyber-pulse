from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from ..database import Base
from .base import TimestampMixin


class ApiClientStatus(str, Enum):
    """API client status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ApiClient(Base, TimestampMixin):
    """API client for authentication"""
    __tablename__ = "api_clients"

    client_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_key = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="active")
    description = Column(Text, nullable=True)
    permissions = Column(JSONB, nullable=False, default=list)
    last_used_at = Column(DateTime, nullable=True)