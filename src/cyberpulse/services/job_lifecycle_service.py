"""Job lifecycle service for delete, retry, and cleanup operations."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
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
    - Cleaning up REMOVED sources
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

        try:
            self.db.delete(job)
            self.db.commit()
            logger.info(f"Deleted job: {job_id}")
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to delete job {job_id}: {e}")
            raise ValueError(f"Failed to delete job: {e}") from e

        return {"deleted": job_id}

    def retry_job(self, job_id: str) -> dict:
        """Retry a FAILED job.

        Resets job state and dispatches appropriate Dramatiq task.
        Uses savepoint to allow partial rollback if task dispatch fails.

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

        # Validate job type requirements before state change
        if job.type == JobType.INGEST and not job.source_id:
            raise ValueError("Cannot retry INGEST job without source_id")

        # Store original state for potential rollback
        original_status = job.status
        original_retry_count = job.retry_count

        try:
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
                ingest_source.send(job.source_id, job_id=job.job_id)
                logger.info(
                    f"Dispatched ingest_source for job {job_id}, "
                    f"source {job.source_id}"
                )
            elif job.type == JobType.IMPORT:
                process_import_job.send(job.job_id)
                logger.info(f"Dispatched process_import_job for job {job_id}")
            else:
                # Rollback on unsupported job type
                job.status = original_status
                job.retry_count = original_retry_count
                self.db.commit()
                raise ValueError(f"Unsupported job type: {job.type.value}")

            logger.info(f"Job {job_id} queued for retry (attempt {job.retry_count})")

        except Exception as e:
            # Rollback state if task dispatch failed
            self.db.rollback()
            job = self.db.get(Job, job_id)
            if job:
                job.status = original_status
                job.retry_count = original_retry_count
                self.db.commit()
            logger.error(f"Failed to retry job {job_id}: {e}")
            raise ValueError(f"Failed to dispatch retry task: {e}") from e

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

        try:
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
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to cleanup jobs: {e}")
            raise ValueError(f"Failed to cleanup jobs: {e}") from e

    def cleanup_sources(self) -> dict:
        """Clean up REMOVED sources with cascade deletion.

        Deletes all sources with status=REMOVED along with their
        associated items and jobs.

        Returns:
            Dict with counts of deleted sources, items, and jobs.
        """
        from ..models import Item, Source, SourceStatus

        removed_sources = self.db.scalars(
            select(Source).where(Source.status == SourceStatus.REMOVED)
        ).all()

        if not removed_sources:
            return {
                "deleted_sources": 0,
                "deleted_items": 0,
                "deleted_jobs": 0,
            }

        deleted_sources = 0
        deleted_items = 0
        deleted_jobs = 0

        try:
            for source in removed_sources:
                # Order matters: FK constraints require children deleted first
                # 1. Delete items (items.source_id is not null)
                items_result = self.db.execute(
                    delete(Item).where(Item.source_id == source.source_id)
                )
                deleted_items += getattr(items_result, "rowcount", 0)

                # 2. Delete jobs with this source_id (jobs.source_id is nullable)
                jobs_result = self.db.execute(
                    delete(Job).where(Job.source_id == source.source_id)
                )
                deleted_jobs += getattr(jobs_result, "rowcount", 0)

                # 3. Delete source
                self.db.delete(source)
                deleted_sources += 1

            self.db.commit()

            logger.info(
                f"Cleaned up {deleted_sources} REMOVED sources, "
                f"{deleted_items} items, {deleted_jobs} jobs"
            )

            return {
                "deleted_sources": deleted_sources,
                "deleted_items": deleted_items,
                "deleted_jobs": deleted_jobs,
            }
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to cleanup sources: {e}")
            raise ValueError(f"Failed to cleanup sources: {e}") from e
