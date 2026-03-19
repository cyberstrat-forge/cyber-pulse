"""Integration tests for scheduler-dramatiq connection."""
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from cyberpulse.scheduler.jobs import collect_source, run_scheduled_collection, update_source_scores


class TestCollectSource:
    """Tests for collect_source job."""

    def test_collect_source_triggers_ingest_task(self) -> None:
        """Test that collect_source triggers Dramatiq ingest_source task."""
        with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
            mock_ingest.send = MagicMock()

            result = collect_source("src_test123")

            mock_ingest.send.assert_called_once_with("src_test123")
            assert result["status"] == "queued"
            assert result["source_id"] == "src_test123"


class TestRunScheduledCollection:
    """Tests for run_scheduled_collection job."""

    def test_scheduled_collection_queues_active_sources(self, db_session: Session) -> None:
        """Test that only active sources are queued."""
        from cyberpulse.models import Source, SourceTier, SourceStatus
        from cyberpulse.services import SourceService

        # Create test sources
        service = SourceService(db_session)
        service.add_source("Active Source", "rss", tier=SourceTier.T2)
        service.add_source("Frozen Source", "rss", tier=SourceTier.T2)

        # Freeze one source
        db_session.query(Source).filter(
            Source.name == "Frozen Source"
        ).update({"status": SourceStatus.FROZEN})
        db_session.commit()

        # Patch SessionLocal to return our test session
        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session_local.return_value = db_session

            with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
                mock_ingest.send = MagicMock()

                result = run_scheduled_collection()

                # Only active source should be queued
                assert result["sources_count"] == 1
                mock_ingest.send.assert_called_once()

    def test_scheduled_collection_handles_connection_error(self, db_session: Session) -> None:
        """Test that connection errors are handled gracefully."""
        from cyberpulse.models import SourceTier
        from cyberpulse.services import SourceService

        # Create test source
        service = SourceService(db_session)
        service.add_source("Test Source", "rss", tier=SourceTier.T2)
        db_session.commit()

        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session_local.return_value = db_session

            with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
                # Simulate connection error
                mock_ingest.send.side_effect = ConnectionError("Redis connection failed")

                result = run_scheduled_collection()

                assert result["status"] == "completed"
                assert result["sources_count"] == 0
                assert result["failed_count"] == 1

    def test_update_source_scores(self, db_session: Session) -> None:
        """Test that source scores are updated."""
        from cyberpulse.models import SourceTier
        from cyberpulse.services import SourceService

        # Create test source
        service = SourceService(db_session)
        source, _ = service.add_source("Test Source", "rss", tier=SourceTier.T2)
        db_session.commit()

        # Patch SessionLocal to return our test session
        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session_local.return_value = db_session

            # Patch SourceScoreService to verify update_tier is called
            with patch("cyberpulse.scheduler.jobs.SourceScoreService") as mock_score_service:
                mock_score_instance = MagicMock()
                mock_score_service.return_value = mock_score_instance

                result = update_source_scores()

                assert result["status"] == "completed"
                # Verify SourceScoreService.update_tier was called for the source
                mock_score_instance.update_tier.assert_called_once_with(source.source_id)

    def test_update_source_scores_handles_value_error(self, db_session: Session) -> None:
        """Test that ValueError during score update is handled gracefully."""
        from cyberpulse.models import SourceTier
        from cyberpulse.services import SourceService

        # Create test source
        service = SourceService(db_session)
        service.add_source("Test Source", "rss", tier=SourceTier.T2)
        db_session.commit()

        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session_local.return_value = db_session

            with patch("cyberpulse.scheduler.jobs.SourceScoreService") as mock_score_service:
                mock_score_instance = MagicMock()
                mock_score_instance.update_tier.side_effect = ValueError("No items to score")
                mock_score_service.return_value = mock_score_instance

                result = update_source_scores()

                assert result["status"] == "completed"
                assert result["sources_updated"] == 0
                assert result["failed_count"] == 1