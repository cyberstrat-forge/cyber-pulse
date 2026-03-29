"""Tests for JobLifecycleService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from cyberpulse.models import (
    Job,
    JobStatus,
    JobType,
    Source,
    SourceStatus,
    SourceTier,
)
from cyberpulse.services.job_lifecycle_service import (
    MAX_RETRIES,
    JobLifecycleService,
)


@pytest.fixture
def job_lifecycle_service(db_session):
    """Create a JobLifecycleService instance."""
    return JobLifecycleService(db_session)


@pytest.fixture
def sample_source(db_session):
    """Create a sample source for testing."""
    source = Source(
        source_id="src_test01",
        name="Test Source",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
        config={"feed_url": "https://example.com/feed.xml"},
    )
    db_session.add(source)
    db_session.commit()
    return source


class TestDeleteJob:
    """Tests for delete_job method."""

    def test_delete_failed_job(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test deleting a FAILED job."""
        # Create a FAILED INGEST job
        job = Job(
            job_id="job_test01",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            error_type="ConnectionError",
            error_message="Failed to connect",
        )
        db_session.add(job)
        db_session.commit()

        result = job_lifecycle_service.delete_job("job_test01")

        assert result == {"deleted": "job_test01"}
        # Verify job is deleted
        deleted_job = db_session.get(Job, "job_test01")
        assert deleted_job is None

    def test_delete_failed_import_job(self, job_lifecycle_service, db_session):
        """Test deleting a FAILED IMPORT job (no source required)."""
        job = Job(
            job_id="job_test_import",
            type=JobType.IMPORT,
            status=JobStatus.FAILED,
            file_name="feeds.opml",
            error_type="ParseError",
            error_message="Invalid OPML format",
        )
        db_session.add(job)
        db_session.commit()

        result = job_lifecycle_service.delete_job("job_test_import")

        assert result == {"deleted": "job_test_import"}
        deleted_job = db_session.get(Job, "job_test_import")
        assert deleted_job is None

    def test_delete_job_not_found(self, job_lifecycle_service):
        """Test deleting a non-existent job."""
        with pytest.raises(ValueError, match="Job not found"):
            job_lifecycle_service.delete_job("job_nonexistent")

    def test_delete_running_job_raises_error(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test deleting a RUNNING job raises error."""
        job = Job(
            job_id="job_test02",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
            source_id=sample_source.source_id,
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(ValueError, match="Only FAILED jobs can be deleted"):
            job_lifecycle_service.delete_job("job_test02")

    def test_delete_completed_job_raises_error(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test deleting a COMPLETED job raises error."""
        job = Job(
            job_id="job_test03",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            result={"new_items": 10},
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(ValueError, match="Only FAILED jobs can be deleted"):
            job_lifecycle_service.delete_job("job_test03")

    def test_delete_pending_job_raises_error(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test deleting a PENDING job raises error."""
        job = Job(
            job_id="job_test04",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id=sample_source.source_id,
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(ValueError, match="Only FAILED jobs can be deleted"):
            job_lifecycle_service.delete_job("job_test04")


class TestRetryJob:
    """Tests for retry_job method."""

    def test_retry_ingest_job(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test retrying a FAILED INGEST job."""
        job = Job(
            job_id="job_retry01",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            error_type="ConnectionError",
            error_message="Failed to connect",
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        with patch(
            "cyberpulse.services.job_lifecycle_service.ingest_source"
        ) as mock_ingest:
            result = job_lifecycle_service.retry_job("job_retry01")

            assert result["job_id"] == "job_retry01"
            assert result["status"] == "PENDING"
            assert result["retry_count"] == 1

            # Verify task was dispatched
            mock_ingest.send.assert_called_once_with(
                sample_source.source_id,
                job_id="job_retry01"
            )

        # Verify job state reset
        db_session.refresh(job)
        assert job.status == JobStatus.PENDING
        assert job.retry_count == 1
        assert job.error_type is None
        assert job.error_message is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_retry_import_job(self, job_lifecycle_service, db_session):
        """Test retrying a FAILED IMPORT job."""
        job = Job(
            job_id="job_retry02",
            type=JobType.IMPORT,
            status=JobStatus.FAILED,
            file_name="feeds.opml",
            error_type="ParseError",
            error_message="Invalid OPML format",
            retry_count=0,
            result={"feeds": []},
        )
        db_session.add(job)
        db_session.commit()

        with patch(
            "cyberpulse.services.job_lifecycle_service.process_import_job"
        ) as mock_import:
            result = job_lifecycle_service.retry_job("job_retry02")

            assert result["job_id"] == "job_retry02"
            assert result["status"] == "PENDING"
            assert result["retry_count"] == 1

            # Verify task was dispatched
            mock_import.send.assert_called_once_with("job_retry02")

        # Verify job state reset
        db_session.refresh(job)
        assert job.status == JobStatus.PENDING
        assert job.retry_count == 1

    def test_retry_job_not_found(self, job_lifecycle_service):
        """Test retrying a non-existent job."""
        with pytest.raises(ValueError, match="Job not found"):
            job_lifecycle_service.retry_job("job_nonexistent")

    def test_retry_running_job_raises_error(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test retrying a RUNNING job raises error."""
        job = Job(
            job_id="job_retry03",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
            source_id=sample_source.source_id,
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(ValueError, match="Only FAILED jobs can be retried"):
            job_lifecycle_service.retry_job("job_retry03")

    def test_retry_job_exceeds_max_retries(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test retrying a job that exceeds max retries."""
        job = Job(
            job_id="job_retry04",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            error_type="ConnectionError",
            error_message="Failed to connect",
            retry_count=MAX_RETRIES,
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(ValueError, match="Job exceeded max retries"):
            job_lifecycle_service.retry_job("job_retry04")

    def test_retry_job_twice(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test retrying a job multiple times."""
        job = Job(
            job_id="job_retry05",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            error_type="ConnectionError",
            error_message="Failed to connect",
            retry_count=1,  # Already retried once
        )
        db_session.add(job)
        db_session.commit()

        with patch("cyberpulse.services.job_lifecycle_service.ingest_source"):
            result = job_lifecycle_service.retry_job("job_retry05")

            assert result["retry_count"] == 2

        db_session.refresh(job)
        assert job.retry_count == 2

    def test_retry_job_resets_error_info(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test that retry clears error information."""
        job = Job(
            job_id="job_retry06",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            error_type="ConnectionError",
            error_message="Detailed error message",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        with patch("cyberpulse.services.job_lifecycle_service.ingest_source"):
            job_lifecycle_service.retry_job("job_retry06")

        db_session.refresh(job)
        assert job.error_type is None
        assert job.error_message is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_retry_ingest_job_without_source_id_raises_error(
        self, job_lifecycle_service, db_session
    ):
        """Test retrying INGEST job without source_id raises error."""
        job = Job(
            job_id="job_no_source",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=None,  # No source_id
            error_type="ConnectionError",
            error_message="Failed to connect",
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(
            ValueError, match="Cannot retry INGEST job without source_id"
        ):
            job_lifecycle_service.retry_job("job_no_source")


class TestCleanupJobs:
    """Tests for cleanup_jobs method."""

    def test_cleanup_completed_jobs(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleaning up old COMPLETED jobs."""
        # Create old COMPLETED job
        old_completed_at = datetime.now(UTC) - timedelta(days=35)
        job = Job(
            job_id="job_old01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            completed_at=old_completed_at,
            result={"new_items": 5},
        )
        db_session.add(job)

        # Create recent COMPLETED job (should not be deleted)
        recent_job = Job(
            job_id="job_recent01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            completed_at=datetime.now(UTC) - timedelta(days=10),
            result={"new_items": 3},
        )
        db_session.add(recent_job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(
            days=30, status=JobStatus.COMPLETED
        )

        assert result["deleted_count"] == 1
        assert result["threshold_days"] == 30

        # Verify old job is deleted
        deleted_job = db_session.get(Job, "job_old01")
        assert deleted_job is None

        # Verify recent job is kept
        kept_job = db_session.get(Job, "job_recent01")
        assert kept_job is not None

    def test_cleanup_failed_jobs(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleaning up old FAILED jobs."""
        old_completed_at = datetime.now(UTC) - timedelta(days=40)
        job = Job(
            job_id="job_old02",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=sample_source.source_id,
            completed_at=old_completed_at,
            error_type="ConnectionError",
            error_message="Failed",
        )
        db_session.add(job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(
            days=30, status=JobStatus.FAILED
        )

        assert result["deleted_count"] == 1

    def test_cleanup_jobs_default_params(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleanup with default parameters (30 days, COMPLETED)."""
        # Create job older than 30 days
        old_job = Job(
            job_id="job_default01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            completed_at=datetime.now(UTC) - timedelta(days=35),
            result={"new_items": 1},
        )
        db_session.add(old_job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs()

        assert result["deleted_count"] == 1
        assert result["threshold_days"] == 30

    def test_cleanup_jobs_no_matches(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleanup when no jobs match criteria."""
        # Create recent job
        recent_job = Job(
            job_id="job_no_match01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            completed_at=datetime.now(UTC) - timedelta(days=5),
            result={"new_items": 1},
        )
        db_session.add(recent_job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 0

    def test_cleanup_jobs_custom_days(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleanup with custom days threshold."""
        job = Job(
            job_id="job_custom01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id=sample_source.source_id,
            completed_at=datetime.now(UTC) - timedelta(days=8),
            result={"new_items": 1},
        )
        db_session.add(job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(days=7)

        assert result["deleted_count"] == 1
        assert result["threshold_days"] == 7

    def test_cleanup_multiple_jobs(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleaning up multiple old jobs."""
        # Create multiple old jobs
        for i in range(5):
            job = Job(
                job_id=f"job_multi{i:02d}",
                type=JobType.INGEST,
                status=JobStatus.COMPLETED,
                source_id=sample_source.source_id,
                completed_at=datetime.now(UTC) - timedelta(days=40 + i),
                result={"new_items": i},
            )
            db_session.add(job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 5

    def test_cleanup_jobs_keeps_running_and_pending(
        self, job_lifecycle_service, db_session, sample_source
    ):
        """Test cleanup does not affect RUNNING or PENDING jobs."""
        # Create old RUNNING job (should not be deleted)
        running_job = Job(
            job_id="job_running01",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
            source_id=sample_source.source_id,
            started_at=datetime.now(UTC) - timedelta(days=40),
        )
        db_session.add(running_job)

        # Create old PENDING job (should not be deleted)
        pending_job = Job(
            job_id="job_pending01",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id=sample_source.source_id,
        )
        db_session.add(pending_job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 0

        # Verify jobs are kept
        assert db_session.get(Job, "job_running01") is not None
        assert db_session.get(Job, "job_pending01") is not None

    def test_cleanup_import_jobs(self, job_lifecycle_service, db_session):
        """Test cleaning up old IMPORT jobs (no source required)."""
        old_job = Job(
            job_id="job_import_old",
            type=JobType.IMPORT,
            status=JobStatus.COMPLETED,
            file_name="feeds.opml",
            completed_at=datetime.now(UTC) - timedelta(days=35),
            result={"imported": 5},
        )
        db_session.add(old_job)
        db_session.commit()

        result = job_lifecycle_service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 1
