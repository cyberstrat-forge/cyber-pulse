"""Item management API router for admin endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ....models import Item, ItemStatus
from ....services.content_quality_service import ContentQualityService
from ....tasks.quality_tasks import quality_check_item
from ...auth import ApiClient, require_permissions
from ...dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/items/fix-stuck-pending")
async def fix_stuck_pending_items(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Fix items stuck in PENDING_FULL_FETCH with successful full fetch.

    These items have full_fetch_succeeded=True but are stuck in PENDING_FULL_FETCH
    status because quality_check_item doesn't check this flag.

    Fix strategy:
    - If content still insufficient: REJECT (correct status)
    - If content passes: re-trigger quality check (enter normal flow to MAPPED)
    """
    try:
        # Find stuck items
        stuck_items = db.query(Item).filter(
            Item.status == ItemStatus.PENDING_FULL_FETCH,
            Item.full_fetch_succeeded == True,  # noqa: E712
            Item.normalized_body.isnot(None),
        ).all()

        fixed_count = 0
        rejected_count = 0

        for item in stuck_items:
            # Check content quality
            content_service = ContentQualityService()
            content_result = content_service.check_quality(
                title=item.normalized_title,
                body=item.normalized_body,
            )

            if content_result.needs_full_fetch:
                # Content still insufficient -> REJECT
                item.status = ItemStatus.REJECTED  # type: ignore[assignment]
                if item.raw_metadata is None:
                    item.raw_metadata = {}
                item.raw_metadata["rejection_reason"] = (
                    f"Content quality still insufficient after full fetch (data fix): "
                    f"{content_result.reason}"
                )
                rejected_count += 1
                logger.info(
                    f"Item {item.item_id} rejected via data fix: "
                    f"{content_result.reason}"
                )
            else:
                # Content passed -> re-trigger quality check
                quality_check_item.send(
                    item_id=item.item_id,
                    normalized_title=item.normalized_title or "",
                    normalized_body=item.normalized_body or "",
                    canonical_hash=item.canonical_hash or "",
                    word_count=item.word_count or 0,
                )
                fixed_count += 1
                logger.info(
                    f"Item {item.item_id} queued for quality recheck via data fix"
                )

        db.commit()

        logger.info(
            f"Data fix complete: processed={len(stuck_items)}, "
            f"rejected={rejected_count}, queued_for_recheck={fixed_count}"
        )

        return {
            "status": "success",
            "processed_count": len(stuck_items),
            "rejected_count": rejected_count,
            "queued_for_recheck": fixed_count,
            "message": f"Processed {len(stuck_items)} stuck items: "
            f"{rejected_count} rejected, {fixed_count} queued for recheck",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Fix stuck pending items failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fix stuck items: {str(e)}"
        )
