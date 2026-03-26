import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

from .base import BaseService
from ..models import Source, SourceTier, SourceStatus


class SourceService(BaseService):
    """Service for managing intelligence sources"""

    OBSERVATION_PERIOD_DAYS = 30

    # Tier-score consistency per design spec:
    # T0: score >= 80, T1: 60 <= score < 80, T2: 40 <= score < 60, T3: score < 40
    TIER_SCORE_RANGES = {
        SourceTier.T0: (80.0, float("inf")),
        SourceTier.T1: (60.0, 80.0),
        SourceTier.T2: (40.0, 60.0),
        SourceTier.T3: (0.0, 40.0),
    }

    # Default score for each tier (middle of range)
    TIER_DEFAULT_SCORES = {
        SourceTier.T0: 90.0,
        SourceTier.T1: 70.0,
        SourceTier.T2: 50.0,
        SourceTier.T3: 20.0,
    }

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison.

        Removes trailing slashes, converts to lowercase, and removes
        common variations to enable URL deduplication.

        Note: Converts https:// to http:// for deduplication purposes.
        Most RSS feeds are accessible via both http and https, and treating
        them as the same prevents duplicate source entries. If a source
        genuinely has different content on http vs https, the feed_url
        can be manually verified.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL string
        """
        if not url:
            return ""

        # Convert to lowercase
        normalized = url.lower().strip()

        # Remove trailing slash
        if normalized.endswith("/"):
            normalized = normalized[:-1]

        # Normalize protocol to http for deduplication
        # (Most RSS feeds are accessible via both http and https)
        if normalized.startswith("https://"):
            normalized = "http://" + normalized[8:]
        elif normalized.startswith("www."):
            normalized = "http://" + normalized[4:]

        # Remove common URL parameters that don't affect content
        # (keep the path but remove tracking params like ?utm_source=...)
        if "?" in normalized:
            normalized = normalized.split("?")[0]

        return normalized

    def _get_tier_for_score(self, score: float) -> SourceTier:
        """Determine the appropriate tier for a given score.

        Args:
            score: Quality score

        Returns:
            The tier that matches this score
        """
        if score >= 80:
            return SourceTier.T0
        elif score >= 60:
            return SourceTier.T1
        elif score >= 40:
            return SourceTier.T2
        else:
            return SourceTier.T3

    def _validate_tier_score(self, tier: SourceTier, score: float) -> None:
        """Validate tier-score consistency per design spec.

        Args:
            tier: Source tier level
            score: Source quality score

        Raises:
            ValueError: If score doesn't match tier requirements
        """
        min_score, max_score = self.TIER_SCORE_RANGES[tier]
        if not (min_score <= score < max_score):
            raise ValueError(
                f"Tier {tier.value} requires score in [{min_score}, {max_score}), got {score}"
            )

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
        tier: Optional[SourceTier] = None,
        config: Optional[Dict[str, Any]] = None,
        score: Optional[float] = None,
    ) -> Tuple[Optional[Source], str]:
        """Add a new source.

        New sources enter observation period by default.

        Args:
            name: Source name (must be unique)
            connector_type: Type of connector (rss, api, web_scraper, media_api)
            tier: Source tier (optional, derived from score if not provided)
            config: Connector configuration
            score: Initial score (optional, defaults to tier's default if tier provided)

        Returns:
            Tuple of (source, message) where source is None if duplicate
        """
        # Check for duplicate name
        existing = self.db.query(Source).filter(Source.name == name).first()
        if existing:
            return None, f"Source with name '{name}' already exists"

        # Check for duplicate URL in config (for RSS and web_scraper types)
        if config and connector_type in ("rss", "web_scraper"):
            feed_url = config.get("feed_url") or config.get("url")
            if feed_url:
                # Check for existing source with same URL
                existing_url = (
                    self.db.query(Source)
                    .filter(Source.connector_type == connector_type)
                    .filter(Source.status != SourceStatus.REMOVED)
                    .all()
                )
                for src in existing_url:
                    src_url = src.config.get("feed_url") or src.config.get("url") if src.config else None
                    if src_url and self._normalize_url(src_url) == self._normalize_url(feed_url):
                        return None, f"Source with URL '{feed_url}' already exists as '{src.name}'"

        # Determine tier and score based on what was provided
        if score is not None and tier is None:
            # Score provided, derive tier from score
            tier = self._get_tier_for_score(score)
        elif tier is not None and score is None:
            # Tier provided, use tier's default score
            score = self.TIER_DEFAULT_SCORES[tier]
        elif tier is None and score is None:
            # Neither provided, use defaults
            tier = SourceTier.T2
            score = self.TIER_DEFAULT_SCORES[SourceTier.T2]
        # else: both provided, keep as is (user's choice)

        # Create new source with observation period
        source_id = self.generate_source_id()
        now = datetime.now(timezone.utc)
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

        # Prevent updates to removed sources
        if source.status == SourceStatus.REMOVED:
            return None, f"Cannot update removed source '{source_id}'"

        # Handle tier update
        if "tier" in kwargs and isinstance(kwargs["tier"], str):
            kwargs["tier"] = SourceTier(kwargs["tier"])

        # Handle status update
        if "status" in kwargs and isinstance(kwargs["status"], str):
            kwargs["status"] = SourceStatus(kwargs["status"])

        # Auto-adjust tier/score to maintain consistency (tier is derived from score)
        if "score" in kwargs:
            # Score update takes precedence - auto-adjust tier
            kwargs["tier"] = self._get_tier_for_score(kwargs["score"])
        elif "tier" in kwargs:
            # Only tier updated - adjust score to match tier's default
            kwargs["score"] = self.TIER_DEFAULT_SCORES[kwargs["tier"]]

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

        source.status = SourceStatus.REMOVED  # type: ignore[assignment]
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