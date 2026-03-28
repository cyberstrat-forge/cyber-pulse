"""Full content fetch tasks.

Task fetches full content using two-level strategy:
- Level 1: httpx + trafilatura
- Level 2: Jina AI Reader (20 RPM)

On success: item -> NORMALIZED -> quality_check
On failure: item -> REJECTED
"""

import asyncio
import logging

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus
from ..services.full_content_fetch_service import FullContentFetchService

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=2, max_concurrency=3)
def fetch_full_content(item_id: str) -> dict:
    """Fetch full content for an item.

    Max concurrency is 3 to respect Jina AI 20 RPM limit.

    Args:
        item_id: The item ID to fetch content for.

    Returns:
        Dictionary with fetch result.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return {"error": "Item not found", "item_id": item_id}

        # Skip if already attempted
        if item.full_fetch_attempted:
            logger.debug(f"Full fetch already attempted for {item_id}")
            return {"item_id": item_id, "skipped": True}

        url = item.url
        if not url:
            # No URL - reject immediately
            item.full_fetch_attempted = True  # type: ignore[assignment]
            item.full_fetch_succeeded = False  # type: ignore[assignment]
            item.status = ItemStatus.REJECTED  # type: ignore[assignment]
            db.commit()
            logger.warning(f"Item {item_id} has no URL, marking REJECTED")
            return {"item_id": item_id, "error": "No URL", "status": "REJECTED"}

        logger.info(f"Fetching full content for {item_id}")

        service = FullContentFetchService()
        result = asyncio.run(service.fetch_full_content(str(url)))

        # Update item
        item.full_fetch_attempted = True  # type: ignore[assignment]

        if result.success and result.content:
            item.full_fetch_succeeded = True  # type: ignore[assignment]
            item.raw_content = result.content  # type: ignore[assignment]
            # Set to NORMALIZED to trigger re-quality-check
            item.status = ItemStatus.NORMALIZED  # type: ignore[assignment]
            logger.info(
                f"Full content fetched: {len(result.content)} chars "
                f"via {result.level}"
            )

            db.commit()

            # Re-normalize with new content
            from .normalization_tasks import normalize_item
            normalize_item.send(item_id)

            return {
                "item_id": item_id,
                "success": True,
                "content_length": len(result.content),
                "level": result.level,
            }
        else:
            # Full fetch failed - REJECT the item
            item.full_fetch_succeeded = False  # type: ignore[assignment]
            item.status = ItemStatus.REJECTED  # type: ignore[assignment]
            logger.warning(
                f"Full fetch failed for {item_id}: {result.error}, "
                "marking REJECTED"
            )

            db.commit()

            return {
                "item_id": item_id,
                "success": False,
                "error": result.error,
                "status": "REJECTED",
            }

    except Exception as e:
        logger.error(f"Full fetch failed for {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
