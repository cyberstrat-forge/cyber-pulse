import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_

from .base import BaseService
from ..models import Source, SourceTier, SourceStatus


class SourceService(BaseService):
    """Service for managing intelligence sources"""

    OBSERVATION_PERIOD_DAYS = 30

    def generate_source_id(self) -> str:
        """Generate a unique source ID.

        Format: src_{uuid8}
        """
        uuid_str = str(uuid.uuid4()).replace("-", "")[:8]
        return f"src_{uuid_str}"

    def add_source(
        self,
        name: str,
        connector_type: str,
        tier: SourceTier = SourceTier.T2,
        config: Optional[Dict[str, Any]] = None,
        score: float = 50.0,
    ) -> Tuple[Optional[Source], str]:
        """Add a new source.

        New sources enter observation period by default.

        Args:
            name: Source name (must be unique)
            connector_type: Type of connector (rss, api, web_scraper, media_api)
            tier: Source tier (default T2)
            config: Connector configuration
            score: Initial score (default 50.0)

        Returns:
            Tuple of (source, message) where source is None if duplicate
        """
        # Check for duplicate name
        existing = self.db.query(Source).filter(Source.name == name).first()
        if existing:
            return None, f"Source with name '{name}' already exists"

        # Create new source with observation period
        source_id = self.generate_source_id()
        now = datetime.utcnow()
        observation_until = now + timedelta(days=self.OBSERVATION_PERIOD_DAYS)

        source = Source(
            source_id=source_id,
            name=name,
            connector_type=connector_type,
            tier=tier,
            score=score,
            status=SourceStatus.ACTIVE,
            is_in_observation=True,
            observation_until=observation_until,
            config=config or {},
        )

        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)

        return source, f"Source '{name}' created successfully with ID {source_id}"

    def update_source(
        self, source_id: str, **kwargs
    ) -> Tuple[Optional[Source], str]:
        """Update a source.

        Args:
            source_id: Source ID to update
            **kwargs: Fields to update

        Returns:
            Tuple of (source, message)
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return None, f"Source with ID '{source_id}' not found"

        # Handle tier update
        if "tier" in kwargs and isinstance(kwargs["tier"], str):
            kwargs["tier"] = SourceTier(kwargs["tier"])

        # Handle status update
        if "status" in kwargs and isinstance(kwargs["status"], str):
            kwargs["status"] = SourceStatus(kwargs["status"])

        # Update allowed fields
        allowed_fields = {
            "name", "connector_type", "tier", "score", "status",
            "is_in_observation", "observation_until", "pending_review",
            "review_reason", "fetch_interval", "config",
        }

        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(source, key, value)

        self.db.commit()
        self.db.refresh(source)

        return source, f"Source '{source.name}' updated successfully"

    def remove_source(self, source_id: str) -> Tuple[bool, str]:
        """Soft delete a source by setting status to REMOVED.

        Args:
            source_id: Source ID to remove

        Returns:
            Tuple of (success, message)
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return False, f"Source with ID '{source_id}' not found"

        if source.status == SourceStatus.REMOVED:
            return True, f"Source '{source.name}' is already removed"

        source.status = SourceStatus.REMOVED
        self.db.commit()

        return True, f"Source '{source.name}' removed successfully"

    def list_sources(
        self,
        tier: Optional[SourceTier] = None,
        status: Optional[SourceStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Source]:
        """List sources with optional filtering.

        Args:
            tier: Filter by tier
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of Source objects
        """
        query = self.db.query(Source)

        if tier:
            query = query.filter(Source.tier == tier)

        if status:
            query = query.filter(Source.status == status)

        return query.order_by(Source.created_at.desc()).offset(offset).limit(limit).all()

    def get_source_statistics(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a source.

        Args:
            source_id: Source ID

        Returns:
            Dictionary with statistics or None if not found
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return None

        return {
            "source_id": source.source_id,
            "name": source.name,
            "tier": source.tier.value,
            "score": source.score,
            "status": source.status.value,
            "is_in_observation": source.is_in_observation,
            "observation_until": source.observation_until.isoformat() if source.observation_until else None,
            "total_items": source.total_items,
            "total_contents": source.total_contents,
            "last_fetched_at": source.last_fetched_at.isoformat() if source.last_fetched_at else None,
            "last_scored_at": source.last_scored_at.isoformat() if source.last_scored_at else None,
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "updated_at": source.updated_at.isoformat() if source.updated_at else None,
        }