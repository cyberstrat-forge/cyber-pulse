from enum import StrEnum

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base
from .base import TimestampMixin


class ApiClientStatus(StrEnum):
    """API client status"""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class ApiClient(Base, TimestampMixin):
    """API client for authentication"""
    __tablename__ = "api_clients"

    client_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_key = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(
        SAEnum(ApiClientStatus, name="apiclientstatus"),
        nullable=False,
        default=ApiClientStatus.ACTIVE,
    )
    description = Column(Text, nullable=True)
    permissions = Column(JSONB, nullable=False, default=list)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
