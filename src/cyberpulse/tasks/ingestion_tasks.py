"""Ingestion tasks for fetching items from sources."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

import dramatiq
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from ..database import SessionLocal
from ..config import settings
from ..models import Source, SourceStatus
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


@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str) -> None:
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
    """
    db = SessionLocal()
    source = None
    try:
        # Get source from database
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            logger.error(f"Source not found: {source_id}")
            return

        # Skip frozen sources
        if source.status == SourceStatus.FROZEN:
            logger.debug(f"Skipping frozen source: {source.name}")
            return

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
            source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
                item = item_service.create_item(
                    source_id=source_id,
                    external_id=item_data["external_id"],
                    url=item_data["url"],
                    title=item_data["title"],
                    raw_content=item_data.get("content", ""),
                    published_at=item_data["published_at"],
                    content_hash=item_data["content_hash"],
                    raw_metadata={
                        "author": item_data.get("author", ""),
                        "tags": item_data.get("tags", []),
                    },
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
        source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
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

    except Exception as e:
        logger.error(f"Ingestion failed for source {source_id}: {e}", exc_info=True)

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
            source.last_error_at = datetime.now(timezone.utc).replace(tzinfo=None)

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


async def _fetch_items(connector: "BaseConnector", source_url: Optional[str] = None) -> list:
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


async def _try_discover_rss(source: Source) -> Optional[str]:
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