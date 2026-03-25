# tests/test_tasks/test_ingestion_enhanced.py
"""Tests for enhanced ingestion tasks."""

import pytest
from unittest.mock import patch

from cyberpulse.models import Source, SourceStatus
from cyberpulse.services.connector_service import ConnectorError


class TestIngestionFailureTracking:
    """Test ingestion failure tracking."""

    def test_skips_frozen_source(self, db_session_no_rollback):
        """Test that frozen sources are skipped."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source

        source = Source(
            source_id="src_frozen01",
            name="Frozen Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.FROZEN,
            consecutive_failures=5,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        # Patch SessionLocal to return the test session
        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback):
            # Should not raise and should not try to fetch
            ingest_source("src_frozen01")

    def test_increments_consecutive_failures(self, db_engine, db_session_no_rollback):
        """Test that consecutive_failures is incremented on error."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from sqlalchemy.orm import Session

        source = Source(
            source_id="src_fail01",
            name="Fail Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=0,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 404")

            with pytest.raises(ConnectorError):
                ingest_source("src_fail01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_fail01").first()
            assert updated is not None
            assert updated.consecutive_failures == 1
            assert updated.last_error_at is not None

    def test_freezes_after_max_failures(self, db_engine, db_session_no_rollback):
        """Test that source is frozen after MAX_CONSECUTIVE_FAILURES."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source, MAX_CONSECUTIVE_FAILURES
        from sqlalchemy.orm import Session

        source = Source(
            source_id="src_freeze01",
            name="To Freeze Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=MAX_CONSECUTIVE_FAILURES - 1,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 404")

            with pytest.raises(ConnectorError):
                ingest_source("src_freeze01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_freeze01").first()
            assert updated is not None
            assert updated.status == SourceStatus.FROZEN
            assert "连续采集失败" in updated.review_reason

    def test_resets_failures_on_success(self, db_engine, db_session_no_rollback):
        """Test that consecutive_failures is reset on successful fetch."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult
        from sqlalchemy.orm import Session

        source = Source(
            source_id="src_success01",
            name="Success Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=3,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=None)

            ingest_source("src_success01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_success01").first()
            assert updated is not None
            assert updated.consecutive_failures == 0

    def test_updates_feed_url_on_redirect(self, db_engine, db_session_no_rollback):
        """Test that feed_url is updated on permanent redirect."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult
        from sqlalchemy.orm import Session

        source = Source(
            source_id="src_redirect01",
            name="Redirect Source",
            connector_type="rss",
            config={"feed_url": "https://old.example.com/feed/"},
            status=SourceStatus.ACTIVE,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        redirect_info = {
            "original_url": "https://old.example.com/feed/",
            "final_url": "https://new.example.com/feed/",
            "status_code": 301,
        }

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=redirect_info)

            ingest_source("src_redirect01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_redirect01").first()
            assert updated is not None
            assert updated.config["feed_url"] == "https://new.example.com/feed/"

    def test_temporary_redirect_does_not_update_url(self, db_engine, db_session_no_rollback):
        """Test that 302/307 redirects are followed but URL is not updated."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult
        from sqlalchemy.orm import Session

        source = Source(
            source_id="src_temp_redirect01",
            name="Temp Redirect Source",
            connector_type="rss",
            config={"feed_url": "https://old.example.com/feed/"},
            status=SourceStatus.ACTIVE,
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        # 302 temporary redirect
        redirect_info = {
            "original_url": "https://old.example.com/feed/",
            "final_url": "https://new.example.com/feed/",
            "status_code": 302,
        }

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=redirect_info)

            ingest_source("src_temp_redirect01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_temp_redirect01").first()
            assert updated is not None
            # URL should NOT be updated for temporary redirect
            assert updated.config["feed_url"] == "https://old.example.com/feed/"

    def test_consecutive_failures_boundary(self, db_engine, db_session_no_rollback):
        """Test consecutive_failures at boundary values (4 and 5)."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source, MAX_CONSECUTIVE_FAILURES
        from sqlalchemy.orm import Session

        # Test at MAX - 1 (should not freeze)
        source = Source(
            source_id="src_boundary01",
            name="Boundary Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=MAX_CONSECUTIVE_FAILURES - 2,  # 3
        )
        db_session_no_rollback.add(source)
        db_session_no_rollback.commit()

        with patch('cyberpulse.tasks.ingestion_tasks.SessionLocal', return_value=db_session_no_rollback), \
             patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 500")

            with pytest.raises(ConnectorError):
                ingest_source("src_boundary01")

        # Use a new session to verify the changes
        with Session(db_engine) as new_session:
            updated = new_session.query(Source).filter(Source.source_id == "src_boundary01").first()
            assert updated is not None
            # After 1 failure, should be at 4 (MAX - 1), not frozen
            assert updated.consecutive_failures == MAX_CONSECUTIVE_FAILURES - 1
            assert updated.status == SourceStatus.ACTIVE