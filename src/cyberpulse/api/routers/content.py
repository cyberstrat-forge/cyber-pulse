"""
Content API router.

Provides endpoints for retrieving deduplicated content items.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_client
from ..schemas.content import ContentResponse, ContentListResponse
from ...models import ApiClient
from ...services.content_service import ContentService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/content", response_model=ContentListResponse)
async def list_content(
    cursor: Optional[str] = Query(
        None,
        description="Pagination cursor (last content_id seen from previous page)"
    ),
    since: Optional[datetime] = Query(
        None,
        description="Filter contents first_seen_at >= since (ISO 8601)"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of results (1-1000)"
    ),
    source_tier: Optional[str] = Query(
        None,
        description="Filter by source tier (T0, T1, T2, T3) - not yet implemented"
    ),
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> ContentListResponse:
    """
    List content with cursor-based pagination.

    Returns deduplicated content items ordered by content_id descending
    (newest first due to timestamp prefix in ID).

    **Pagination:**
    - `cursor` is the last content_id from the previous page
    - Pass the `next_cursor` from the response to get the next page
    - `has_more` indicates if additional pages exist

    **Filtering:**
    - `since` filters by first_seen_at timestamp
    - `source_tier` filter is reserved for future use

    **Note:** content_id is generated with a timestamp prefix, so lexical
    ordering matches chronological ordering.
    """
    # Log the request for debugging
    logger.debug(
        f"list_content called by client {client.client_id}: "
        f"cursor={cursor}, since={since}, limit={limit}"
    )

    # Create content service
    service = ContentService(db)

    # Get contents from service
    # Note: ContentService.get_contents uses cursor to filter content_id < cursor
    # and orders by content_id DESC, returning newer items first
    contents = service.get_contents(
        since=since,
        cursor=cursor,
        limit=limit,
        source_tier=source_tier,  # Reserved for future use
    )

    # Determine if there are more results
    # We got 'limit' items, but we don't know if there are more
    # To check, we would need to fetch one more item
    # For simplicity, we assume there might be more if we got exactly 'limit' items
    has_more = len(contents) == limit

    # The next cursor is the last item's content_id
    next_cursor: Optional[str] = None
    if contents:
        next_cursor = str(contents[-1].content_id)

    # Build response
    return ContentListResponse(
        data=[ContentResponse.model_validate(c) for c in contents],
        next_cursor=next_cursor,
        has_more=has_more,
        count=len(contents),
        server_timestamp=datetime.now(timezone.utc),
    )


@router.get("/content/{content_id}", response_model=ContentResponse)
async def get_content(
    content_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> ContentResponse:
    """
    Get a single content item by ID.

    Returns the content with the specified content_id, or 404 if not found.

    **Path Parameters:**
    - `content_id`: The unique content identifier (e.g., cnt_20260319143052_a1b2c3d4)
    """
    # Log the request for debugging
    logger.debug(
        f"get_content called by client {client.client_id}: content_id={content_id}"
    )

    # Create content service
    service = ContentService(db)

    # Get content by ID
    content = service.get_content_by_id(content_id)

    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Content not found: {content_id}"
        )

    return ContentResponse.model_validate(content)