"""
Client API schemas.

Pydantic models for Client API request/response validation.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    """Schema for creating a new API client."""

    name: str = Field(
        ...,
        description="Client name for identification",
        min_length=1,
        max_length=255
    )
    permissions: list[str] | None = Field(
        default_factory=list,
        description="List of permissions for this client (e.g., ['read', 'write'])"
    )
    description: str | None = Field(
        None,
        description="Optional description of the client's purpose"
    )
    expires_at: datetime | None = Field(
        None,
        description="Optional expiration time. None means never expires."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Analytics Service",
                "permissions": ["read"],
                "description": "Client for analytics dashboard",
                "expires_at": None
            }
        }
    }


class ClientResponse(BaseModel):
    """
    Single client response.

    IMPORTANT: The API key is NEVER returned in this response.
    Only the plain API key is returned once when creating a client.
    """

    client_id: str = Field(..., description="Unique client identifier")
    name: str = Field(..., description="Client name")
    status: str = Field(..., description="Client status (ACTIVE, SUSPENDED, REVOKED)")
    permissions: list[str] = Field(
        default_factory=list,
        description="List of permissions for this client"
    )
    description: str | None = Field(None, description="Client description")
    expires_at: datetime | None = Field(
        None,
        description="Expiration time. None means never expires."
    )
    last_used_at: datetime | None = Field(
        None,
        description="When the client was last used"
    )
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "client_id": "cli_a1b2c3d4",
                "name": "Analytics Service",
                "status": "ACTIVE",
                "permissions": ["read"],
                "description": "Client for analytics dashboard",
                "expires_at": None,
                "last_used_at": "2026-03-19T10:00:00Z",
                "created_at": "2026-03-19T08:00:00Z",
                "updated_at": "2026-03-19T08:00:00Z"
            }
        }
    }


class ClientCreatedResponse(BaseModel):
    """
    Response for client creation.

    This is the ONLY time the plain API key is shown.
    The key cannot be retrieved again - store it securely.

    WARNING: The API key should be stored securely immediately.
    It cannot be retrieved later.
    """

    client: ClientResponse = Field(..., description="The created client")
    api_key: str = Field(
        ...,
        description="The plain API key. STORE THIS SECURELY - it cannot be retrieved again!"
    )
    warning: str = Field(
        default="This API key will only be shown once. Store it securely immediately.",
        description="Warning about API key visibility"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "client": {
                    "client_id": "cli_a1b2c3d4",
                    "name": "Analytics Service",
                    "status": "ACTIVE",
                    "permissions": ["read"],
                    "description": "Client for analytics dashboard",
                    "expires_at": None,
                    "last_used_at": None,
                    "created_at": "2026-03-19T08:00:00Z",
                    "updated_at": "2026-03-19T08:00:00Z"
                },
                "api_key": "cp_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
                "warning": "This API key will only be shown once. Store it securely immediately."
            }
        }
    }


class ClientListResponse(BaseModel):
    """
    List of API clients.

    Simple list response without pagination (admin endpoints typically
    have fewer clients).
    """

    data: list[ClientResponse] = Field(
        default_factory=list,
        description="List of API clients"
    )
    count: int = Field(..., description="Number of clients returned")
    server_timestamp: datetime = Field(
        ...,
        description="Server timestamp when response was generated"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "data": [
                    {
                        "client_id": "cli_a1b2c3d4",
                        "name": "Analytics Service",
                        "status": "ACTIVE",
                        "permissions": ["read"],
                        "description": "Client for analytics dashboard",
                        "last_used_at": "2026-03-19T10:00:00Z",
                        "created_at": "2026-03-19T08:00:00Z",
                        "updated_at": "2026-03-19T08:00:00Z"
                    }
                ],
                "count": 1,
                "server_timestamp": "2026-03-19T16:00:00Z"
            }
        }
    }
