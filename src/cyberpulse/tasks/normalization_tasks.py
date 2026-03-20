"""Normalization tasks for processing items."""

import logging

import dramatiq
from sqlalchemy.exc import SQLAlchemyError

from ..database import SessionLocal
from ..models import Item
from ..models.item import ItemStatus
from ..services.item_service import ItemService
from ..services.normalization_service import NormalizationService
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def normalize_item(item_id: str) -> None:
    """Normalize an item.

    This task:
    1. Gets item from database
    2. Runs NormalizationService
    3. Updates item with normalized content
    4. Queues quality check

    Args:
        item_id: The item ID to normalize.
    """
    db = SessionLocal()
    try:
        # Get item from database
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting normalization for item: {item_id}")

        # Initialize services
        normalization_service = NormalizationService()

        # Run normalization
        result = normalization_service.normalize(
            title=item.title,  # type: ignore[arg-type]
            raw_content=item.raw_content or "",  # type: ignore[arg-type]
            url=item.url,  # type: ignore[arg-type]
        )

        logger.debug(
            f"Normalization complete for {item_id}: "
            f"word_count={result.word_count}, "
            f"language={result.language}"
        )

        # Update item status and store normalization result
        item_service = ItemService(db)
        updated_item = item_service.update_item_status(
            item_id=item_id,
            status=ItemStatus.NORMALIZED.value,
            quality_metrics={
                "meta_completeness": None,  # Will be set by quality gate
                "content_completeness": None,
                "noise_ratio": None,
            },
        )

        if not updated_item:
            logger.error(f"Failed to update item status: {item_id}")
            return

        # Store normalization result in item for quality check
        # We pass the normalization result to the quality check task
        logger.info(f"Normalization complete for item: {item_id}")

        # Queue quality check (get actor at runtime to avoid circular import)
        quality_actor = broker.get_actor("quality_check_item")
        quality_actor.send(
            item_id=item_id,
            normalized_title=result.normalized_title,
            normalized_body=result.normalized_body,
            canonical_hash=result.canonical_hash,
            language=result.language,
            word_count=result.word_count,
            extraction_method=result.extraction_method,
        )

    except Exception as e:
        logger.error(f"Normalization failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


@dramatiq.actor(max_retries=3)
def normalize_item_with_result(item_id: str) -> dict:
    """Normalize an item and return the result.

    This is a variant that stores the result in Redis for retrieval.
    Note: Only expected errors (ValueError, KeyError, TypeError) return
    error dicts. Database errors and unexpected exceptions are re-raised.

    Args:
        item_id: The item ID to normalize.

    Returns:
        Dictionary with normalization result or error.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return {"error": "Item not found", "item_id": item_id}

        normalization_service = NormalizationService()
        result = normalization_service.normalize(
            title=item.title,  # type: ignore[arg-type]
            raw_content=item.raw_content or "",  # type: ignore[arg-type]
            url=item.url,  # type: ignore[arg-type]
        )

        item_service = ItemService(db)
        item_service.update_item_status(item_id=item_id, status="normalized")

        return {
            "item_id": item_id,
            "normalized_title": result.normalized_title,
            "normalized_body": result.normalized_body,
            "canonical_hash": result.canonical_hash,
            "language": result.language,
            "word_count": result.word_count,
            "extraction_method": result.extraction_method,
        }

    except (ValueError, KeyError, TypeError) as e:
        # Expected errors - return error dict for caller to handle
        logger.warning(f"Normalization failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        return {"error": str(e), "item_id": item_id}
    except SQLAlchemyError as e:
        # Database error - log and re-raise
        logger.error(f"Database error during normalization for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    except Exception as e:
        # Unexpected errors - log and re-raise
        logger.error(f"Unexpected error during normalization for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()