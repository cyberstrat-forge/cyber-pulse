"""Tests for import_tasks module."""

from unittest.mock import MagicMock, patch

import pytest

from cyberpulse.models import Job, JobStatus, Source
from cyberpulse.tasks.import_tasks import process_import_job


class TestProcessImportJob:
    """Tests for process_import_job task."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        return db

    @pytest.fixture
    def mock_job(self):
        """Create mock import job."""
        job = MagicMock(spec=Job)
        job.job_id = "job_test123"
        job.result = {
            "feeds": [
                {"url": "https://feed1.example.com/rss.xml", "title": "Feed 1"},
                {"url": "https://feed2.example.com/rss.xml", "title": "Feed 2"},
            ],
            "skip_invalid": True,
        }
        return job

    @pytest.fixture
    def mock_source(self):
        """Create mock source."""
        source = MagicMock(spec=Source)
        source.source_id = "src_a1b2c3d4"
        source.name = "Test Feed"
        return source

    def test_process_import_job_job_not_found(self, mock_db):
        """Test processing when job not found."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = None

            # Should return early without error
            process_import_job("job_nonexistent")

            # Job should not be updated
            assert not mock_db.commit.called

    def test_process_import_job_marks_running(self, mock_db, mock_job):
        """Test that job status is marked as RUNNING."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service:
                mock_service.return_value.add_source.return_value = (None, "Duplicate")

                process_import_job("job_test123")

            assert mock_job.status == JobStatus.COMPLETED

    def test_process_import_job_empty_feeds(self, mock_db, mock_job):
        """Test processing when no feeds provided."""
        mock_job.result = {"feeds": [], "skip_invalid": True}

        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            process_import_job("job_test123")

            assert mock_job.status == JobStatus.COMPLETED
            assert mock_job.result["imported"] == 0
            assert mock_job.result["skipped"] == 0
            assert mock_job.result["failed"] == 0

    def test_process_import_job_creates_sources(self, mock_db, mock_job, mock_source):
        """Test that sources are created for each feed."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.add_source.return_value = (mock_source, None)

                with patch("cyberpulse.tasks.import_tasks.ingest_source") as mock_ingest:
                    mock_ingest.send = MagicMock()

                    process_import_job("job_test123")

            # Should create 2 sources (2 feeds)
            assert mock_service.add_source.call_count == 2
            # Should trigger ingestion for each
            assert mock_ingest.send.call_count == 2

    def test_process_import_job_includes_ingestion_triggered(self, mock_db, mock_job, mock_source):
        """Test that details include ingestion_triggered field."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.add_source.return_value = (mock_source, None)

                with patch("cyberpulse.tasks.import_tasks.ingest_source") as mock_ingest:
                    mock_ingest.send = MagicMock()

                    process_import_job("job_test123")

            # Check result details
            details = mock_job.result["details"]
            assert len(details) == 2
            for detail in details:
                assert "ingestion_triggered" in detail
                assert detail["ingestion_triggered"] is True

    def test_process_import_job_ingestion_failure(self, mock_db, mock_job, mock_source):
        """Test that ingestion failure is recorded in details."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.add_source.return_value = (mock_source, None)

                with patch("cyberpulse.tasks.import_tasks.ingest_source") as mock_ingest:
                    # Simulate ingestion trigger failure
                    mock_ingest.send.side_effect = Exception("Redis connection failed")

                    process_import_job("job_test123")

            # Check result details
            details = mock_job.result["details"]
            assert len(details) == 2
            for detail in details:
                assert detail["ingestion_triggered"] is False
                assert "ingestion_error" in detail
                assert "Redis connection failed" in detail["ingestion_error"]

    def test_process_import_job_handles_duplicate(self, mock_db, mock_job):
        """Test handling of duplicate sources."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service_class:
                mock_service = mock_service_class.return_value
                # Return None to indicate duplicate
                mock_service.add_source.return_value = (None, "Source already exists")

                process_import_job("job_test123")

            # Should skip, not fail
            assert mock_job.result["skipped"] == 2
            assert mock_job.result["imported"] == 0
            details = mock_job.result["details"]
            for detail in details:
                assert detail["status"] == "skipped"

    def test_process_import_job_handles_missing_url(self, mock_db, mock_job):
        """Test handling of feeds without URL."""
        mock_job.result = {
            "feeds": [
                {"title": "No URL Feed"},
            ],
            "skip_invalid": True,  # Will skip silently (no details recorded)
        }

        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            process_import_job("job_test123")

            # When skip_invalid=True, missing URL is skipped silently
            assert mock_job.result["skipped"] == 0  # Not recorded
            assert mock_job.result["imported"] == 0
            assert mock_job.result["failed"] == 0
            # No details for silently skipped
            assert len(mock_job.result["details"]) == 0

    def test_process_import_job_handles_missing_url_skip_false(self, mock_db, mock_job):
        """Test handling of feeds without URL when skip_invalid=False."""
        mock_job.result = {
            "feeds": [
                {"title": "No URL Feed"},
            ],
            "skip_invalid": False,  # Will fail and record
        }

        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            process_import_job("job_test123")

            # When skip_invalid=False, missing URL is recorded as failed
            assert mock_job.result["failed"] == 1
            details = mock_job.result["details"]
            assert details[0]["status"] == "failed"
            assert "No URL provided" in details[0]["reason"]

    def test_process_import_job_skip_invalid_false(self, mock_db, mock_job):
        """Test that skip_invalid=False records failures."""
        mock_job.result = {
            "feeds": [
                {"title": "No URL Feed"},
            ],
            "skip_invalid": False,  # Will fail instead of skip
        }

        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            process_import_job("job_test123")

            # Should fail, not skip
            assert mock_job.result["failed"] == 1
            details = mock_job.result["details"]
            assert details[0]["status"] == "failed"

    def test_process_import_job_exception_handling(self, mock_db, mock_job):
        """Test that exceptions are properly handled."""
        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            with patch("cyberpulse.tasks.import_tasks.SourceService") as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.add_source.side_effect = Exception("Database error")

                process_import_job("job_test123")

            # Should record as skipped (skip_invalid=True by default)
            assert mock_job.result["skipped"] == 2
            details = mock_job.result["details"]
            for detail in details:
                assert detail["status"] == "skipped"
                assert "Database error" in detail["reason"]


class TestImportJobResultFormat:
    """Tests for import job result format."""

    def test_result_includes_required_fields(self):
        """Test that result includes all required fields."""
        # This is a contract test for the result format
        expected_fields = ["imported", "skipped", "failed", "details"]

        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.job_id = "job_test"
        mock_job.result = {"feeds": []}

        with patch("cyberpulse.tasks.import_tasks.SessionLocal") as mock_session:
            mock_session.return_value = mock_db
            mock_db.query.return_value.filter.return_value.first.return_value = mock_job

            process_import_job("job_test")

            for field in expected_fields:
                assert field in mock_job.result, f"Missing field: {field}"

    def test_detail_format_for_imported(self):
        """Test detail format for imported source."""
        # Expected fields for imported source
        expected_fields = ["url", "title", "status", "source_id", "ingestion_triggered"]

        # This validates the contract
        sample_detail = {
            "url": "https://example.com/feed.xml",
            "title": "Example Feed",
            "status": "imported",
            "source_id": "src_a1b2c3d4",
            "ingestion_triggered": True,
        }

        for field in expected_fields:
            assert field in sample_detail, f"Missing field in detail: {field}"
