"""Job functions for the scheduler.

This module contains the job functions that are scheduled by APScheduler.
These jobs trigger Dramatiq tasks for actual processing.
"""

import logging
from typing import Dict, Any

from ..database import SessionLocal
from ..models import Source, SourceStatus
from ..tasks.ingestion_tasks import ingest_source
from ..services.source_score_service import SourceScoreService

logger = logging.getLogger(__name__)


def collect_source(source_id: str) -> Dict[str, Any]:
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


def run_scheduled_collection() -> Dict[str, Any]:
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


def update_source_scores() -> Dict[str, Any]:
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