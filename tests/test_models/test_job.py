"""Tests for Job model."""

from cyberpulse.models.job import Job, JobStatus, JobType
from cyberpulse.models.source import Source, SourceStatus, SourceTier


class TestJobModel:
    """Test cases for Job model."""

    def test_job_creation(self, db_session):
        """Test creating a job record."""
        # Create a source first for foreign key
        source = Source(
            source_id="src_xxx",
            name="Test Source",
            connector_type="rss",
            tier=SourceTier.T2,
            status=SourceStatus.ACTIVE,
            config={"feed_url": "https://example.com/feed"},
        )
        db_session.add(source)
        db_session.commit()

        job = Job(
            job_id="job_abc123",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id="src_xxx",
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.job_id == "job_abc123"
        assert job.type == JobType.INGEST
        assert job.status == JobStatus.PENDING

    def test_job_with_result(self, db_session):
        """Test job with result data."""
        # Create a source first for foreign key
        source = Source(
            source_id="src_xxx2",
            name="Test Source 2",
            connector_type="rss",
            tier=SourceTier.T2,
            status=SourceStatus.ACTIVE,
            config={"feed_url": "https://example.com/feed"},
        )
        db_session.add(source)
        db_session.commit()

        job = Job(
            job_id="job_xyz789",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id="src_xxx2",
            result={"items_fetched": 15, "items_created": 12},
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.result["items_fetched"] == 15

    def test_job_with_error(self, db_session):
        """Test job with error information."""
        # Create a source first for foreign key
        source = Source(
            source_id="src_xxx3",
            name="Test Source 3",
            connector_type="rss",
            tier=SourceTier.T2,
            status=SourceStatus.ACTIVE,
            config={"feed_url": "https://example.com/feed"},
        )
        db_session.add(source)
        db_session.commit()

        job = Job(
            job_id="job_err001",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id="src_xxx3",
            error_type="connection_timeout",
            error_message="Connection timeout after 30s",
            retry_count=3,
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.status == JobStatus.FAILED
        assert job.retry_count == 3

    def test_job_type_enums(self):
        """Test JobType enum values."""
        assert JobType.INGEST.value == "INGEST"
        assert JobType.IMPORT.value == "IMPORT"

    def test_job_status_enums(self):
        """Test JobStatus enum values."""
        assert JobStatus.PENDING.value == "PENDING"
        assert JobStatus.RUNNING.value == "RUNNING"
        assert JobStatus.COMPLETED.value == "COMPLETED"
        assert JobStatus.FAILED.value == "FAILED"

    def test_job_import_type(self, db_session):
        """Test creating an import job."""
        job = Job(
            job_id="job_imp001",
            type=JobType.IMPORT,
            status=JobStatus.COMPLETED,
            file_name="sources.yaml",
            result={"imported": 10, "skipped": 2},
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.type == JobType.IMPORT
        assert job.file_name == "sources.yaml"
        assert job.source_id is None
