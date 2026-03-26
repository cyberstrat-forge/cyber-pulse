"""Items API router.

Business API for downstream systems to fetch intelligence items.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..dependencies import get_db
from ..schemas.item import ItemResponse, ItemListResponse, SourceInItem
from ..auth import require_permissions, ApiClient
from ...models import Item, Source, ItemStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# Cursor format: item_{YYYYMMDDHHMMSS}_{uuid8}
CURSOR_PATTERN = re.compile(r"^item_\d{14}_[a-f0-9]{8}$")


def validate_cursor(cursor: str) -> None:
    """Validate cursor format."""
    if not CURSOR_PATTERN.match(cursor):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cursor format: {cursor}"
        )


def calculate_completeness_score(item: Item) -> float:
    """Calculate completeness score for an item."""
    meta = item.meta_completeness or 0.0
    content = item.content_completeness or 0.0
    noise = item.noise_ratio or 0.0

    return meta * 0.4 + content * 0.4 + (1 - noise) * 0.2


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    since: Optional[datetime] = Query(None, description="Start time"),
    until: Optional[datetime] = Query(None, description="End time"),
    from_param: Optional[str] = Query(None, alias="from", description="Start position: latest or beginning"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _client: ApiClient = Depends(require_permissions(["read"])),
) -> ItemListResponse:
    """
    Fetch intelligence items.

    Supports cursor-based pagination for incremental sync.
    """
    # Validate cursor and from are not both provided
    if cursor and from_param:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both cursor and from parameters"
        )

    # Validate cursor format
    if cursor:
        validate_cursor(cursor)

    # Build query
    query = db.query(Item).filter(Item.status != ItemStatus.REJECTED)

    # Apply time filters
    if since:
        query = query.filter(Item.published_at >= since)
    if until:
        query = query.filter(Item.published_at < until)

    # Apply cursor/pagination
    if cursor:
        # Find item with this cursor
        cursor_item = db.query(Item).filter(Item.item_id == cursor).first()
        if not cursor_item:
            raise HTTPException(
                status_code=404,
                detail=f"Cursor item not found: {cursor}"
            )
        query = query.filter(Item.fetched_at < cursor_item.fetched_at)
    elif from_param == "beginning":
        # Start from earliest
        query = query.order_by(Item.fetched_at.asc())
    else:
        # Default: latest first
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
            fetched_at=item.fetched_at,
            source=source_info,
        ))

    next_cursor = None
    if has_more and items:
        next_cursor = items[-1].item_id

    return ItemListResponse(
        data=data,
        next_cursor=next_cursor,
        has_more=has_more,
        count=len(data),
        server_timestamp=datetime.now(timezone.utc),
    )