"""Job functions for the scheduler.

This module contains the job functions that are scheduled by APScheduler.
These jobs trigger Dramatiq tasks for actual processing.

Import order note:
- models imports are safe (no broker dependency)
- ingestion_tasks import triggers worker.py which configures broker
"""

import logging
import secrets
from typing import Any

from ..database import SessionLocal
from ..models import Item, ItemStatus, Job, JobStatus, JobType, Source, SourceStatus
from ..models.job import JobTrigger
from ..services.source_score_service import SourceScoreService
from ..tasks.ingestion_tasks import ingest_source

logger = logging.getLogger(__name__)


def collect_source(source_id: str) -> dict[str, Any]:
    """Collect items from a source via Dramatiq task.

    Creates a job record for tracking before queuing the task.

    Args:
        source_id: The ID of the source to collect from.

    Returns:
        Dictionary with job result status.
    """
    db = SessionLocal()
    try:
        # Create job record for tracking
        job = Job(
            job_id=f"job_{secrets.token_hex(8)}",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id=source_id,
            trigger=JobTrigger.SCHEDULER,
        )
        db.add(job)
        db.commit()

        # Send to Dramatiq task queue with job_id
        ingest_source.send(source_id, job_id=job.job_id)

        logger.info(f"Created scheduler job {job.job_id} for source {source_id}")

        return {
            "source_id": source_id,
            "job_id": job.job_id,
            "status": "queued",
            "message": "Collection job queued successfully",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create job for source {source_id}: {e}")
        raise
    finally:
        db.close()


def run_scheduled_collection() -> dict[str, Any]:
    """Run scheduled collection for all active sources.

    Queries database for active sources and queues collection
    jobs for each, creating job records for tracking.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Running scheduled collection for all active sources")

    db = SessionLocal()
    queued_count = 0
    failed_count = 0
    job_ids = []

    try:
        # Query all active sources and extract IDs before processing
        # This avoids DetachedInstanceError after rollback
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()
        source_ids = [s.source_id for s in sources]

        for source_id in source_ids:
            try:
                # Create job record
                job = Job(
                    job_id=f"job_{secrets.token_hex(8)}",
                    type=JobType.INGEST,
                    status=JobStatus.PENDING,
                    source_id=source_id,
                    trigger=JobTrigger.SCHEDULER,
                )
                db.add(job)
                db.flush()  # Get job_id without committing

                # Queue task with job_id
                ingest_source.send(source_id, job_id=job.job_id)
                job_ids.append(job.job_id)
                queued_count += 1
            except (OSError, ConnectionError) as e:
                # Catch broker/connection errors specifically
                # Rollback uncommitted job record but continue with other sources
                db.rollback()
                logger.error(f"Failed to queue source {source_id}: {e}")
                failed_count += 1
                # Note: rollback detaches all pending objects, but we use
                # extracted source_ids list, not source objects, so we can continue

        # Only commit if we have successfully queued at least one job
        # or if no errors occurred
        if queued_count > 0 or failed_count == 0:
            db.commit()

        logger.info(
            f"Queued {queued_count} sources for collection "
            f"({failed_count} failed)"
        )

        return {
            "status": "completed",
            "sources_count": queued_count,
            "failed_count": failed_count,
            "job_ids": job_ids,
            "message": (
                f"Queued {queued_count} sources for collection "
                f"({failed_count} failed)"
            ),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Scheduled collection failed with unexpected error: {e}")
        return {
            "status": "failed",
            "sources_count": queued_count,
            "failed_count": failed_count,
            "job_ids": job_ids,
            "error": str(e),
            "message": f"Scheduled collection failed: {e}",
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
    updated_count = 0
    failed_count = 0

    try:
        # Query all active sources and extract IDs before processing
        # This avoids DetachedInstanceError after rollback
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()
        source_ids = [s.source_id for s in sources]

        score_service = SourceScoreService(db)

        for source_id in source_ids:
            try:
                score_service.update_tier(source_id)
                updated_count += 1
            except ValueError as e:
                # Value errors indicate missing data for scoring
                logger.warning(f"Could not update score for {source_id}: {e}")
                failed_count += 1
            except Exception as e:
                # Log unexpected errors but continue processing other sources
                logger.error(f"Unexpected error updating score for {source_id}: {e}")
                failed_count += 1

        db.commit()

        logger.info(
            f"Updated scores for {updated_count} sources "
            f"({failed_count} failed)"
        )

        return {
            "status": "completed",
            "sources_updated": updated_count,
            "failed_count": failed_count,
            "message": (
                f"Updated scores for {updated_count} sources "
                f"({failed_count} failed)"
            ),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Source score update failed with unexpected error: {e}")
        return {
            "status": "failed",
            "sources_updated": updated_count,
            "failed_count": failed_count,
            "error": str(e),
            "message": f"Source score update failed: {e}",
        }
    finally:
        db.close()


def retry_pending_full_fetch() -> dict[str, Any]:
    """Retry full fetch for items stuck in PENDING_FULL_FETCH status.

    Items can get stuck in this status when:
    - Task failed due to rate limiting
    - Task exceeded time limit
    - Worker crashed during processing

    This job re-queues items that have not yet attempted full fetch.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Retrying pending full fetch items")

    db = SessionLocal()
    try:
        # Find items that are pending full fetch but haven't attempted yet
        items = db.query(Item).filter(
            Item.status == ItemStatus.PENDING_FULL_FETCH,
            Item.full_fetch_attempted == False,  # noqa: E712
            Item.url.isnot(None),  # Must have a URL to fetch
        ).limit(100).all()

        if not items:
            logger.debug("No pending items to retry")
            return {
                "status": "completed",
                "items_queued": 0,
                "message": "No pending items to retry",
            }

        # Import here to avoid circular dependency
        from ..tasks.full_content_tasks import fetch_full_content

        queued_count = 0
        for item in items:
            try:
                fetch_full_content.send(item.item_id)
                queued_count += 1
            except (OSError, ConnectionError) as e:
                logger.error(f"Failed to queue item {item.item_id}: {e}")
                continue

        logger.info(f"Queued {queued_count} pending items for full fetch retry")

        return {
            "status": "completed",
            "items_queued": queued_count,
            "message": f"Queued {queued_count} pending items for full fetch retry",
        }
    finally:
        db.close()
