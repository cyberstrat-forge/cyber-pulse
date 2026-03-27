"""Job functions for the scheduler.

This module contains the job functions that are scheduled by APScheduler.
These jobs trigger Dramatiq tasks for actual processing.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ..database import SessionLocal
from ..models import Job, JobStatus, Source, SourceStatus
from ..services.source_score_service import SourceScoreService
from ..tasks.ingestion_tasks import ingest_source

logger = logging.getLogger(__name__)

# Timeout threshold for orphaned jobs (minutes)
ORPHANED_JOB_TIMEOUT_MINUTES = 5


def collect_source(source_id: str) -> dict[str, Any]:
    """Collect items from a source via Dramatiq task.

    Args:
        source_id: The ID of the source to collect from.

    Returns:
        Dictionary with job result status.
    """
    logger.info(f"Queueing collection for source: {source_id}")

    # Send to Dramatiq task queue
    ingest_source.send(source_id)

    return {
        "source_id": source_id,
        "status": "queued",
        "message": "Collection job queued successfully",
    }


def run_scheduled_collection() -> dict[str, Any]:
    """Run scheduled collection for all active sources.

    Queries database for active sources and queues collection
    jobs for each.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Running scheduled collection for all active sources")

    db = SessionLocal()
    try:
        # Query all active sources
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()

        queued_count = 0
        failed_count = 0
        for source in sources:
            try:
                ingest_source.send(source.source_id)
                queued_count += 1
            except (OSError, ConnectionError) as e:
                # Catch broker/connection errors specifically
                # Let system errors (MemoryError, etc.) propagate
                logger.error(f"Failed to queue source {source.source_id}: {e}")
                failed_count += 1
                continue

        logger.info(f"Queued {queued_count} sources for collection ({failed_count} failed)")

        return {
            "status": "completed",
            "sources_count": queued_count,
            "failed_count": failed_count,
            "message": f"Queued {queued_count} sources for collection ({failed_count} failed)",
        }
    finally:
        db.close()


def update_source_scores() -> dict[str, Any]:
    """Update scores for all sources.

    Recalculates source scores based on collection statistics.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Updating source scores")

    db = SessionLocal()
    try:
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()

        score_service = SourceScoreService(db)
        updated_count = 0
        failed_count = 0

        for source in sources:
            try:
                score_service.update_tier(source.source_id)
                updated_count += 1
            except ValueError as e:
                logger.warning(f"Could not update score for {source.source_id}: {e}")
                failed_count += 1

        logger.info(f"Updated scores for {updated_count} sources ({failed_count} failed)")

        return {
            "status": "completed",
            "sources_updated": updated_count,
            "failed_count": failed_count,
            "message": f"Updated scores for {updated_count} sources ({failed_count} failed)",
        }
    finally:
        db.close()


def cleanup_orphaned_jobs() -> dict[str, Any]:
    """Clean up orphaned PENDING jobs.

    Scans for jobs that have been in PENDING status longer than the
    timeout threshold and marks them as FAILED. This handles cases where
    the Dramatiq message was lost or the worker failed to process it.

    Returns:
        Dictionary with cleanup result status.
    """
    logger.info("Running orphaned jobs cleanup")

    db = SessionLocal()
    try:
        # Calculate threshold: jobs older than this are considered orphaned
        threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            minutes=ORPHANED_JOB_TIMEOUT_MINUTES
        )

        # Find orphaned jobs
        orphaned_jobs = (
            db.query(Job)
            .filter(
                Job.status == JobStatus.PENDING,
                Job.created_at < threshold,
            )
            .all()
        )

        cleaned_count = 0
        for job in orphaned_jobs:
            job.status = JobStatus.FAILED  # type: ignore[assignment]
            job.error_type = "OrphanedJob"
            job.error_message = (
                f"Task timeout - no worker response after "
                f"{ORPHANED_JOB_TIMEOUT_MINUTES} minutes"
            )
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            cleaned_count += 1
            logger.warning(
                f"Marked orphaned job {job.job_id} as FAILED "
                f"(type: {job.type}, created: {job.created_at})"
            )

        if cleaned_count > 0:
            db.commit()
            logger.info(f"Cleaned up {cleaned_count} orphaned jobs")
        else:
            logger.debug("No orphaned jobs found")

        return {
            "status": "completed",
            "cleaned_count": cleaned_count,
            "message": f"Cleaned up {cleaned_count} orphaned jobs",
        }
    except Exception as e:
        logger.error(f"Failed to cleanup orphaned jobs: {e}", exc_info=True)
        db.rollback()
        return {
            "status": "failed",
            "cleaned_count": 0,
            "error": str(e),
        }
    finally:
        db.close()
