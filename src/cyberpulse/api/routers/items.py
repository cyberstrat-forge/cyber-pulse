"""Items API router.

Business API for downstream systems to fetch intelligence items.
"""

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from ...models import Item, ItemStatus, Source
from ..auth import ApiClient, require_permissions
from ..dependencies import get_db
from ..schemas.item import ItemListResponse, ItemResponse, SourceInItem

logger = logging.getLogger(__name__)

router = APIRouter()

# Cursor format: item_{uuid8}
CURSOR_PATTERN = re.compile(r"^item_[a-f0-9]{8}$")


def validate_cursor(cursor: str) -> None:
    """Validate cursor format."""
    if not CURSOR_PATTERN.match(cursor):
        raise HTTPException(status_code=400, detail=f"Invalid cursor format: {cursor}")


def calculate_completeness_score(item: Item) -> float:
    """Calculate completeness score for an item."""
    meta = item.meta_completeness or 0.0
    content = item.content_completeness or 0.0

    score = meta * 0.5 + content * 0.5
    return round(score, 3)


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    since: str | None = Query(
        None, description="'beginning' or ISO 8601 datetime for incremental sync"
    ),
    cursor: str | None = Query(None, description="Pagination cursor (item_id)"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _client: ApiClient = Depends(require_permissions(["read"])),
) -> ItemListResponse:
    """
    Fetch intelligence items.

    Supports timestamp-based incremental sync.

    Args:
        since: "beginning" for full sync, or ISO 8601 datetime for incremental sync
        cursor: Pagination cursor (must be used with since)
        limit: Page size (1-100)
    """
    # Validate: cursor must be used with since
    if cursor and not since:
        raise HTTPException(
            status_code=400, detail="cursor must be used with since parameter"
        )

    # Validate cursor format
    if cursor:
        validate_cursor(cursor)

    # Parse since parameter
    since_datetime = None
    if since and since != "beginning":
        try:
            # Handle Z suffix (UTC)
            if since.endswith("Z"):
                since_datetime = datetime.fromisoformat(since.replace("Z", "+00:00"))
            else:
                since_datetime = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid since format: {since}. "
                "Use 'beginning' or ISO 8601 datetime.",
            )

    # Build query - only expose MAPPED items to downstream systems
    query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)

    # Apply time filter (based on fetched_at, not published_at)
    if since_datetime:
        query = query.filter(Item.fetched_at >= since_datetime)

    # Apply cursor skip
    if cursor:
        cursor_item = db.query(Item).filter(Item.item_id == cursor).first()
        if not cursor_item:
            raise HTTPException(
                status_code=404, detail=f"Cursor item not found: {cursor}"
            )
        if cursor_item.fetched_at is None:
            raise HTTPException(
                status_code=400,
                detail=f"Cursor item has no fetched_at timestamp: {cursor}",
            )
        query = query.filter(Item.fetched_at > cursor_item.fetched_at)

    # Apply ordering: ascending if since provided, descending otherwise
    if since:
        query = query.order_by(asc(Item.fetched_at))
    else:
        query = query.order_by(desc(Item.fetched_at))

    # Fetch items
    items = query.limit(limit + 1).all()
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    # Prefetch sources in a single query to avoid N+1
    source_ids = {item.source_id for item in items if item.source_id}
    sources = db.query(Source).filter(Source.source_id.in_(source_ids)).all()
    source_map = {s.source_id: s for s in sources}

    # Build response
    data = []
    for item in items:
        source = source_map.get(item.source_id)
        source_info = None
        if source:
            source_info = SourceInItem(
                source_id=source.source_id,
                source_name=source.name,
                source_url=source.config.get("feed_url") if source.config else None,
                source_tier=source.tier.value if source.tier else None,
                source_score=source.score,
            )

        data.append(ItemResponse(
            id=item.item_id,
            title=item.normalized_title or item.title,
            author=item.raw_metadata.get("author") if item.raw_metadata else None,
            published_at=item.published_at,
            body=item.normalized_body,
            url=item.url,
            completeness_score=calculate_completeness_score(item),
            tags=item.raw_metadata.get("tags", []) if item.raw_metadata else [],
            word_count=item.word_count,
            fetched_at=item.fetched_at,
            source=source_info,
        ))

    # Build pagination fields
    last_item_id = items[-1].item_id if items else None
    last_fetched_at = items[-1].fetched_at if items else None

    return ItemListResponse(
        data=data,
        last_item_id=last_item_id,
        last_fetched_at=last_fetched_at,
        has_more=has_more,
        count=len(data),
        server_timestamp=datetime.now(UTC),
    )
