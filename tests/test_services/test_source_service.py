import pytest
from datetime import datetime, timedelta, timezone

from cyberpulse.models import Source, SourceTier, SourceStatus
from cyberpulse.services import SourceService


@pytest.fixture
def source_service(db_session):
    """Create a SourceService instance."""
    return SourceService(db_session)


class TestAddSource:
    """Tests for add_source method."""

    def test_add_source(self, source_service):
        """Test adding a new source."""
        source, message = source_service.add_source(
            name="Test Blog",
            connector_type="rss",
            tier=SourceTier.T2,
            config={"url": "https://example.com/feed.xml"},
        )

        assert source is not None
        assert source.name == "Test Blog"
        assert source.connector_type == "rss"
        assert source.tier == SourceTier.T2
        assert source.status == SourceStatus.ACTIVE
        assert source.is_in_observation is True
        assert source.observation_until is not None
        assert source.source_id.startswith("src_")
        assert "created successfully" in message

    def test_add_source_with_default_tier(self, source_service):
        """Test adding source with default tier T2."""
        source, message = source_service.add_source(
            name="Default Tier Source",
            connector_type="rss",
        )

        assert source is not None
        assert source.tier == SourceTier.T2
        assert source.score == 50.0

    def test_add_source_with_custom_score(self, source_service):
        """Test adding source with custom score."""
        source, message = source_service.add_source(
            name="High Score Source",
            connector_type="api",
            score=85.0,
        )

        assert source is not None
        assert source.score == 85.0

    def test_add_duplicate_source(self, source_service):
        """Test adding a duplicate source returns None."""
        # Add first source
        source1, message1 = source_service.add_source(
            name="Duplicate Test",
            connector_type="rss",
        )
        assert source1 is not None

        # Try to add duplicate
        source2, message2 = source_service.add_source(
            name="Duplicate Test",
            connector_type="api",
        )

        assert source2 is None
        assert "already exists" in message2

    def test_add_source_observation_period(self, source_service):
        """Test that new sources have correct observation period."""
        source, _ = source_service.add_source(
            name="Observation Test",
            connector_type="rss",
        )

        assert source.is_in_observation is True
        assert source.observation_until is not None

        # Check observation period is approximately 30 days
        expected_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
        delta = abs((source.observation_until - expected_until).total_seconds())
        assert delta < 60  # Within 1 minute tolerance

    def test_generate_source_id(self, source_service):
        """Test source ID generation."""
        id1 = source_service.generate_source_id()
        id2 = source_service.generate_source_id()

        assert id1.startswith("src_")
        assert id2.startswith("src_")
        assert id1 != id2  # IDs should be unique
        assert len(id1) == 12  # "src_" + 8 characters


class TestUpdateSource:
    """Tests for update_source method."""

    def test_update_source(self, source_service):
        """Test updating a source."""
        source, _ = source_service.add_source(
            name="Update Test",
            connector_type="rss",
        )

        updated, message = source_service.update_source(
            source.source_id,
            tier=SourceTier.T1,
            score=75.0,
        )

        assert updated is not None
        assert updated.tier == SourceTier.T1
        assert updated.score == 75.0
        assert "updated successfully" in message

    def test_update_source_with_string_tier(self, source_service):
        """Test updating source with string tier value."""
        source, _ = source_service.add_source(
            name="String Tier Update",
            connector_type="rss",
        )

        updated, message = source_service.update_source(
            source.source_id,
            tier="T0",
        )

        assert updated is not None
        assert updated.tier == SourceTier.T0

    def test_update_source_with_string_status(self, source_service):
        """Test updating source with string status value."""
        source, _ = source_service.add_source(
            name="String Status Update",
            connector_type="rss",
        )

        updated, message = source_service.update_source(
            source.source_id,
            status="FROZEN",
        )

        assert updated is not None
        assert updated.status == SourceStatus.FROZEN

    def test_update_nonexistent_source(self, source_service):
        """Test updating a nonexistent source."""
        source, message = source_service.update_source(
            "src_nonexist",
            tier=SourceTier.T0,
        )

        assert source is None
        assert "not found" in message

    def test_update_source_config(self, source_service):
        """Test updating source config."""
        source, _ = source_service.add_source(
            name="Config Update Test",
            connector_type="api",
            config={"api_key": "old_key"},
        )

        updated, message = source_service.update_source(
            source.source_id,
            config={"api_key": "new_key", "endpoint": "https://api.example.com"},
        )

        assert updated is not None
        assert updated.config["api_key"] == "new_key"
        assert updated.config["endpoint"] == "https://api.example.com"


class TestRemoveSource:
    """Tests for remove_source method."""

    def test_remove_source(self, source_service):
        """Test soft deleting a source."""
        source, _ = source_service.add_source(
            name="Remove Test",
            connector_type="rss",
        )

        success, message = source_service.remove_source(source.source_id)

        assert success is True
        assert "removed successfully" in message

        # Verify status is REMOVED
        db_source = source_service.db.query(Source).filter(
            Source.source_id == source.source_id
        ).first()
        assert db_source.status == SourceStatus.REMOVED

    def test_remove_nonexistent_source(self, source_service):
        """Test removing a nonexistent source."""
        success, message = source_service.remove_source("src_nonexist")

        assert success is False
        assert "not found" in message

    def test_remove_already_removed_source(self, source_service):
        """Test removing an already removed source."""
        source, _ = source_service.add_source(
            name="Already Removed",
            connector_type="rss",
        )

        # Remove once
        source_service.remove_source(source.source_id)

        # Remove again
        success, message = source_service.remove_source(source.source_id)

        assert success is True
        assert "already removed" in message


class TestListSources:
    """Tests for list_sources method."""

    def test_list_sources(self, source_service):
        """Test listing all sources."""
        # Add multiple sources
        source_service.add_source("Source 1", "rss")
        source_service.add_source("Source 2", "api")
        source_service.add_source("Source 3", "web_scraper")

        sources = source_service.list_sources()

        assert len(sources) == 3

    def test_list_sources_by_tier(self, source_service):
        """Test filtering sources by tier."""
        source_service.add_source("T0 Source", "rss", tier=SourceTier.T0)
        source_service.add_source("T1 Source", "rss", tier=SourceTier.T1)
        source_service.add_source("T2 Source", "rss", tier=SourceTier.T2)

        t0_sources = source_service.list_sources(tier=SourceTier.T0)
        t1_sources = source_service.list_sources(tier=SourceTier.T1)

        assert len(t0_sources) == 1
        assert t0_sources[0].name == "T0 Source"
        assert len(t1_sources) == 1
        assert t1_sources[0].name == "T1 Source"

    def test_list_sources_by_status(self, source_service):
        """Test filtering sources by status."""
        source, _ = source_service.add_source("Active Source", "rss")
        frozen_source, _ = source_service.add_source("Frozen Source", "rss")
        source_service.update_source(frozen_source.source_id, status=SourceStatus.FROZEN)

        active_sources = source_service.list_sources(status=SourceStatus.ACTIVE)
        frozen_sources = source_service.list_sources(status=SourceStatus.FROZEN)

        assert len(active_sources) == 1
        assert active_sources[0].name == "Active Source"
        assert len(frozen_sources) == 1
        assert frozen_sources[0].name == "Frozen Source"

    def test_list_sources_pagination(self, source_service):
        """Test pagination of sources."""
        # Add 5 sources
        for i in range(5):
            source_service.add_source(f"Source {i}", "rss")

        # Test limit
        sources = source_service.list_sources(limit=3)
        assert len(sources) == 3

        # Test offset
        sources_offset = source_service.list_sources(limit=3, offset=3)
        assert len(sources_offset) == 2

    def test_list_sources_combined_filters(self, source_service):
        """Test combining tier and status filters."""
        source_service.add_source("T0 Active", "rss", tier=SourceTier.T0)
        t1_source, _ = source_service.add_source("T1 Frozen", "rss", tier=SourceTier.T1)
        source_service.update_source(t1_source.source_id, status=SourceStatus.FROZEN)
        source_service.add_source("T2 Active", "rss", tier=SourceTier.T2)

        sources = source_service.list_sources(tier=SourceTier.T1, status=SourceStatus.FROZEN)

        assert len(sources) == 1
        assert sources[0].name == "T1 Frozen"


class TestGetSourceStatistics:
    """Tests for get_source_statistics method."""

    def test_get_source_statistics(self, source_service):
        """Test getting source statistics."""
        source, _ = source_service.add_source(
            name="Stats Test",
            connector_type="rss",
            tier=SourceTier.T1,
            score=65.0,
        )

        stats = source_service.get_source_statistics(source.source_id)

        assert stats is not None
        assert stats["source_id"] == source.source_id
        assert stats["name"] == "Stats Test"
        assert stats["tier"] == "T1"
        assert stats["score"] == 65.0
        assert stats["status"] == "ACTIVE"
        assert stats["is_in_observation"] is True
        assert stats["total_items"] == 0
        assert stats["total_contents"] == 0

    def test_get_source_statistics_nonexistent(self, source_service):
        """Test getting statistics for nonexistent source."""
        stats = source_service.get_source_statistics("src_nonexist")

        assert stats is None


class TestBaseService:
    """Tests for BaseService methods."""

    def test_get_or_create_create(self, source_service):
        """Test get_or_create creates new record."""
        from cyberpulse.models import Source

        defaults = {
            "source_id": "src_test01",
            "connector_type": "rss",
            "tier": SourceTier.T2,
            "config": {},
        }

        source, created = source_service.get_or_create(
            Source,
            defaults=defaults,
            name="Get Or Create Test",
        )

        assert created is True
        assert source is not None
        assert source.name == "Get Or Create Test"
        assert source.connector_type == "rss"

    def test_get_or_create_get(self, source_service):
        """Test get_or_create gets existing record."""
        from cyberpulse.models import Source

        # Create first
        source_service.add_source("Existing Source", "rss")

        # Get existing
        source, created = source_service.get_or_create(
            Source,
            name="Existing Source",
        )

        assert created is False
        assert source is not None
        assert source.name == "Existing Source"