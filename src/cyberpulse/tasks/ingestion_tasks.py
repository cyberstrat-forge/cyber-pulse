"""Ingestion tasks for fetching items from sources."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import dramatiq
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from ..config import settings
from ..database import SessionLocal
from ..models import Job, JobStatus, Source, SourceStatus
from ..models.item import ItemStatus
from ..services.connector_factory import get_connector_for_source
from ..services.item_service import ItemService
from ..services.rss_connector import FetchResult
from ..services.rss_discovery import RSSDiscoveryService
from .worker import broker

if TYPE_CHECKING:
    from ..services.connector_service import BaseConnector

logger = logging.getLogger(__name__)

# Export for backward compatibility with tests
MAX_CONSECUTIVE_FAILURES = settings.max_consecutive_failures


def _mark_job_failed(
    db: "SessionLocal",
    job_id: str,
    error_type: str,
    error_message: str,
) -> None:
    """Mark a job as failed with error details.

    Args:
        db: Database session.
        job_id: The job ID to mark as failed.
        error_type: Type of error (e.g., exception class name).
        error_message: Detailed error message.
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if job:
        job.status = JobStatus.FAILED
        job.error_type = error_type
        job.error_message = error_message
        job.completed_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        logger.info(f"Job {job_id} marked as failed: {error_type}: {error_message}")
    else:
        logger.warning(f"Job {job_id} not found when trying to mark as failed")


@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str, job_id: str | None = None) -> None:
    """Ingest items from a source.

    This task:
    1. Gets source from database
    2. Skips if source is FROZEN
    3. Uses connector to fetch items
    4. Handles redirect and updates feed_url
    5. Creates Item records
    6. Tracks failures and freezes source if needed

    Args:
        source_id: The source ID to ingest from.
        job_id: Optional job ID for status tracking.
    """
    db = SessionLocal()
    source = None
    job = None
    try:
        # Get source from database
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            logger.error(f"Source not found: {source_id}")
            if job_id:
                _mark_job_failed(
                    db, job_id, "SourceNotFound", f"Source not found: {source_id}"
                )
            return

        # Skip frozen sources
        if source.status == SourceStatus.FROZEN:
            logger.debug(f"Skipping frozen source: {source.name}")
            if job_id:
                _mark_job_failed(
                    db, job_id, "SourceFrozen", f"Source is frozen: {source.name}"
                )
            return

        # Mark job as RUNNING and update source's last_job_id
        if job_id:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(UTC).replace(tzinfo=None)
                db.commit()
                logger.info(f"Job {job_id} marked as RUNNING")

        # Update source's last_job_id
        if job_id:
            source.last_job_id = job_id

        logger.info(f"Starting ingestion for source: {source.name} ({source_id})")

        # Create connector for this source
        connector = get_connector_for_source(source)

        # Fetch items using async connector
        result = asyncio.run(_fetch_items(connector, None))

        # Handle both FetchResult and legacy list return
        if isinstance(result, FetchResult):
            items_data = result.items
            redirect_info = result.redirect_info
        else:
            items_data = result
            redirect_info = None

        # Handle permanent redirect (only 301/308)
        if redirect_info and redirect_info.get("status_code") in (301, 308):
            logger.info(
                f"Updating source URL: {redirect_info['original_url']} -> {redirect_info['final_url']}"
            )
            source.config["feed_url"] = redirect_info["final_url"]
            flag_modified(source, "config")

        # Reset failure count on success
        source.consecutive_failures = 0

        if not items_data:
            logger.info(f"No items fetched from source: {source.name}")
            source.last_ingested_at = datetime.now(UTC).replace(tzinfo=None)
            # Mark job as COMPLETED (no items is still a successful run)
            if job_id and job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                job.result = {"new_items": 0, "duplicates": 0, "failed": 0}
            db.commit()
            return

        logger.info(f"Fetched {len(items_data)} items from source: {source.name}")

        # Create ItemService and process items
        item_service = ItemService(db)
        new_items = []
        failed_count = 0

        for item_data in items_data:
            try:
                # Check if this is a duplicate before creating
                # Merge connector-provided raw_metadata with standard fields
                raw_metadata = item_data.get("raw_metadata", {})
                raw_metadata.update({
                    "author": item_data.get("author", ""),
                    "tags": item_data.get("tags", []),
                })

                item = item_service.create_item(
                    source_id=source_id,
                    external_id=item_data["external_id"],
                    url=item_data["url"],
                    title=item_data["title"],
                    raw_content=item_data.get("content", ""),
                    published_at=item_data["published_at"],
                    raw_metadata=raw_metadata,
                )

                # Only queue normalization for new items (not duplicates)
                # Check if this was a new item by comparing fetched_at
                if item is not None and item.status.value == ItemStatus.NEW.value:
                    new_items.append(item)

            except IntegrityError as e:
                # Duplicate item - expected, log and continue
                db.rollback()  # Reset session state after IntegrityError
                logger.warning(
                    f"Duplicate item detected from source {source_id}: {e}",
                    exc_info=True
                )
                continue
            except (ValueError, KeyError, TypeError) as e:
                # Invalid item data - log and continue
                logger.warning(
                    f"Invalid item data from source {source_id}: {e}",
                    exc_info=True
                )
                failed_count += 1
                continue
            except SQLAlchemyError as e:
                # Database error - log and re-raise for main handler
                logger.error(
                    f"Database error creating item from source {source_id}: {e}",
                    exc_info=True
                )
                raise

        # Update source statistics
        source.last_ingested_at = datetime.now(UTC).replace(tzinfo=None)
        source.total_items = (source.total_items or 0) + len(new_items)
        db.commit()

        duplicate_count = len(items_data) - len(new_items) - failed_count
        logger.info(
            f"Ingestion complete for {source.name}: "
            f"{len(new_items)} new items, {duplicate_count} duplicates, "
            f"{failed_count} failed"
        )

        # Queue normalization for each new item
        for item in new_items:
            # Get actor at runtime to avoid circular import
            normalize_actor = broker.get_actor("normalize_item")
            normalize_actor.send(item.item_id)
            logger.debug(f"Queued normalization for item: {item.item_id}")

        # Mark job as COMPLETED
        if job_id and job:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            job.result = {
                "new_items": len(new_items),
                "duplicates": duplicate_count,
                "failed": failed_count,
            }
            db.commit()
            logger.info(f"Job {job_id} marked as COMPLETED")

    except Exception as e:
        logger.error(f"Ingestion failed for source {source_id}: {e}", exc_info=True)

        # Mark job as FAILED
        if job_id:
            error_type = type(e).__name__
            error_message = str(e)[:500]  # Truncate long error messages
            _mark_job_failed(db, job_id, error_type, error_message)

        # Try RSS discovery for RSS sources
        if source and source.connector_type == "rss":
            try:
                new_feed_url = asyncio.run(_try_discover_rss(source))
                if new_feed_url:
                    logger.info(
                        f"Discovered new RSS URL for source {source_id}: {new_feed_url}"
                    )
                    source.config["feed_url"] = new_feed_url
                    source.consecutive_failures = 0
                    db.commit()
                    return
            except Exception as discover_error:
                logger.warning(f"RSS discovery failed: {discover_error}")

        # Update failure tracking
        if source:
            # Rollback any partial changes first
            db.rollback()
            # Now update failure tracking
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            source.last_error_at = datetime.now(UTC).replace(tzinfo=None)

            # Check if should freeze
            if source.consecutive_failures >= settings.max_consecutive_failures:
                source.status = SourceStatus.FROZEN
                source.review_reason = f"连续采集失败: {str(e)[:100]}"
                logger.warning(
                    f"Source {source_id} frozen after {source.consecutive_failures} consecutive failures"
                )

            # Commit the failure tracking
            db.commit()
        else:
            # No source found, just rollback
            db.rollback()

        raise

    finally:
        db.close()


async def _fetch_items(connector: "BaseConnector", source_url: str | None = None) -> list:
    """Fetch items from connector asynchronously.

    Args:
        connector: The connector instance to use.
        source_url: Optional source URL for context.

    Returns:
        List of item dictionaries or FetchResult.
    """
    try:
        return await connector.fetch()
    except Exception as e:
        logger.error(f"Failed to fetch items: {e}", exc_info=True)
        raise


async def _try_discover_rss(source: Source) -> str | None:
    """Try to discover new RSS URL for a source.

    Args:
        source: Source object with config containing feed_url

    Returns:
        New RSS URL if found, None otherwise
    """
    feed_url = source.config.get("feed_url", "")
    if not feed_url:
        return None

    # Extract site URL from feed URL
    parsed = urlparse(feed_url)
    site_url = f"{parsed.scheme}://{parsed.netloc}"

    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)
