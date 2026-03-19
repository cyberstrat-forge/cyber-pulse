"""
Client API router.

Provides administrative endpoints for managing API clients.

Note: These endpoints do NOT require authentication as they are intended
for internal admin use. In production, these should be protected by
network-level access controls or admin authentication.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.client import (
    ClientCreate,
    ClientResponse,
    ClientCreatedResponse,
    ClientListResponse,
)
from ...models import ApiClientStatus
from ..auth import ApiClientService

logger = logging.getLogger(__name__)

router = APIRouter()

# client_id format: cli_{16 hex chars}
CLIENT_ID_PATTERN = re.compile(r"^cli_[a-f0-9]{16}$")


def validate_client_id(client_id: str) -> None:
    """Validate client_id format.

    Raises:
        HTTPException: If client_id format is invalid
    """
    if not CLIENT_ID_PATTERN.match(client_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid client_id format: {client_id}. Expected format: cli_xxxxxxxxxxxxxxxx"
        )


@router.post("/clients", response_model=ClientCreatedResponse, status_code=201)
async def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
) -> ClientCreatedResponse:
    """
    Create a new API client.

    **IMPORTANT**: The API key is returned ONCE in this response.
    Store it securely - it cannot be retrieved again.

    This is an administrative endpoint for internal use.
    """
    logger.info(f"Creating API client: name={client.name}")

    service = ApiClientService(db)
    new_client, plain_key = service.create_client(
        name=client.name,
        permissions=client.permissions,
        description=client.description,
    )

    logger.info(f"Created API client: client_id={new_client.client_id}")

    return ClientCreatedResponse(
        client=ClientResponse.model_validate(new_client),
        api_key=plain_key,
        warning="This API key will only be shown once. Store it securely immediately.",
    )


@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    status: Optional[str] = Query(
        None,
        description="Filter by status (active, suspended, revoked)"
    ),
    db: Session = Depends(get_db),
) -> ClientListResponse:
    """
    List all API clients.

    Returns all clients ordered by creation date (newest first).

    This is an administrative endpoint for internal use.
    """
    logger.debug(f"Listing API clients: status={status}")

    # Convert status string to enum if provided
    status_enum = None
    if status:
        try:
            status_enum = ApiClientStatus(status.lower())
        except ValueError:
            valid_statuses = [s.value for s in ApiClientStatus]
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}"
            )

    service = ApiClientService(db)
    clients = service.list_clients(status_filter=status_enum)

    return ClientListResponse(
        data=[ClientResponse.model_validate(c) for c in clients],
        count=len(clients),
        server_timestamp=datetime.now(timezone.utc),
    )


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
) -> None:
    """
    Revoke an API client.

    Sets the client status to 'revoked'. The client will no longer
    be able to authenticate.

    This is an administrative endpoint for internal use.

    **Note**: This is a soft delete - the client record remains in the
    database for audit purposes.
    """
    # Validate client_id format
    validate_client_id(client_id)

    logger.info(f"Revoking API client: client_id={client_id}")

    service = ApiClientService(db)
    success = service.revoke_client(client_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Client not found: {client_id}"
        )

    logger.info(f"Revoked API client: client_id={client_id}")