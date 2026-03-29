"""Job lifecycle service for delete, retry, and cleanup operations."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..models import Job, JobStatus, JobType
from ..tasks.import_tasks import process_import_job
from ..tasks.ingestion_tasks import ingest_source

logger = logging.getLogger(__name__)

# Default maximum retries for a job
MAX_RETRIES = 3


class JobLifecycleService:
    """Service for managing job lifecycle operations.

    Provides methods for:
    - Deleting failed jobs
    - Retrying failed jobs
    - Cleaning up old jobs
    """

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db

    def delete_job(self, job_id: str) -> dict:
        """Delete a FAILED job.

        Args:
            job_id: The job ID to delete.

        Returns:
            Dict with deleted job_id.

        Raises:
            ValueError: If job not found or not in FAILED status.
        """
        job = self.db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.FAILED:
            raise ValueError(
                f"Only FAILED jobs can be deleted, "
                f"current status: {job.status.value}"
            )

        self.db.delete(job)
        self.db.commit()
        logger.info(f"Deleted job: {job_id}")

        return {"deleted": job_id}

    def retry_job(self, job_id: str) -> dict:
        """Retry a FAILED job.

        Resets job state and dispatches appropriate Dramatiq task.

        Args:
            job_id: The job ID to retry.

        Returns:
            Dict with job_id, status, and retry_count.

        Raises:
            ValueError: If job not found, not FAILED, or exceeds retry limit.
        """
        job = self.db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.FAILED:
            raise ValueError(
                f"Only FAILED jobs can be retried, "
                f"current status: {job.status.value}"
            )

        if job.retry_count >= MAX_RETRIES:
            raise ValueError(f"Job exceeded max retries ({MAX_RETRIES})")

        # Reset job state first (before dispatching task to avoid race condition)
        job.status = JobStatus.PENDING
        job.retry_count += 1
        job.error_type = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        self.db.commit()

        # Dispatch appropriate task based on job type
        if job.type == JobType.INGEST:
            if not job.source_id:
                raise ValueError(
                    f"Cannot retry INGEST job without source_id"
                )
            ingest_source.send(job.source_id, job_id=job.job_id)
            logger.info(
                f"Dispatched ingest_source for job {job_id}, "
                f"source {job.source_id}"
            )
        elif job.type == JobType.IMPORT:
            process_import_job.send(job.job_id)
            logger.info(f"Dispatched process_import_job for job {job_id}")
        else:
            raise ValueError(f"Unsupported job type: {job.type.value}")

        logger.info(f"Job {job_id} queued for retry (attempt {job.retry_count})")

        return {
            "job_id": job_id,
            "status": "PENDING",
            "retry_count": job.retry_count,
        }

    def cleanup_jobs(
        self,
        days: int = 30,
        status: JobStatus = JobStatus.COMPLETED
    ) -> dict:
        """Clean up old jobs by status.

        Args:
            days: Delete jobs completed before this many days ago.
            status: Job status to clean up.

        Returns:
            Dict with deleted_count and threshold_days.
        """
        threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        stmt = delete(Job).where(
            Job.status == status,
            Job.completed_at < threshold
        )
        result = self.db.execute(stmt)
        self.db.commit()

        deleted_count = getattr(result, "rowcount", 0)
        logger.info(
            f"Cleaned up {deleted_count} jobs older than {days} days "
            f"with status {status.value}"
        )

        return {
            "deleted_count": deleted_count,
            "threshold_days": days,
        }
