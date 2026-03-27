from sqlalchemy import Column, DateTime, func


class TimestampMixin:
    """Timestamp mixin for created_at and updated_at"""

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
