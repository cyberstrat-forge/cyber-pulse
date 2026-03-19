"""Source score service for calculating and updating source quality scores."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import func, distinct

from .base import BaseService
from ..models import Source, SourceTier, Item

logger = logging.getLogger(__name__)


@dataclass
class ScoreComponents:
    """Score components for source quality calculation."""

    stability: float  # Cs: Source stability (0-1)
    activity: float  # Cf: Update frequency (0-1)
    quality: float  # Cq: Content quality (0-1)
    strategic_value: float = 0.5  # V: Strategic value (default 0.5, reserved for cyber-nexus feedback)


class SourceScoreService(BaseService):
    """Service for calculating and updating source scores.

    Score Formula:
        C = 0.30 * Cs + 0.30 * Cf + 0.40 * Cq
        Score = 0.60 * C + 0.40 * V
        Final Score = Score * 100 (scale 0-100)

    Where:
        - Cs (Stability): min(1.0, updates_in_past_30_days / 30)
        - Cf (Activity): min(1.0, weekly_items / REFERENCE_VALUE)
          REFERENCE_VALUE = 7 (assuming 1 item/day as baseline)
        - Cq (Quality): meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
        - V (Strategic Value): Default 0.5 (reserved for cyber-nexus feedback)

    Tier Mapping:
        - T0: Score >= 80
        - T1: 60 <= Score < 80
        - T2: 40 <= Score < 60
        - T3: Score < 40
    """

    # Weight configuration for composite score
    WEIGHTS = {
        "stability": 0.30,
        "activity": 0.30,
        "quality": 0.40,
    }

    # Reference value for activity calculation (1 item/day baseline)
    ACTIVITY_REFERENCE_VALUE = 7

    # Weights for composite quality calculation
    QUALITY_WEIGHTS = {
        "meta_completeness": 0.4,
        "content_completeness": 0.4,
        "noise_ratio": 0.2,  # Applied as (1 - noise_ratio)
    }

    # Default values when data is unavailable
    DEFAULT_STABILITY = 0.5
    DEFAULT_ACTIVITY = 0.5
    DEFAULT_QUALITY = 0.5
    DEFAULT_STRATEGIC_VALUE = 0.5

    def calculate_score(self, source_id: str) -> float:
        """Calculate comprehensive score for a source.

        Args:
            source_id: Source ID to calculate score for

        Returns:
            Final score on 0-100 scale

        Raises:
            ValueError: If source not found
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            raise ValueError(f"Source with ID '{source_id}' not found")

        # Calculate individual components
        stability = self.calculate_stability(source_id)
        activity = self.calculate_activity(source_id)
        quality = self.calculate_quality(source_id)

        # Get strategic value (default or from source config)
        strategic_value = self._get_strategic_value(source)

        # Calculate composite score C
        composite = (
            self.WEIGHTS["stability"] * stability
            + self.WEIGHTS["activity"] * activity
            + self.WEIGHTS["quality"] * quality
        )

        # Calculate final score: Score = 0.60 * C + 0.40 * V
        score = 0.60 * composite + 0.40 * strategic_value

        # Scale to 0-100
        final_score = score * 100

        # Clamp to valid range
        return max(0.0, min(100.0, final_score))

    def calculate_stability(self, source_id: str) -> float:
        """Calculate source stability (Cs).

        Stability measures how consistently the source is updated.
        Cs = min(1.0, updates_in_past_30_days / 30)

        Args:
            source_id: Source ID

        Returns:
            Stability score (0-1)
        """
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Count distinct days with fetched items in the past 30 days
        result = (
            self.db.query(
                func.count(distinct(func.date(Item.fetched_at))).label("update_days")
            )
            .filter(
                Item.source_id == source_id,
                Item.fetched_at >= thirty_days_ago,
            )
            .first()
        )

        if result is None or result.update_days is None or result.update_days == 0:
            return self.DEFAULT_STABILITY

        # Calculate stability: updates / 30, capped at 1.0
        stability = min(1.0, result.update_days / 30.0)
        return stability

    def calculate_activity(self, source_id: str) -> float:
        """Calculate update activity (Cf).

        Activity measures the frequency of item updates.
        Cf = min(1.0, weekly_items / REFERENCE_VALUE)

        Args:
            source_id: Source ID

        Returns:
            Activity score (0-1)
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        # Count items fetched in the past 7 days
        item_count = (
            self.db.query(func.count(Item.item_id))
            .filter(
                Item.source_id == source_id,
                Item.fetched_at >= seven_days_ago,
            )
            .scalar()
        )

        if item_count is None or item_count == 0:
            return self.DEFAULT_ACTIVITY

        # Calculate activity: items / reference, capped at 1.0
        activity = min(1.0, item_count / self.ACTIVITY_REFERENCE_VALUE)
        return activity

    def calculate_quality(self, source_id: str) -> float:
        """Calculate content quality (Cq).

        Quality is based on item quality metrics from normalized items.
        Cq = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2

        Args:
            source_id: Source ID

        Returns:
            Quality score (0-1)
        """
        # Get items with quality metrics (normalized items)
        items = (
            self.db.query(
                func.avg(Item.meta_completeness).label("avg_meta"),
                func.avg(Item.content_completeness).label("avg_content"),
                func.avg(Item.noise_ratio).label("avg_noise"),
                func.count(Item.item_id).label("count"),
            )
            .filter(
                Item.source_id == source_id,
                Item.meta_completeness.isnot(None),
                Item.content_completeness.isnot(None),
                Item.noise_ratio.isnot(None),
            )
            .first()
        )

        if items is None or items.count == 0:
            return self.DEFAULT_QUALITY

        # Calculate quality components
        avg_meta = items.avg_meta or 0.0
        avg_content = items.avg_content or 0.0
        avg_noise = items.avg_noise or 0.0

        # Cq = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
        quality = (
            avg_meta * self.QUALITY_WEIGHTS["meta_completeness"]
            + avg_content * self.QUALITY_WEIGHTS["content_completeness"]
            + (1 - avg_noise) * self.QUALITY_WEIGHTS["noise_ratio"]
        )

        # Clamp to valid range
        return max(0.0, min(1.0, quality))

    def update_tier(self, source_id: str) -> SourceTier:
        """Update tier based on score.

        Calculates the current score and updates the source's tier accordingly.
        Also updates the source's score and last_scored_at timestamp.

        Args:
            source_id: Source ID

        Returns:
            The new tier

        Raises:
            ValueError: If source not found
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            raise ValueError(f"Source with ID '{source_id}' not found")

        # Calculate new score
        score = self.calculate_score(source_id)

        # Determine tier based on score
        if score >= 80:
            new_tier = SourceTier.T0
        elif score >= 60:
            new_tier = SourceTier.T1
        elif score >= 40:
            new_tier = SourceTier.T2
        else:
            new_tier = SourceTier.T3

        # Update source
        source.score = score  # type: ignore[assignment]
        source.tier = new_tier  # type: ignore[assignment]
        source.last_scored_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        self.db.commit()
        self.db.refresh(source)

        logger.info(
            f"Updated source {source_id}: score={score:.2f}, tier={new_tier.value}"
        )

        return new_tier

    def check_tier_evolution(self, source_id: str) -> Dict:
        """Check if source should be promoted/demoted.

        Analyzes the source's current tier against its calculated score
        and provides recommendations for tier changes.

        Args:
            source_id: Source ID

        Returns:
            Dictionary with evolution analysis:
                - current_tier: Current tier
                - recommended_tier: Tier based on current score
                - current_score: Current stored score
                - calculated_score: Newly calculated score
                - action: "promote", "demote", or "stable"
                - message: Human-readable recommendation

        Raises:
            ValueError: If source not found
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            raise ValueError(f"Source with ID '{source_id}' not found")

        # Calculate current score
        calculated_score = self.calculate_score(source_id)

        # Determine recommended tier
        if calculated_score >= 80:
            recommended_tier = SourceTier.T0
        elif calculated_score >= 60:
            recommended_tier = SourceTier.T1
        elif calculated_score >= 40:
            recommended_tier = SourceTier.T2
        else:
            recommended_tier = SourceTier.T3

        # Determine action
        tier_order = {SourceTier.T3: 0, SourceTier.T2: 1, SourceTier.T1: 2, SourceTier.T0: 3}
        current_order = tier_order[SourceTier(source.tier)]  # type: ignore[arg-type]
        recommended_order = tier_order[recommended_tier]

        if recommended_order > current_order:
            action = "promote"
            message = (
                f"Source qualifies for promotion from {source.tier.value} to {recommended_tier.value} "
                f"(score: {calculated_score:.2f})"
            )
        elif recommended_order < current_order:
            action = "demote"
            message = (
                f"Source should be demoted from {source.tier.value} to {recommended_tier.value} "
                f"(score: {calculated_score:.2f})"
            )
        else:
            action = "stable"
            message = f"Source tier {source.tier.value} is consistent with score {calculated_score:.2f}"

        # Get score components for detailed analysis
        components = self.get_score_components(source_id)

        return {
            "source_id": source_id,
            "source_name": source.name,
            "current_tier": source.tier.value,
            "recommended_tier": recommended_tier.value,
            "current_score": source.score,
            "calculated_score": calculated_score,
            "action": action,
            "message": message,
            "components": {
                "stability": components.stability,
                "activity": components.activity,
                "quality": components.quality,
                "strategic_value": components.strategic_value,
            },
            "is_in_observation": source.is_in_observation,
        }

    def get_score_components(self, source_id: str) -> ScoreComponents:
        """Get individual score components for a source.

        Args:
            source_id: Source ID

        Returns:
            ScoreComponents dataclass with individual component values

        Raises:
            ValueError: If source not found
        """
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            raise ValueError(f"Source with ID '{source_id}' not found")

        return ScoreComponents(
            stability=self.calculate_stability(source_id),
            activity=self.calculate_activity(source_id),
            quality=self.calculate_quality(source_id),
            strategic_value=self._get_strategic_value(source),
        )

    def _get_strategic_value(self, source: Source) -> float:
        """Get strategic value for a source.

        Strategic value is reserved for cyber-nexus feedback.
        Currently returns default value, but can be extended to read from
        source config or external system.

        Args:
            source: Source object

        Returns:
            Strategic value (0-1)
        """
        # Check if strategic_value is configured in source config
        config = source.config  # type: ignore[assignment]
        if config and "strategic_value" in config:
            value = config["strategic_value"]
            if isinstance(value, (int, float)) and 0 <= value <= 1:
                return float(value)

        return self.DEFAULT_STRATEGIC_VALUE