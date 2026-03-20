"""
Source API router.

Provides endpoints for managing intelligence sources.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_client
from ..schemas.source import (
    SourceCreate,
    SourceUpdate,
    SourceResponse,
    SourceListResponse,
)
from ...models import ApiClient, SourceTier, SourceStatus
from ...services.source_service import SourceService

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_tier(tier: str) -> SourceTier:
    """Validate and convert tier string to enum."""
    try:
        return SourceTier(tier.upper())
    except ValueError:
        valid_tiers = [t.value for t in SourceTier]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{tier}'. Must be one of: {valid_tiers}"
        )


def _validate_status(status: str) -> SourceStatus:
    """Validate and convert status string to enum."""
    try:
        return SourceStatus(status.upper())
    except ValueError:
        valid_statuses = [s.value for s in SourceStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}"
        )


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    tier: Optional[str] = Query(
        None,
        description="Filter by tier (T0, T1, T2, T3)"
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status (ACTIVE, FROZEN, REMOVED)"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of results (1-500)"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Offset for pagination"
    ),
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceListResponse:
    """
    List sources with optional filtering.

    Returns sources ordered by creation date (newest first).

    **Filtering:**
    - `tier` - Filter by source tier (T0, T1, T2, T3)
    - `status` - Filter by status (active, frozen, removed)

    **Pagination:**
    - Use `limit` and `offset` for page-based pagination
    """
    logger.debug(
        f"list_sources called by client {client.client_id}: "
        f"tier={tier}, status={status}, limit={limit}, offset={offset}"
    )

    # Convert query params to enums if provided
    tier_enum = None
    if tier:
        tier_enum = _validate_tier(tier)

    status_enum = None
    if status:
        status_enum = _validate_status(status)

    # Create service and get sources
    service = SourceService(db)
    sources = service.list_sources(
        tier=tier_enum,
        status=status_enum,
        limit=limit,
        offset=offset,
    )

    # Build response
    return SourceListResponse(
        data=[SourceResponse.model_validate(s) for s in sources],
        count=len(sources),
        offset=offset,
        limit=limit,
        server_timestamp=datetime.now(timezone.utc),
    )


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    source: SourceCreate,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """
    Create a new source.

    New sources enter observation period by default (30 days).

    **Tier/Score Rules:**
    - If both `tier` and `score` provided: use as-is
    - If only `score` provided: tier is derived from score
    - If only `tier` provided: score defaults to tier's middle value
    - If neither provided: defaults to T2 with score 50

    **Tier-Score Mapping:**
    - T0: score >= 80
    - T1: 60 <= score < 80
    - T2: 40 <= score < 60
    - T3: score < 40
    """
    logger.debug(
        f"create_source called by client {client.client_id}: name={source.name}"
    )

    # Convert tier string to enum if provided
    tier_enum = None
    if source.tier:
        tier_enum = _validate_tier(source.tier)

    # Create service and add source
    service = SourceService(db)
    created_source, message = service.add_source(
        name=source.name,
        connector_type=source.connector_type,
        tier=tier_enum,
        config=source.config or {},
        score=source.score,
    )

    if created_source is None:
        # Duplicate name
        raise HTTPException(
            status_code=409,
            detail=message
        )

    return SourceResponse.model_validate(created_source)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """
    Get a single source by ID.

    Returns the source with the specified source_id, or 404 if not found.
    """
    logger.debug(
        f"get_source called by client {client.client_id}: source_id={source_id}"
    )

    # Query source directly
    from ...models import Source
    source = db.query(Source).filter(Source.source_id == source_id).first()

    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source not found: {source_id}"
        )

    return SourceResponse.model_validate(source)


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    source: SourceUpdate,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """
    Update a source.

    Only provided fields will be updated. Removed sources cannot be updated.

    **Note:** When updating tier or score:
    - Updating `score` will auto-adjust `tier` to match
    - Updating `tier` will auto-adjust `score` to tier's default
    """
    logger.debug(
        f"update_source called by client {client.client_id}: source_id={source_id}"
    )

    # Build update kwargs from non-None fields
    update_data = source.model_dump(exclude_unset=True, exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields to update"
        )

    # Create service and update source
    service = SourceService(db)
    updated_source, message = service.update_source(source_id, **update_data)

    if updated_source is None:
        # Source not found or is removed
        if "not found" in message.lower():
            raise HTTPException(
                status_code=404,
                detail=message
            )
        elif "removed" in message.lower():
            raise HTTPException(
                status_code=400,
                detail=message
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=message
            )

    return SourceResponse.model_validate(updated_source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a source (soft delete).

    Sets the source status to 'removed'. The source remains in the database
    but will not appear in default list queries.

    **Note:** This is a soft delete - the source can be recovered by
    updating its status back to 'active'.
    """
    logger.debug(
        f"delete_source called by client {client.client_id}: source_id={source_id}"
    )

    # Create service and remove source
    service = SourceService(db)
    success, message = service.remove_source(source_id)

    if not success:
        # Source not found
        raise HTTPException(
            status_code=404,
            detail=message
        )