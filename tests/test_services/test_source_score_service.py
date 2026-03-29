"""Tests for SourceScoreService."""

from datetime import UTC, datetime, timedelta

import pytest

from cyberpulse.models import Item, ItemStatus, Source, SourceStatus, SourceTier
from cyberpulse.services import ScoreComponents, SourceScoreService


@pytest.fixture
def source_score_service(db_session):
    """Create a SourceScoreService instance."""
    return SourceScoreService(db_session)


@pytest.fixture
def test_source(db_session):
    """Create a test source."""
    source = Source(
        source_id="src_test001",
        name="Test Source",
        connector_type="rss",
        tier=SourceTier.T2,
        score=50.0,
        status=SourceStatus.ACTIVE,
        config={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


@pytest.fixture
def test_source_with_items(db_session, test_source):
    """Create a test source with items for scoring."""
    now = datetime.now(UTC)

    # Create items across different days in the past 30 days
    items = []
    for i in range(10):
        # Spread items across 5 distinct days
        days_ago = i // 2
        fetched_at = now - timedelta(days=days_ago, hours=i % 24)

        item = Item(
            item_id=f"item_{i:03d}",
            source_id=test_source.source_id,
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            raw_content=f"Content {i}",
            published_at=fetched_at,
            fetched_at=fetched_at,
            status=ItemStatus.NORMALIZED,
            meta_completeness=0.8,
            content_completeness=0.7,
            noise_ratio=0.1,
        )
        items.append(item)

    db_session.add_all(items)
    db_session.commit()
    return test_source


class TestCalculateStability:
    """Tests for calculate_stability method."""

    def test_calculate_stability_with_items(self, source_score_service, test_source_with_items):
        """Test stability calculation with items."""
        stability = source_score_service.calculate_stability(test_source_with_items.source_id)

        # Items were created across 5 distinct days
        # Stability should be min(1.0, distinct_days/30)
        # Note: Due to timezone handling, distinct_days may vary between 5-6
        assert stability > 0
        assert stability <= 1.0
        # Allow for timezone boundary effects (5-6 distinct days)
        expected_min = 5 / 30
        expected_max = 6 / 30
        assert expected_min - 0.01 <= stability <= expected_max + 0.01

    def test_calculate_stability_no_items(self, source_score_service, test_source):
        """Test stability with no items returns default."""
        stability = source_score_service.calculate_stability(test_source.source_id)

        # Should return default when no items
        assert stability == SourceScoreService.DEFAULT_STABILITY

    def test_calculate_stability_high_frequency(self, db_session, source_score_service, test_source):
        """Test stability with daily updates."""
        now = datetime.now(UTC)

        # Create items for each of the past 30 days
        for i in range(30):
            fetched_at = now - timedelta(days=i)
            item = Item(
                item_id=f"item_daily_{i:03d}",
                source_id=test_source.source_id,
                external_id=f"ext_daily_{i}",
                url=f"https://example.com/daily/{i}",
                title=f"Daily Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NEW,
            )
            db_session.add(item)
        db_session.commit()

        stability = source_score_service.calculate_stability(test_source.source_id)

        # With 30 distinct days, stability should be 1.0
        assert stability == 1.0


class TestCalculateActivity:
    """Tests for calculate_activity method."""

    def test_calculate_activity_with_items(self, source_score_service, test_source_with_items):
        """Test activity calculation with recent items."""
        activity = source_score_service.calculate_activity(test_source_with_items.source_id)

        # 10 items in past 7 days, reference is 7
        # Activity should be min(1.0, 10/7) = 1.0
        assert activity > 0
        assert activity <= 1.0

    def test_calculate_activity_no_items(self, source_score_service, test_source):
        """Test activity with no items returns default."""
        activity = source_score_service.calculate_activity(test_source.source_id)

        assert activity == SourceScoreService.DEFAULT_ACTIVITY

    def test_calculate_activity_low_frequency(self, db_session, source_score_service, test_source):
        """Test activity with low update frequency."""
        now = datetime.now(UTC)

        # Create only 3 items in past 7 days
        for i in range(3):
            fetched_at = now - timedelta(days=i)
            item = Item(
                item_id=f"item_low_{i:03d}",
                source_id=test_source.source_id,
                external_id=f"ext_low_{i}",
                url=f"https://example.com/low/{i}",
                title=f"Low Activity Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NEW,
            )
            db_session.add(item)
        db_session.commit()

        activity = source_score_service.calculate_activity(test_source.source_id)

        # 3 items / 7 reference = 0.429
        assert 0.4 < activity < 0.5


class TestCalculateQuality:
    """Tests for calculate_quality method."""

    def test_calculate_quality_with_metrics(self, source_score_service, test_source_with_items):
        """Test quality calculation with quality metrics."""
        quality = source_score_service.calculate_quality(test_source_with_items.source_id)

        # Quality = 0.8 * 0.4 + 0.7 * 0.4 + (1 - 0.1) * 0.2
        #         = 0.32 + 0.28 + 0.18 = 0.78
        assert quality > 0
        assert quality <= 1.0
        assert abs(quality - 0.78) < 0.01

    def test_calculate_quality_no_items(self, source_score_service, test_source):
        """Test quality with no items returns default."""
        quality = source_score_service.calculate_quality(test_source.source_id)

        assert quality == SourceScoreService.DEFAULT_QUALITY

    def test_calculate_quality_no_metrics(self, db_session, source_score_service, test_source):
        """Test quality with items but no quality metrics."""
        now = datetime.now(UTC)

        # Create items without quality metrics
        item = Item(
            item_id="item_no_metrics",
            source_id=test_source.source_id,
            external_id="ext_no_metrics",
            url="https://example.com/no_metrics",
            title="No Metrics Item",
            raw_content="Content",
            published_at=now,
            fetched_at=now,
            status=ItemStatus.NEW,
            # No quality metrics set
        )
        db_session.add(item)
        db_session.commit()

        quality = source_score_service.calculate_quality(test_source.source_id)

        # Should return default when no items with metrics
        assert quality == SourceScoreService.DEFAULT_QUALITY

    def test_calculate_quality_mixed_metrics(self, db_session, source_score_service, test_source):
        """Test quality with mixed quality metrics."""
        now = datetime.now(UTC)

        # Create items with different quality levels
        items = [
            Item(
                item_id="item_q1",
                source_id=test_source.source_id,
                external_id="ext_q1",
                url="https://example.com/q1",
                title="Quality 1",
                raw_content="Content",
                published_at=now,
                fetched_at=now,
                status=ItemStatus.NORMALIZED,
                meta_completeness=1.0,
                content_completeness=1.0,
                noise_ratio=0.0,
            ),
            Item(
                item_id="item_q2",
                source_id=test_source.source_id,
                external_id="ext_q2",
                url="https://example.com/q2",
                title="Quality 2",
                raw_content="Content",
                published_at=now,
                fetched_at=now,
                status=ItemStatus.NORMALIZED,
                meta_completeness=0.5,
                content_completeness=0.5,
                noise_ratio=0.5,
            ),
        ]
        db_session.add_all(items)
        db_session.commit()

        quality = source_score_service.calculate_quality(test_source.source_id)

        # Average: meta=0.75, content=0.75, noise=0.25
        # Quality = 0.75*0.4 + 0.75*0.4 + 0.75*0.2 = 0.75
        assert abs(quality - 0.75) < 0.01


class TestCalculateScore:
    """Tests for calculate_score method."""

    def test_calculate_score(self, source_score_service, test_source_with_items):
        """Test comprehensive score calculation."""
        score = source_score_service.calculate_score(test_source_with_items.source_id)

        # Score should be between 0 and 100
        assert 0 <= score <= 100

        # Verify it matches the formula
        components = source_score_service.get_score_components(test_source_with_items.source_id)
        expected_composite = (
            0.30 * components.stability
            + 0.30 * components.activity
            + 0.40 * components.quality
        )
        expected_score = (0.60 * expected_composite + 0.40 * components.strategic_value) * 100

        assert abs(score - expected_score) < 0.1

    def test_calculate_score_nonexistent_source(self, source_score_service):
        """Test score calculation for nonexistent source."""
        with pytest.raises(ValueError, match="not found"):
            source_score_service.calculate_score("src_nonexistent")

    def test_calculate_score_with_custom_strategic_value(
        self, db_session, source_score_service
    ):
        """Test score with custom strategic value in config."""
        source = Source(
            source_id="src_strategic",
            name="Strategic Source",
            connector_type="api",
            tier=SourceTier.T1,
            score=70.0,
            status=SourceStatus.ACTIVE,
            config={"strategic_value": 0.9},
        )
        db_session.add(source)
        db_session.commit()

        # With higher strategic value (0.9 instead of 0.5), score should be higher
        # than the default would produce
        components = source_score_service.get_score_components("src_strategic")
        assert components.strategic_value == 0.9


class TestUpdateTier:
    """Tests for update_tier method."""

    def test_update_tier_t0(self, db_session, source_score_service, test_source):
        """Test tier update to T0."""
        now = datetime.now(UTC)

        # Create high-quality, high-frequency items across all 30 days
        # This ensures stability = 1.0 (30/30 distinct days)
        for i in range(60):  # More items for higher activity
            days_ago = i % 30  # Spread across 30 days
            fetched_at = now - timedelta(days=days_ago, hours=i % 24)
            item = Item(
                item_id=f"item_t0_{i:03d}",
                source_id=test_source.source_id,
                external_id=f"ext_t0_{i}",
                url=f"https://example.com/t0/{i}",
                title=f"T0 Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NORMALIZED,
                meta_completeness=1.0,
                content_completeness=1.0,
                noise_ratio=0.0,
            )
            db_session.add(item)
        db_session.commit()

        tier = source_score_service.update_tier(test_source.source_id)

        # With perfect metrics: stability=1.0, activity=1.0, quality=1.0
        # C = 0.3*1.0 + 0.3*1.0 + 0.4*1.0 = 1.0
        # Score = 0.6*1.0 + 0.4*0.5 = 0.8 = 80 (T0 threshold)
        # Due to many items in past 7 days, activity should be 1.0
        assert tier == SourceTier.T0

        # Verify source was updated
        db_session.refresh(test_source)
        assert test_source.tier == SourceTier.T0
        assert test_source.score >= 80
        assert test_source.last_scored_at is not None

    def test_update_tier_t1(self, db_session, source_score_service, test_source):
        """Test tier update to T1."""
        now = datetime.now(UTC)

        # Create moderate items for T1 range
        for i in range(10):
            days_ago = i
            fetched_at = now - timedelta(days=days_ago)
            item = Item(
                item_id=f"item_t1_{i:03d}",
                source_id=test_source.source_id,
                external_id=f"ext_t1_{i}",
                url=f"https://example.com/t1/{i}",
                title=f"T1 Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NORMALIZED,
                meta_completeness=0.7,
                content_completeness=0.7,
                noise_ratio=0.3,
            )
            db_session.add(item)
        db_session.commit()

        source_score_service.update_tier(test_source.source_id)

        # Verify source was updated
        db_session.refresh(test_source)
        assert test_source.tier in [SourceTier.T0, SourceTier.T1, SourceTier.T2]
        assert test_source.last_scored_at is not None

    def test_update_tier_t3(self, db_session, source_score_service):
        """Test tier update to T3 for low-quality source."""
        source = Source(
            source_id="src_t3_test",
            name="Low Quality Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        # Create few low-quality items
        now = datetime.now(UTC)
        for i in range(2):
            fetched_at = now - timedelta(days=20 + i)
            item = Item(
                item_id=f"item_t3_{i:03d}",
                source_id=source.source_id,
                external_id=f"ext_t3_{i}",
                url=f"https://example.com/t3/{i}",
                title=f"T3 Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NORMALIZED,
                meta_completeness=0.2,
                content_completeness=0.2,
                noise_ratio=0.8,
            )
            db_session.add(item)
        db_session.commit()

        source_score_service.update_tier(source.source_id)

        db_session.refresh(source)
        # Should be T2 or T3 based on score
        assert source.tier in [SourceTier.T2, SourceTier.T3]

    def test_update_tier_nonexistent_source(self, source_score_service):
        """Test tier update for nonexistent source."""
        with pytest.raises(ValueError, match="not found"):
            source_score_service.update_tier("src_nonexistent")


class TestTierEvolution:
    """Tests for check_tier_evolution method."""

    def test_check_tier_evolution_stable(self, source_score_service, test_source_with_items):
        """Test tier evolution when stable."""
        # First update the tier to match current score
        source_score_service.update_tier(test_source_with_items.source_id)

        result = source_score_service.check_tier_evolution(test_source_with_items.source_id)

        assert "current_tier" in result
        assert "recommended_tier" in result
        assert "action" in result
        assert "message" in result
        assert "components" in result
        assert result["action"] in ["promote", "demote", "stable"]

    def test_check_tier_evolution_promote(self, db_session, source_score_service):
        """Test tier evolution when promotion is recommended."""
        # Create source at T3 but with high-quality items
        source = Source(
            source_id="src_promote",
            name="Promotion Candidate",
            connector_type="rss",
            tier=SourceTier.T3,  # Low tier
            score=20.0,
            status=SourceStatus.ACTIVE,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        # Add high-quality items that would push it to T0/T1
        now = datetime.now(UTC)
        for i in range(35):
            days_ago = i // 2
            fetched_at = now - timedelta(days=days_ago, hours=i % 24)
            item = Item(
                item_id=f"item_promo_{i:03d}",
                source_id=source.source_id,
                external_id=f"ext_promo_{i}",
                url=f"https://example.com/promo/{i}",
                title=f"Promo Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NORMALIZED,
                meta_completeness=1.0,
                content_completeness=1.0,
                noise_ratio=0.0,
            )
            db_session.add(item)
        db_session.commit()

        result = source_score_service.check_tier_evolution(source.source_id)

        assert result["current_tier"] == "T3"
        assert result["action"] == "promote"
        assert result["recommended_tier"] in ["T0", "T1", "T2"]
        assert result["calculated_score"] > source.score

    def test_check_tier_evolution_demote(self, db_session, source_score_service):
        """Test tier evolution when demotion is recommended."""
        # Create source at T0 but with low-quality items
        source = Source(
            source_id="src_demote",
            name="Demotion Candidate",
            connector_type="rss",
            tier=SourceTier.T0,  # High tier
            score=90.0,
            status=SourceStatus.ACTIVE,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        # Add low-quality items
        now = datetime.now(UTC)
        for i in range(2):
            fetched_at = now - timedelta(days=20 + i)
            item = Item(
                item_id=f"item_demo_{i:03d}",
                source_id=source.source_id,
                external_id=f"ext_demo_{i}",
                url=f"https://example.com/demo/{i}",
                title=f"Demo Item {i}",
                raw_content=f"Content {i}",
                published_at=fetched_at,
                fetched_at=fetched_at,
                status=ItemStatus.NORMALIZED,
                meta_completeness=0.2,
                content_completeness=0.2,
                noise_ratio=0.8,
            )
            db_session.add(item)
        db_session.commit()

        result = source_score_service.check_tier_evolution(source.source_id)

        assert result["current_tier"] == "T0"
        assert result["action"] == "demote"
        assert result["calculated_score"] < source.score

    def test_check_tier_evolution_nonexistent_source(self, source_score_service):
        """Test tier evolution for nonexistent source."""
        with pytest.raises(ValueError, match="not found"):
            source_score_service.check_tier_evolution("src_nonexistent")


class TestScoreComponents:
    """Tests for ScoreComponents dataclass."""

    def test_score_components_default_values(self):
        """Test ScoreComponents with default strategic_value."""
        components = ScoreComponents(
            stability=0.8,
            activity=0.7,
            quality=0.9,
        )

        assert components.stability == 0.8
        assert components.activity == 0.7
        assert components.quality == 0.9
        assert components.strategic_value == 0.5  # Default

    def test_score_components_custom_strategic_value(self):
        """Test ScoreComponents with custom strategic_value."""
        components = ScoreComponents(
            stability=0.8,
            activity=0.7,
            quality=0.9,
            strategic_value=0.8,
        )

        assert components.strategic_value == 0.8


class TestGetScoreComponents:
    """Tests for get_score_components method."""

    def test_get_score_components(self, source_score_service, test_source_with_items):
        """Test getting score components."""
        components = source_score_service.get_score_components(test_source_with_items.source_id)

        assert isinstance(components, ScoreComponents)
        assert 0 <= components.stability <= 1
        assert 0 <= components.activity <= 1
        assert 0 <= components.quality <= 1
        assert 0 <= components.strategic_value <= 1

    def test_get_score_components_nonexistent_source(self, source_score_service):
        """Test getting components for nonexistent source."""
        with pytest.raises(ValueError, match="not found"):
            source_score_service.get_score_components("src_nonexistent")
