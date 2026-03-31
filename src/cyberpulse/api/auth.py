"""
API Key authentication module.

Provides secure API key generation, hashing, and validation for API clients.
"""

import logging
import secrets
from datetime import UTC, datetime

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.api_client import ApiClient, ApiClientStatus

logger = logging.getLogger(__name__)

security = HTTPBearer()


def generate_api_key() -> str:
    """
    Generate a new API key.

    Format: cp_live_{random_32_chars}
    Example: cp_live_<32_hex_characters>

    The key is returned ONCE when created and cannot be retrieved again.
    """
    random_part = secrets.token_hex(16)  # 32 hex chars
    return f"cp_live_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    Uses bcrypt for secure one-way hashing.
    The original key cannot be recovered from the hash.
    """
    # bcrypt requires bytes input
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(api_key.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    try:
        return bcrypt.checkpw(
            plain_key.encode("utf-8"),
            hashed_key.encode("utf-8")
        )
    except (ValueError, TypeError, UnicodeError) as e:
        # Expected errors: malformed input, corrupted hash, encoding issues
        logger.warning(f"API key verification failed: {e}")
        return False
    except Exception as e:
        # Unexpected error - log at error level and re-raise
        logger.error(f"Unexpected error during API key verification: {e}")
        raise


async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> ApiClient:
    """
    Validate API key and return client.

    1. Extract Bearer token from Authorization header
    2. Look up client by hashed API key
    3. Check if client is active
    4. Update last_used_at timestamp
    5. Return client object

    Raises:
        HTTPException 401: Invalid or expired API key
    """
    api_key = credentials.credentials

    # Get all active clients and check their hashed keys
    # We cannot query by hash directly since we need to verify each one
    clients = db.query(ApiClient).filter(
        ApiClient.status == ApiClientStatus.ACTIVE
    ).all()

    for client in clients:
        if verify_api_key(api_key, client.api_key):  # type: ignore[arg-type]
            # Update last_used_at timestamp
            client.last_used_at = datetime.now(UTC)  # type: ignore[assignment]
            try:
                db.commit()
            except SQLAlchemyError as e:
                # Database error - log and rollback, but don't fail auth
                logger.error(f"Failed to update last_used_at: {e}")
                db.rollback()
                # Continue with authentication - don't fail the request
            return client

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_permissions(permissions: list[str]):
    """
    Dependency factory for permission checking.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            client: ApiClient = Depends(require_permissions(["admin"]))
        ):
            ...

    Args:
        permissions: List of required permissions (any one is sufficient)

    Returns:
        Dependency function that validates permissions
    """
    async def permission_checker(
        client: ApiClient = Depends(get_current_client),
    ) -> ApiClient:
        client_permissions: list[str] = client.permissions or []  # type: ignore[assignment]
        if not any(perm in client_permissions for perm in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return client

    return permission_checker


class ApiClientService:
    """Service for managing API clients."""

    def __init__(self, db: Session):
        self.db = db

    def create_client(
        self,
        name: str,
        permissions: list[str] | None = None,
        description: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[ApiClient, str]:
        """
        Create a new API client.

        Args:
            name: Client name
            permissions: List of permissions for this client
            description: Optional description
            expires_at: Optional expiration time (None = never expires)

        Returns:
            Tuple of (ApiClient, plain_api_key)
            The plain_api_key should be shown to user ONCE and never stored.
        """
        # Generate client ID
        client_id = f"cli_{secrets.token_hex(8)}"

        # Generate and hash API key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        # Create client record
        client = ApiClient(
            client_id=client_id,
            name=name,
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=permissions or [],
            description=description,
            expires_at=expires_at,
        )

        self.db.add(client)
        try:
            self.db.commit()
            self.db.refresh(client)
            logger.info(f"Created API client: {client_id}")
            return client, plain_key
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create API client: {e}")
            raise

    def validate_client(self, api_key: str) -> ApiClient | None:
        """
        Validate API key and return client if valid.

        This method checks all active clients to find a matching key.
        Used internally for authentication.

        Args:
            api_key: The plain API key to validate

        Returns:
            ApiClient if valid, None otherwise
        """
        active_clients = self.db.query(ApiClient).filter(
            ApiClient.status == ApiClientStatus.ACTIVE
        ).all()

        for client in active_clients:
            if verify_api_key(api_key, client.api_key):  # type: ignore[arg-type]
                # Update last_used_at
                client.last_used_at = datetime.now(UTC)  # type: ignore[assignment]
                try:
                    self.db.commit()
                except SQLAlchemyError as e:
                    logger.error(f"Failed to update last_used_at in validate_client: {e}")
                    self.db.rollback()
                return client

        return None

    def activate_client(self, client_id: str) -> bool:
        """
        Activate (or reactivate) an API client.

        Args:
            client_id: The client ID to activate

        Returns:
            True if activated, False if client not found
        """
        client = self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

        if not client:
            return False

        client.status = ApiClientStatus.ACTIVE  # type: ignore[assignment]
        try:
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to activate client {client_id}: {e}")
            self.db.rollback()
            raise
        logger.info(f"Activated API client: {client_id}")
        return True

    def suspend_client(self, client_id: str) -> bool:
        """
        Suspend an API client's access.

        Args:
            client_id: The client ID to suspend

        Returns:
            True if suspended, False if client not found
        """
        client = self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

        if not client:
            return False

        client.status = ApiClientStatus.SUSPENDED  # type: ignore[assignment]
        try:
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to suspend client {client_id}: {e}")
            self.db.rollback()
            raise
        logger.info(f"Suspended API client: {client_id}")
        return True

    def get_client(self, client_id: str) -> ApiClient | None:
        """
        Get a client by ID.

        Args:
            client_id: The client ID

        Returns:
            ApiClient if found, None otherwise
        """
        return self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

    def list_clients(
        self,
        status_filter: ApiClientStatus | None = None,
    ) -> list[ApiClient]:
        """
        List all API clients.

        Args:
            status_filter: Optional status to filter by

        Returns:
            List of ApiClient objects
        """
        query = self.db.query(ApiClient)
        if status_filter:
            query = query.filter(ApiClient.status == status_filter)
        return query.order_by(ApiClient.created_at.desc()).all()

    def rotate_key(self, client_id: str) -> tuple[ApiClient, str] | None:
        """
        Rotate an API client's key.

        Args:
            client_id: The client ID to rotate

        Returns:
            Tuple of (ApiClient, new_plain_key) if successful, None otherwise
        """
        client = self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

        if not client:
            return None

        # Generate and hash new API key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        client.api_key = hashed_key  # type: ignore[assignment]
        try:
            self.db.commit()
            self.db.refresh(client)
            logger.info(f"Rotated API key for client: {client_id}")
            return client, plain_key
        except SQLAlchemyError as e:
            logger.error(f"Failed to rotate key for {client_id}: {e}")
            self.db.rollback()
            raise

    def reset_admin_key(self) -> tuple[ApiClient, str] | None:
        """
        Reset admin API key.

        Generates a new key for the first client with 'admin' permission.
        The old key immediately becomes invalid.

        Returns:
            Tuple of (ApiClient, new_plain_key) if successful, None otherwise
        """
        admin = self.get_by_permission("admin")
        if not admin:
            return None

        # Generate and hash new API key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        admin.api_key = hashed_key  # type: ignore[assignment]
        try:
            self.db.commit()
            self.db.refresh(admin)
            logger.info(f"Reset admin API key for client: {admin.client_id}")
            return admin, plain_key
        except SQLAlchemyError as e:
            logger.error(f"Failed to reset admin key: {e}")
            self.db.rollback()
            raise

    def get_by_permission(self, permission: str) -> ApiClient | None:
        """
        Get first client with specific permission.

        Args:
            permission: Permission to search for

        Returns:
            ApiClient if found, None otherwise
        """
        clients = self.db.query(ApiClient).filter(
            ApiClient.status == ApiClientStatus.ACTIVE
        ).all()

        for client in clients:
            perms: list[str] = client.permissions or []  # type: ignore[assignment]
            if permission in perms:
                return client
        return None
