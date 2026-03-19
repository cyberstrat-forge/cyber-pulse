"""Job functions for the scheduler.

This module contains the job functions that are scheduled by APScheduler.
These jobs will trigger Dramatiq tasks for actual processing.
"""

import logging

logger = logging.getLogger(__name__)


def collect_source(source_id: str) -> dict:
    """Collect items from a source.

    This job function triggers the ingestion pipeline for a source.
    In Phase 2D.3, this will send a message to Dramatiq worker.

    Args:
        source_id: The ID of the source to collect from.

    Returns:
        Dictionary with job result status.

    Note:
        This is a placeholder implementation. The actual Dramatiq task
        integration will be added in Task 2D.3.
    """
    logger.info(f"Collecting items from source: {source_id}")

    # Placeholder: In Task 2D.3, this will call:
    # from ..tasks.ingestion_tasks import ingest_source
    # ingest_source.send(source_id)

    return {
        "source_id": source_id,
        "status": "queued",
        "message": "Collection job queued (placeholder - Dramatiq integration pending)",
    }


def run_scheduled_collection() -> dict:
    """Run scheduled collection for all active sources.

    This job is run periodically to collect from all active sources.
    It queries the database for active sources and queues collection
    jobs for each.

    Returns:
        Dictionary with job result status.

    Note:
        This is a placeholder implementation. The actual implementation
        will query sources from the database and trigger Dramatiq tasks.
    """
    logger.info("Running scheduled collection for all active sources")

    # Placeholder: In Task 2D.3, this will:
    # 1. Query all active sources from database
    # 2. For each source, call ingest_source.send(source_id)

    return {
        "status": "queued",
        "sources_count": 0,
        "message": "Scheduled collection queued (placeholder)",
    }


def update_source_scores() -> dict:
    """Update scores for all sources.

    This job recalculates source scores based on collection statistics.

    Returns:
        Dictionary with job result status.

    Note:
        This is a placeholder implementation. The actual implementation
        will use SourceScoreService from Phase 2E.
    """
    logger.info("Updating source scores")

    # Placeholder: In Phase 2E, this will:
    # from ..services.source_score_service import SourceScoreService
    # Recalculate scores for all sources

    return {
        "status": "completed",
        "sources_updated": 0,
        "message": "Source scores updated (placeholder)",
    }