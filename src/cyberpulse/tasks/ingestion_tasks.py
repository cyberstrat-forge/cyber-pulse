"""Ingestion tasks for fetching items from sources."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import dramatiq
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..database import SessionLocal
from ..models import Source
from ..services.connector_factory import get_connector_for_source
from ..services.item_service import ItemService
from .worker import broker

if TYPE_CHECKING:
    from ..services.connector_service import BaseConnector

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str) -> None:
    """Ingest items from a source.

    This task:
    1. Gets source from database
    2. Uses connector_factory.get_connector_for_source() to create appropriate connector
    3. Calls connector.fetch() to get items
    4. Creates Item records via ItemService
    5. Queues normalize_item for each new item

    Args:
        source_id: The source ID to ingest from.
    """
    db = SessionLocal()
    try:
        # Get source from database
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            logger.error(f"Source not found: {source_id}")
            return

        logger.info(f"Starting ingestion for source: {source.name} ({source_id})")

        # Create connector for this source
        connector = get_connector_for_source(source)

        # Fetch items using async connector
        items_data = asyncio.run(_fetch_items(connector, None))

        if not items_data:
            logger.info(f"No items fetched from source: {source.name}")
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
                if item and item.status.value == "new":
                    new_items.append(item)

            except IntegrityError as e:
                # Duplicate item - expected, log and continue
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
        source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)  # type: ignore[assignment]
        source.total_items = (source.total_items or 0) + len(new_items)  # type: ignore[assignment]
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
        List of item dictionaries.
    """
    try:
        return await connector.fetch()
    except Exception as e:
        logger.error(f"Failed to fetch items: {e}", exc_info=True)
        raise