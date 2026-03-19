"""Tests for CLI source commands."""

from unittest.mock import patch, MagicMock, AsyncMock
from typer.testing import CliRunner

from cyberpulse.cli.app import app
from cyberpulse.models import SourceTier, SourceStatus

runner = CliRunner()


class TestSourceList:
    """Tests for source list command."""

    def test_source_list_empty(self, db_session) -> None:
        """Test listing sources when empty."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list"])

        assert result.exit_code == 0
        assert "No sources found" in result.stdout

    def test_source_list_with_sources(self, db_session) -> None:
        """Test listing sources with data."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source1, _ = service.add_source("Source 1", "rss", tier=SourceTier.T1)
        source2, _ = service.add_source("Source 2", "api", tier=SourceTier.T2)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list"])

        assert result.exit_code == 0
        # Check for source IDs since name column may be truncated in output
        assert source1.source_id in result.stdout
        assert source2.source_id in result.stdout
        assert "T1" in result.stdout
        assert "T2" in result.stdout

    def test_source_list_filter_by_tier(self, db_session) -> None:
        """Test filtering sources by tier."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        t0_source, _ = service.add_source("T0 Source", "rss", tier=SourceTier.T0)
        t1_source, _ = service.add_source("T1 Source", "rss", tier=SourceTier.T1)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--tier", "T0"])

        assert result.exit_code == 0
        # Check for source ID since name column may be truncated
        assert t0_source.source_id in result.stdout
        assert t1_source.source_id not in result.stdout

    def test_source_list_filter_by_status(self, db_session) -> None:
        """Test filtering sources by status."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        active_source, _ = service.add_source("Active Source", "rss")
        frozen_source, _ = service.add_source("Frozen Source", "rss")
        service.update_source(frozen_source.source_id, status=SourceStatus.FROZEN)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--status", "active"])

        assert result.exit_code == 0
        # Check for source ID since name column may be truncated
        assert active_source.source_id in result.stdout
        assert frozen_source.source_id not in result.stdout

    def test_source_list_invalid_tier(self, db_session) -> None:
        """Test listing with invalid tier filter."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--tier", "T9"])

        assert result.exit_code == 1
        assert "Invalid tier" in result.stdout

    def test_source_list_invalid_status(self, db_session) -> None:
        """Test listing with invalid status filter."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--status", "invalid"])

        assert result.exit_code == 1
        assert "Invalid status" in result.stdout


class TestSourceAdd:
    """Tests for source add command."""

    def test_source_add_success(self, db_session) -> None:
        """Test adding a source successfully."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            # Mock the connector to avoid network calls
            mock_connector = MagicMock()
            mock_connector.validate_config.return_value = True
            mock_connector.fetch = AsyncMock(return_value=[
                {"title": "Test Item", "url": "https://example.com/1", "content": "Test content"}
            ])

            with patch("cyberpulse.cli.commands.source.get_connector", return_value=mock_connector):
                # Use --no-test to skip onboarding
                result = runner.invoke(app, [
                    "source", "add", "Test Source", "rss", "https://example.com/feed.xml",
                    "--no-test"
                ])

        assert result.exit_code == 0
        assert "created successfully" in result.stdout

    def test_source_add_with_onboarding(self, db_session) -> None:
        """Test adding a source with onboarding flow."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            # Mock the connector
            mock_connector = MagicMock()
            mock_connector.validate_config.return_value = True
            mock_connector.fetch = AsyncMock(return_value=[
                {
                    "title": "Test Item 1",
                    "url": "https://example.com/1",
                    "content": "Test content with some length to score well",
                    "published_at": "2024-01-01",
                }
                for _ in range(5)
            ])

            with patch("cyberpulse.cli.commands.source.get_connector", return_value=mock_connector):
                # Input: "n" for tier suggestion prompt (keep default tier)
                result = runner.invoke(app, [
                    "source", "add", "Test Source", "rss", "https://example.com/feed.xml",
                    "--test"
                ], input="n\n")

        assert result.exit_code == 0
        assert "created successfully" in result.stdout
        assert "Step 1" in result.stdout
        assert "Step 2" in result.stdout

    def test_source_add_duplicate(self, db_session) -> None:
        """Test adding a duplicate source."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        service.add_source("Existing Source", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "add", "Existing Source", "rss", "https://example.com/feed.xml",
                "--no-test"
            ])

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_source_add_invalid_connector(self, db_session) -> None:
        """Test adding with invalid connector type."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "add", "Test Source", "invalid", "https://example.com/feed.xml",
                "--no-test"
            ])

        assert result.exit_code == 1
        assert "Invalid connector type" in result.stdout

    def test_source_add_invalid_tier(self, db_session) -> None:
        """Test adding with invalid tier."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "add", "Test Source", "rss", "https://example.com/feed.xml",
                "--tier", "T9", "--no-test"
            ])

        assert result.exit_code == 1
        assert "Invalid tier" in result.stdout

    def test_source_add_connection_failed(self, db_session) -> None:
        """Test adding when connection test fails and user cancels."""
        from cyberpulse.services import ConnectorError

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            mock_connector = MagicMock()
            mock_connector.validate_config.return_value = True
            mock_connector.fetch = AsyncMock(side_effect=ConnectorError("Connection refused"))

            with patch("cyberpulse.cli.commands.source.get_connector", return_value=mock_connector):
                # Input: "n" for "Add source anyway?" prompt
                result = runner.invoke(app, [
                    "source", "add", "Test Source", "rss", "https://example.com/feed.xml",
                    "--test"
                ], input="n\n")

        # Should exit cleanly when user says no to "add anyway"
        assert result.exit_code == 0
        assert "Connection failed" in result.stdout
        # Source should not be created
        assert "created successfully" not in result.stdout


class TestSourceUpdate:
    """Tests for source update command."""

    def test_source_update_tier(self, db_session) -> None:
        """Test updating source tier."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Update Test", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "update", source.source_id, "--tier", "T0"
            ])

        assert result.exit_code == 0
        assert "updated successfully" in result.stdout

    def test_source_update_status(self, db_session) -> None:
        """Test updating source status."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Status Update Test", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "update", source.source_id, "--status", "frozen"
            ])

        assert result.exit_code == 0
        assert "updated successfully" in result.stdout

    def test_source_update_no_options(self, db_session) -> None:
        """Test updating without options."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("No Update Test", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "update", source.source_id])

        assert result.exit_code == 0
        assert "No updates specified" in result.stdout

    def test_source_update_invalid_id(self, db_session) -> None:
        """Test updating with invalid source ID."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "update", "invalid_id", "--tier", "T0"])

        assert result.exit_code == 1
        assert "Invalid source ID format" in result.stdout

    def test_source_update_not_found(self, db_session) -> None:
        """Test updating non-existent source."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "update", "src_12345678", "--tier", "T0"])

        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestSourceRemove:
    """Tests for source remove command."""

    def test_source_remove_success(self, db_session) -> None:
        """Test removing a source."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Remove Test", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "remove", source.source_id, "--force"
            ])

        assert result.exit_code == 0
        assert "removed successfully" in result.stdout

    def test_source_remove_with_confirmation(self, db_session) -> None:
        """Test removing a source with confirmation."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Confirm Remove", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "remove", source.source_id
            ], input="y\n")

        assert result.exit_code == 0
        assert "removed successfully" in result.stdout

    def test_source_remove_cancel(self, db_session) -> None:
        """Test cancelling source removal."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Cancel Remove", "rss")

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "remove", source.source_id
            ], input="n\n")

        assert result.exit_code == 0

    def test_source_remove_invalid_id(self, db_session) -> None:
        """Test removing with invalid source ID."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "remove", "invalid_id", "--force"])

        assert result.exit_code == 1
        assert "Invalid source ID format" in result.stdout

    def test_source_remove_not_found(self, db_session) -> None:
        """Test removing non-existent source."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "remove", "src_12345678", "--force"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_source_remove_already_removed(self, db_session) -> None:
        """Test removing already removed source."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Already Removed", "rss")
        service.remove_source(source.source_id)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, [
                "source", "remove", source.source_id, "--force"
            ])

        assert result.exit_code == 0
        assert "already removed" in result.stdout


class TestSourceTest:
    """Tests for source test command."""

    def test_source_test_success(self, db_session) -> None:
        """Test testing a source successfully."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Test Source", "rss", config={"feed_url": "https://example.com/feed.xml"})

        mock_connector = MagicMock()
        mock_connector.validate_config.return_value = True
        mock_connector.fetch = AsyncMock(return_value=[
            {"title": "Test Item", "url": "https://example.com/1", "content": "Content"}
        ])

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            with patch("cyberpulse.cli.commands.source.get_connector", return_value=mock_connector):
                result = runner.invoke(app, ["source", "test", source.source_id])

        assert result.exit_code == 0
        assert "Testing source" in result.stdout
        assert "Connection Test" in result.stdout

    def test_source_test_invalid_id(self, db_session) -> None:
        """Test testing with invalid source ID."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "test", "invalid_id"])

        assert result.exit_code == 1
        assert "Invalid source ID format" in result.stdout

    def test_source_test_not_found(self, db_session) -> None:
        """Test testing non-existent source."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "test", "src_12345678"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_source_test_connection_failed(self, db_session) -> None:
        """Test testing source when connection fails."""
        from cyberpulse.services import SourceService, ConnectorError

        service = SourceService(db_session)
        source, _ = service.add_source("Failed Source", "rss", config={"feed_url": "https://example.com/feed.xml"})

        mock_connector = MagicMock()
        mock_connector.validate_config.return_value = True
        mock_connector.fetch = AsyncMock(side_effect=ConnectorError("Connection refused"))

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            with patch("cyberpulse.cli.commands.source.get_connector", return_value=mock_connector):
                result = runner.invoke(app, ["source", "test", source.source_id])

        assert result.exit_code == 1
        assert "Connection failed" in result.stdout


class TestSourceStats:
    """Tests for source stats command."""

    def test_source_stats_single_source(self, db_session) -> None:
        """Test showing stats for a single source."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        source, _ = service.add_source("Stats Test", "rss", tier=SourceTier.T1, score=75.0)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "stats", source.source_id])

        assert result.exit_code == 0
        assert "Stats Test" in result.stdout
        assert "T1" in result.stdout
        assert "75.0" in result.stdout

    def test_source_stats_all_sources(self, db_session) -> None:
        """Test showing stats for all sources."""
        from cyberpulse.services import SourceService

        service = SourceService(db_session)
        service.add_source("Source A", "rss", tier=SourceTier.T0)
        service.add_source("Source B", "api", tier=SourceTier.T1)
        service.add_source("Source C", "rss", tier=SourceTier.T2)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "stats"])

        assert result.exit_code == 0
        assert "Total Sources" in result.stdout
        assert "3" in result.stdout
        assert "Tier Distribution" in result.stdout

    def test_source_stats_empty(self, db_session) -> None:
        """Test showing stats when no sources."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "stats"])

        assert result.exit_code == 0
        assert "No sources found" in result.stdout

    def test_source_stats_invalid_id(self, db_session) -> None:
        """Test showing stats with invalid source ID."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "stats", "invalid_id"])

        assert result.exit_code == 1
        assert "Invalid source ID format" in result.stdout

    def test_source_stats_not_found(self, db_session) -> None:
        """Test showing stats for non-existent source."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "stats", "src_12345678"])

        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestSourceIDValidation:
    """Tests for source ID validation."""

    def test_validate_source_id_valid(self) -> None:
        """Test valid source ID validation."""
        from cyberpulse.cli.commands.source import _validate_source_id

        assert _validate_source_id("src_12345678") is True
        assert _validate_source_id("src_abcdef12") is True
        assert _validate_source_id("src_ABCDEF12") is False  # lowercase only
        assert _validate_source_id("src_123") is False  # too short
        assert _validate_source_id("src_1234567890") is False  # too long
        assert _validate_source_id("source_12345678") is False  # wrong prefix
        assert _validate_source_id("12345678") is False  # no prefix


class TestTierForScore:
    """Tests for tier calculation from score."""

    def test_get_tier_for_score(self) -> None:
        """Test tier calculation from quality score."""
        from cyberpulse.cli.commands.source import _get_tier_for_score

        assert _get_tier_for_score(85.0) == SourceTier.T0
        assert _get_tier_for_score(80.0) == SourceTier.T0
        assert _get_tier_for_score(79.9) == SourceTier.T1
        assert _get_tier_for_score(65.0) == SourceTier.T1
        assert _get_tier_for_score(60.0) == SourceTier.T1
        assert _get_tier_for_score(59.9) == SourceTier.T2
        assert _get_tier_for_score(45.0) == SourceTier.T2
        assert _get_tier_for_score(40.0) == SourceTier.T2
        assert _get_tier_for_score(39.9) == SourceTier.T3
        assert _get_tier_for_score(0.0) == SourceTier.T3


class TestSampleQualityAssessment:
    """Tests for sample quality assessment."""

    def test_assess_sample_quality_high(self) -> None:
        """Test quality assessment with high quality samples."""
        from cyberpulse.cli.commands.source import _assess_sample_quality

        items = [
            {
                "title": "Test Title",
                "url": "https://example.com/1",
                "content": "x" * 200,
                "published_at": "2024-01-01",
                "author": "Author",
            }
            for _ in range(5)
        ]

        score = _assess_sample_quality(items)
        assert score >= 80.0  # High quality

    def test_assess_sample_quality_low(self) -> None:
        """Test quality assessment with low quality samples."""
        from cyberpulse.cli.commands.source import _assess_sample_quality

        items = [{"title": "", "content": "", "url": ""} for _ in range(5)]

        score = _assess_sample_quality(items)
        assert score < 40.0  # Low quality

    def test_assess_sample_quality_empty(self) -> None:
        """Test quality assessment with no items."""
        from cyberpulse.cli.commands.source import _assess_sample_quality

        score = _assess_sample_quality([])
        assert score == 0.0

    def test_assess_sample_quality_partial(self) -> None:
        """Test quality assessment with partial items."""
        from cyberpulse.cli.commands.source import _assess_sample_quality

        items = [
            {"title": "Title", "url": "https://example.com/1", "content": "Short"},
            {"title": "", "url": "", "content": ""},
        ]

        score = _assess_sample_quality(items)
        # One good item (partial) + one empty item averages to low-medium quality
        assert 10.0 <= score <= 40.0