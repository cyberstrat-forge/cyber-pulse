"""Normalization tasks for processing items."""

import logging

import dramatiq
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from ..database import SessionLocal
from ..models import Item, ItemStatus
from ..services.normalization_service import NormalizationService
from ..services.title_parser_service import TitleParserService
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def normalize_item(item_id: str) -> None:
    """Normalize an item.

    This task:
    1. Gets item from database with source relationship
    2. Runs NormalizationService
    3. Optionally parses compound titles with TitleParserService
    4. Stores normalized content directly in Item fields
    5. Updates status to NORMALIZED
    6. Queues quality check

    Args:
        item_id: The item ID to normalize.
    """
    db = SessionLocal()
    try:
        # Get item from database with source relationship loaded
        item = (
            db.query(Item)
            .options(joinedload(Item.source))  # type: ignore[attr-defined]
            .filter(Item.item_id == item_id)
            .first()
        )
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting normalization for item: {item_id}")

        # Initialize services
        normalization_service = NormalizationService()
        title_parser = TitleParserService()

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

        # Get source name for title parsing (if available)
        source_name: str | None = None
        source = getattr(item, "source", None)
        if source:
            source_name = source.name

        # Parse compound title if applicable (e.g., Anthropic Research)
        normalized_title = result.normalized_title
        if source_name:
            parsed = title_parser.parse_compound_title(
                title=result.normalized_title,
                source_name=source_name,
            )
            # Use the parsed title if it differs from the original
            if parsed.title and parsed.title != result.normalized_title:
                normalized_title = parsed.title
                logger.debug(
                    f"Parsed compound title for {item_id}: "
                    f"category={parsed.category}, "
                    f"date={parsed.date}, "
                    f"title={parsed.title[:50]}..."
                )

        # Store normalized content directly in Item fields
        item.normalized_title = normalized_title  # type: ignore[assignment]
        item.normalized_body = result.normalized_body  # type: ignore[assignment]
        item.canonical_hash = result.canonical_hash  # type: ignore[assignment]
        item.word_count = result.word_count  # type: ignore[assignment]
        item.language = result.language  # type: ignore[assignment]

        # Update status to NORMALIZED
        item.status = ItemStatus.NORMALIZED  # type: ignore[assignment]

        db.commit()
        logger.info(
            f"Normalization complete for item: {item_id}, "
            f"status=NORMALIZED, word_count={result.word_count}"
        )

        # Queue quality check (get actor at runtime to avoid circular import)
        quality_actor = broker.get_actor("quality_check_item")
        quality_actor.send(
            item_id=item_id,
            normalized_title=normalized_title,
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
        # Get item from database with source relationship loaded
        item = (
            db.query(Item)
            .options(joinedload(Item.source))  # type: ignore[attr-defined]
            .filter(Item.item_id == item_id)
            .first()
        )
        if not item:
            logger.error(f"Item not found: {item_id}")
            return {"error": "Item not found", "item_id": item_id}

        # Initialize services
        normalization_service = NormalizationService()
        title_parser = TitleParserService()

        result = normalization_service.normalize(
            title=item.title,  # type: ignore[arg-type]
            raw_content=item.raw_content or "",  # type: ignore[arg-type]
            url=item.url,  # type: ignore[arg-type]
        )

        # Get source name for title parsing (if available)
        source_name: str | None = None
        source = getattr(item, "source", None)
        if source:
            source_name = source.name

        # Parse compound title if applicable
        normalized_title = result.normalized_title
        if source_name:
            parsed = title_parser.parse_compound_title(
                title=result.normalized_title,
                source_name=source_name,
            )
            if parsed.title and parsed.title != result.normalized_title:
                normalized_title = parsed.title

        # Store normalized content directly in Item fields
        item.normalized_title = normalized_title  # type: ignore[assignment]
        item.normalized_body = result.normalized_body  # type: ignore[assignment]
        item.canonical_hash = result.canonical_hash  # type: ignore[assignment]
        item.word_count = result.word_count  # type: ignore[assignment]
        item.language = result.language  # type: ignore[assignment]
        item.status = ItemStatus.NORMALIZED  # type: ignore[assignment]

        db.commit()

        return {
            "item_id": item_id,
            "normalized_title": normalized_title,
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
        logger.error(
            f"Database error during normalization for item {item_id}: {e}",
            exc_info=True,
        )
        db.rollback()
        raise
    except Exception as e:
        # Unexpected errors - log and re-raise
        logger.error(
            f"Unexpected error during normalization for item {item_id}: {e}",
            exc_info=True,
        )
        db.rollback()
        raise
    finally:
        db.close()
