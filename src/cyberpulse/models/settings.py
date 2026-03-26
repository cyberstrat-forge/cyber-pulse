"""Settings model for runtime configuration."""

from sqlalchemy import Column, String, Text

from ..database import Base
from .base import TimestampMixin


class Settings(Base, TimestampMixin):
    """Runtime settings stored in database."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
