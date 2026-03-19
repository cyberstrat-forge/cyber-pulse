"""Quality check tasks for validating normalized items."""

import logging
from typing import Optional

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus
from ..services.quality_gate_service import QualityGateService, QualityDecision
from ..services.content_service import ContentService
from ..services.normalization_service import NormalizationResult
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def quality_check_item(
    item_id: str,
    normalized_title: str,
    normalized_body: str,
    canonical_hash: str,
    language: Optional[str] = None,
    word_count: int = 0,
    extraction_method: str = "trafilatura",
) -> None:
    """Run quality check on an item.

    This task:
    1. Gets item and normalization result
    2. Runs QualityGateService
    3. If pass: create/update Content via ContentService
    4. If reject: mark item as rejected

    Args:
        item_id: The item ID to check.
        normalized_title: Normalized title from normalization.
        normalized_body: Normalized body from normalization.
        canonical_hash: Hash for deduplication.
        language: Detected language code.
        word_count: Word count of normalized body.
        extraction_method: Method used for extraction.
    """
    db = SessionLocal()
    try:
        # Get item from database
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting quality check for item: {item_id}")

        # Create normalization result object
        normalization_result = NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            canonical_hash=canonical_hash,
            language=language,
            word_count=word_count,
            extraction_method=extraction_method,
        )

        # Run quality check
        quality_service = QualityGateService()
        quality_result = quality_service.check(item, normalization_result)

        logger.debug(
            f"Quality check result for {item_id}: "
            f"decision={quality_result.decision.value}, "
            f"warnings={len(quality_result.warnings)}"
        )

        if quality_result.decision == QualityDecision.PASS:
            # Item passed quality check - create/update Content
            _handle_pass(db, item, normalization_result, quality_result)
        else:
            # Item rejected - mark as rejected
            _handle_reject(db, item, quality_result)

        db.commit()
        logger.info(
            f"Quality check complete for item {item_id}: "
            f"{quality_result.decision.value}"
        )

    except Exception as e:
        logger.error(f"Quality check failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def _handle_pass(
    db,
    item: Item,
    normalization_result: NormalizationResult,
    quality_result,
) -> None:
    """Handle a passed quality check.

    Creates or updates Content and links the item.

    Args:
        db: Database session.
        item: The item that passed.
        normalization_result: Normalization result with content.
        quality_result: Quality check result with metrics.
    """
    content_service = ContentService(db)

    # Create or get existing content by canonical_hash
    content, is_new = content_service.create_or_get_content(
        canonical_hash=normalization_result.canonical_hash,
        normalized_title=normalization_result.normalized_title,
        normalized_body=normalization_result.normalized_body,
        item=item,
    )

    # Update item status to mapped and store quality metrics
    item.status = ItemStatus.MAPPED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Update source statistics
    source = getattr(item, "source", None)  # type: ignore[attr-defined]
    if source and is_new:
        source.total_contents = (source.total_contents or 0) + 1  # type: ignore[assignment]

    logger.info(
        f"Content {'created' if is_new else 'updated'} for item {item.item_id}: "
        f"content_id={content.content_id}"
    )


def _handle_reject(db, item: Item, quality_result) -> None:
    """Handle a rejected quality check.

    Marks the item as rejected with the reason.

    Args:
        db: Database session.
        item: The rejected item.
        quality_result: Quality check result with rejection reason.
    """
    item.status = ItemStatus.REJECTED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Store rejection reason in raw_metadata
    if item.raw_metadata is None:
        item.raw_metadata = {}
    item.raw_metadata["rejection_reason"] = quality_result.rejection_reason
    item.raw_metadata["quality_warnings"] = quality_result.warnings

    logger.warning(
        f"Item {item.item_id} rejected: {quality_result.rejection_reason}"
    )


@dramatiq.actor(max_retries=3)
def recheck_item(item_id: str) -> None:
    """Re-run quality check on an item.

    Useful for reprocessing rejected items after source improvements.

    Args:
        item_id: The item ID to recheck.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        # Reset status to new and re-process
        item.status = ItemStatus.NEW  # type: ignore[assignment]
        db.commit()

        # Queue normalization (get actor at runtime to avoid circular import)
        normalize_actor = broker.get_actor("normalize_item")
        normalize_actor.send(item_id)

        logger.info(f"Queued re-processing for item: {item_id}")

    except Exception as e:
        logger.error(f"Recheck failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()