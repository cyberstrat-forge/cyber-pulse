"""Client management API router for admin endpoints."""

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete  # 新增
from sqlalchemy.orm import Session

from ....models import ApiClient, ApiClientStatus  # 添加 ApiClient
from ...auth import ApiClient, ApiClientService, require_permissions
from ...dependencies import get_db
from ...schemas.client import (
    ClientCreate,
    ClientCreatedResponse,
    ClientListResponse,
    ClientResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# client_id format: cli_{16 hex chars}
CLIENT_ID_PATTERN = re.compile(r"^cli_[a-f0-9]{16}$")


def validate_client_id(client_id: str) -> None:
    """Validate client_id format."""
    if not CLIENT_ID_PATTERN.match(client_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid client_id format: {client_id}. Expected format: cli_xxxxxxxx"
        )


@router.post("/clients", response_model=ClientCreatedResponse, status_code=201)
async def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientCreatedResponse:
    """Create a new API client."""
    logger.info(f"Creating API client: name={client.name}")

    service = ApiClientService(db)
    new_client, plain_key = service.create_client(
        name=client.name,
        permissions=client.permissions,
        description=client.description,
        expires_at=client.expires_at,
    )

    logger.info(f"Created API client: client_id={new_client.client_id}")

    return ClientCreatedResponse(
        client=ClientResponse.model_validate(new_client),
        api_key=plain_key,
        warning="This API key will only be shown once. Store it securely immediately.",
    )


@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    status: str | None = Query(None, description="Filter by status: ACTIVE, SUSPENDED, REVOKED"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientListResponse:
    """List all API clients."""
    logger.debug(f"Listing API clients: status={status}")

    status_enum = None
    if status:
        try:
            status_enum = ApiClientStatus(status.upper())
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
        server_timestamp=datetime.now(UTC),
    )


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientResponse:
    """Get client details."""
    validate_client_id(client_id)

    service = ApiClientService(db)
    client = service.get_client(client_id)

    if not client:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    return ClientResponse.model_validate(client)


@router.post("/clients/{client_id}/rotate", response_model=ClientCreatedResponse)
async def rotate_client_key(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientCreatedResponse:
    """Rotate an API client's key."""
    validate_client_id(client_id)

    logger.info(f"Rotating API key for client: {client_id}")

    service = ApiClientService(db)
    result = service.rotate_key(client_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    client, plain_key = result

    logger.info(f"Rotated API key for client: {client_id}")

    return ClientCreatedResponse(
        client=ClientResponse.model_validate(client),
        api_key=plain_key,
        warning="The new API key will only be shown once. Store it securely immediately.",
    )


@router.post("/clients/{client_id}/suspend", response_model=ClientResponse)
async def suspend_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientResponse:
    """Suspend an API client."""
    validate_client_id(client_id)

    service = ApiClientService(db)
    success = service.suspend_client(client_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    client = service.get_client(client_id)
    return ClientResponse.model_validate(client)


@router.post("/clients/{client_id}/activate", response_model=ClientResponse)
async def activate_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientResponse:
    """Activate (or reactivate) an API client."""
    validate_client_id(client_id)

    service = ApiClientService(db)
    success = service.activate_client(client_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    client = service.get_client(client_id)
    return ClientResponse.model_validate(client)


@router.delete("/clients/{client_id}", status_code=200)
async def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Delete an API client (permanent deletion).

    This is a hard delete. The client will be permanently removed
    from the database and cannot be recovered.
    """
    validate_client_id(client_id)

    logger.info(f"Deleting API client: {client_id}")

    result = db.execute(
        delete(ApiClient).where(ApiClient.client_id == client_id)
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    db.commit()

    return {"message": f"Client {client_id} deleted"}
