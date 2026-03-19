"""
Tests for API key authentication module.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from cyberpulse.api.auth import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    get_current_client,
    require_permissions,
    ApiClientService,
)
from cyberpulse.api.main import app
from cyberpulse.models.api_client import ApiClient, ApiClientStatus


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_api_key_format(self):
        """Test that generated API key has correct format."""
        key = generate_api_key()

        assert key.startswith("cp_live_")
        # "cp_live_" (8 chars) + 32 hex chars = 40 total
        assert len(key) == 40

    def test_generate_api_key_unique(self):
        """Test that generated API keys are unique."""
        keys = [generate_api_key() for _ in range(100)]
        assert len(set(keys)) == 100

    def test_generate_api_key_random_part_is_hex(self):
        """Test that random part contains only hex characters."""
        key = generate_api_key()
        random_part = key[8:]  # Remove "cp_live_" prefix
        # Verify it's valid hex
        try:
            int(random_part, 16)
        except ValueError:
            pytest.fail("Random part is not valid hexadecimal")


class TestHashAndVerifyApiKey:
    """Tests for API key hashing and verification."""

    def test_hash_and_verify_api_key(self):
        """Test that a key can be hashed and verified."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"
        hashed = hash_api_key(plain_key)

        assert hashed != plain_key
        assert verify_api_key(plain_key, hashed) is True

    def test_verify_wrong_key_fails(self):
        """Test that wrong key fails verification."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"
        wrong_key = "cp_live_abcdef1234567890abcdef1234567890"
        hashed = hash_api_key(plain_key)

        assert verify_api_key(wrong_key, hashed) is False

    def test_hash_produces_different_hashes_for_same_key(self):
        """Test that bcrypt produces different hashes for same key (salt)."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"
        hash1 = hash_api_key(plain_key)
        hash2 = hash_api_key(plain_key)

        # Different hashes due to salt
        assert hash1 != hash2
        # But both verify correctly
        assert verify_api_key(plain_key, hash1) is True
        assert verify_api_key(plain_key, hash2) is True

    def test_verify_api_key_malformed_hash(self):
        """Test that malformed hash returns False (not exception)."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"
        # Invalid hash - not a valid bcrypt hash
        malformed_hash = "not_a_valid_hash"

        result = verify_api_key(plain_key, malformed_hash)

        assert result is False

    def test_verify_api_key_corrupted_hash(self):
        """Test that corrupted hash returns False."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"
        # Partially corrupted bcrypt hash
        corrupted_hash = "$2b$12$invalidhashdata"

        result = verify_api_key(plain_key, corrupted_hash)

        assert result is False

    def test_verify_api_key_empty_hash(self):
        """Test that empty hash returns False."""
        plain_key = "cp_live_1234567890abcdef1234567890abcdef"

        result = verify_api_key(plain_key, "")

        assert result is False

    def test_verify_api_key_unicode_handling(self):
        """Test that unicode in key is handled gracefully."""
        # Key with unicode characters
        unicode_key = "cp_live_测试1234567890abcdef"
        hashed = hash_api_key(unicode_key)

        assert verify_api_key(unicode_key, hashed) is True


class TestGetCurrentClient:
    """Tests for get_current_client dependency."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def mock_credentials(self):
        """Create mock credentials."""
        return HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="cp_live_test1234567890abcdef1234567890",
        )

    @pytest.mark.asyncio
    async def test_get_current_client_valid(self, mock_db, mock_credentials):
        """Test getting client with valid API key."""
        # Create a client with hashed key
        plain_key = mock_credentials.credentials
        hashed_key = hash_api_key(plain_key)

        mock_client = Mock(spec=ApiClient)
        mock_client.api_key = hashed_key
        mock_client.status = ApiClientStatus.ACTIVE
        mock_client.permissions = ["read"]
        mock_client.last_used_at = None

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_client]

        result = await get_current_client(mock_credentials, mock_db)

        assert result == mock_client
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_client_invalid_key(self, mock_db, mock_credentials):
        """Test that invalid API key raises 401."""
        # Create a client with different hashed key
        different_key = "cp_live_different1234567890abcdef1234567"
        hashed_key = hash_api_key(different_key)

        mock_client = Mock(spec=ApiClient)
        mock_client.api_key = hashed_key
        mock_client.status = ApiClientStatus.ACTIVE

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_client]

        with pytest.raises(HTTPException) as exc_info:
            await get_current_client(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_client_revoked(self, mock_db, mock_credentials):
        """Test that revoked client is not returned."""
        # Create a revoked client - should be filtered by query
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await get_current_client(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_client_suspended(self, mock_db, mock_credentials):
        """Test that suspended client is not returned."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            await get_current_client(mock_credentials, mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_client_updates_last_used_at(self, mock_db, mock_credentials):
        """Test that last_used_at is updated on successful auth."""
        plain_key = mock_credentials.credentials
        hashed_key = hash_api_key(plain_key)

        mock_client = Mock(spec=ApiClient)
        mock_client.api_key = hashed_key
        mock_client.status = ApiClientStatus.ACTIVE
        mock_client.last_used_at = None

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_client]

        await get_current_client(mock_credentials, mock_db)

        assert mock_client.last_used_at is not None
        mock_db.commit.assert_called_once()


class TestRequirePermissions:
    """Tests for require_permissions dependency."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        client = Mock(spec=ApiClient)
        client.permissions = ["read", "write"]
        return client

    @pytest.mark.asyncio
    async def test_require_permissions_has_permission(self, mock_client):
        """Test that client with required permission passes."""
        checker = require_permissions(["read"])

        # Patch get_current_client to return our mock
        with patch("cyberpulse.api.auth.get_current_client") as mock_get:
            mock_get.return_value = mock_client

            # Need to simulate Depends behavior
            result = await checker(client=mock_client)

            assert result == mock_client

    @pytest.mark.asyncio
    async def test_require_permissions_missing_permission(self, mock_client):
        """Test that client without required permission gets 403."""
        checker = require_permissions(["admin"])

        with pytest.raises(HTTPException) as exc_info:
            await checker(client=mock_client)

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_permissions_any_of_multiple(self, mock_client):
        """Test that having any of the required permissions is sufficient."""
        checker = require_permissions(["admin", "write"])

        result = await checker(client=mock_client)

        assert result == mock_client

    @pytest.mark.asyncio
    async def test_require_permissions_empty_permissions(self):
        """Test client with no permissions."""
        client = Mock(spec=ApiClient)
        client.permissions = []

        checker = require_permissions(["read"])

        with pytest.raises(HTTPException) as exc_info:
            await checker(client=client)

        assert exc_info.value.status_code == 403


class TestApiClientService:
    """Tests for ApiClientService."""

    @pytest.fixture
    def service(self, db_session):
        """Create an ApiClientService instance."""
        return ApiClientService(db_session)

    def test_create_client_returns_key_once(self, service, db_session):
        """Test that create_client returns both client and plain key."""
        client, plain_key = service.create_client(
            name="Test Client",
            permissions=["read"],
            description="Test description",
        )

        assert client.name == "Test Client"
        assert client.permissions == ["read"]
        assert client.description == "Test description"
        assert client.status == ApiClientStatus.ACTIVE
        assert client.client_id.startswith("cli_")

        # Plain key should be in correct format
        assert plain_key.startswith("cp_live_")
        assert len(plain_key) == 40  # "cp_live_" (8 chars) + 32 hex chars

        # The stored key should be hashed, not plain
        assert client.api_key != plain_key
        assert verify_api_key(plain_key, client.api_key) is True

    def test_create_client_default_permissions(self, service, db_session):
        """Test that permissions default to empty list."""
        client, plain_key = service.create_client(name="Test Client")

        assert client.permissions == []

    def test_validate_client_valid_key(self, service, db_session):
        """Test validating a correct API key."""
        client, plain_key = service.create_client(
            name="Test Client",
            permissions=["read"],
        )

        validated = service.validate_client(plain_key)

        assert validated is not None
        assert validated.client_id == client.client_id
        assert validated.last_used_at is not None

    def test_validate_client_invalid_key(self, service, db_session):
        """Test validating an incorrect API key."""
        service.create_client(name="Test Client")

        validated = service.validate_client("cp_live_invalid1234567890abcdef12345")

        assert validated is None

    def test_validate_client_revoked_client(self, service, db_session):
        """Test that revoked clients cannot authenticate."""
        client, plain_key = service.create_client(name="Test Client")
        service.revoke_client(client.client_id)

        validated = service.validate_client(plain_key)

        assert validated is None

    def test_revoke_client_success(self, service, db_session):
        """Test revoking a client."""
        client, _ = service.create_client(name="Test Client")

        result = service.revoke_client(client.client_id)

        assert result is True
        db_session.refresh(client)
        assert client.status == ApiClientStatus.REVOKED

    def test_revoke_client_not_found(self, service, db_session):
        """Test revoking a non-existent client."""
        result = service.revoke_client("cli_nonexistent")

        assert result is False

    def test_suspend_client_success(self, service, db_session):
        """Test suspending a client."""
        client, _ = service.create_client(name="Test Client")

        result = service.suspend_client(client.client_id)

        assert result is True
        db_session.refresh(client)
        assert client.status == ApiClientStatus.SUSPENDED

    def test_get_client_found(self, service, db_session):
        """Test getting an existing client."""
        created, _ = service.create_client(name="Test Client")

        found = service.get_client(created.client_id)

        assert found is not None
        assert found.client_id == created.client_id

    def test_get_client_not_found(self, service, db_session):
        """Test getting a non-existent client."""
        found = service.get_client("cli_nonexistent")

        assert found is None

    def test_list_clients_all(self, service, db_session):
        """Test listing all clients."""
        service.create_client(name="Client 1")
        service.create_client(name="Client 2")

        clients = service.list_clients()

        assert len(clients) == 2

    def test_list_clients_by_status(self, service, db_session):
        """Test listing clients filtered by status."""
        active, _ = service.create_client(name="Active Client")
        revoked, _ = service.create_client(name="Revoked Client")
        service.revoke_client(revoked.client_id)

        active_clients = service.list_clients(
            status_filter=ApiClientStatus.ACTIVE
        )
        revoked_clients = service.list_clients(
            status_filter=ApiClientStatus.REVOKED
        )

        assert len(active_clients) == 1
        assert active_clients[0].client_id == active.client_id

        assert len(revoked_clients) == 1
        assert revoked_clients[0].client_id == revoked.client_id

    def test_validate_client_updates_last_used_at(self, service, db_session):
        """Test that validate_client updates last_used_at on success."""
        client, plain_key = service.create_client(name="Test Client")

        # Ensure last_used_at is initially None
        db_session.refresh(client)
        assert client.last_used_at is None

        # Validate should update last_used_at
        validated = service.validate_client(plain_key)

        assert validated is not None
        assert validated.last_used_at is not None


class TestAuthIntegration:
    """Integration tests with FastAPI app."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_protected_endpoint_without_auth_returns_401(self, client):
        """Test that protected endpoints require authentication."""
        # Create a test endpoint
        from fastapi import FastAPI, Depends
        from cyberpulse.api.auth import get_current_client

        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected(client=Depends(get_current_client)):
            return {"client_id": client.client_id}

        test_client = TestClient(test_app)

        response = test_client.get("/protected")

        assert response.status_code == 401  # Missing auth header returns 401 Unauthorized

    def test_protected_endpoint_with_invalid_key_returns_401(self, db_session):
        """Test that invalid API key returns 401."""
        from fastapi import FastAPI, Depends
        from cyberpulse.api.auth import get_current_client

        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected(client=Depends(get_current_client)):
            return {"client_id": client.client_id}

        test_client = TestClient(test_app)

        response = test_client.get(
            "/protected",
            headers={"Authorization": "Bearer cp_live_invalid"}
        )

        assert response.status_code == 401

    def test_protected_endpoint_with_malformed_auth_header(self, db_session):
        """Test that malformed Authorization header returns 401."""
        from fastapi import FastAPI, Depends
        from cyberpulse.api.auth import get_current_client

        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected(client=Depends(get_current_client)):
            return {"client_id": client.client_id}

        test_client = TestClient(test_app)

        # Missing Bearer prefix
        response = test_client.get(
            "/protected",
            headers={"Authorization": "cp_live_test1234567890abcdef12345678"}
        )
        assert response.status_code == 401

        # Wrong scheme
        response = test_client.get(
            "/protected",
            headers={"Authorization": "Basic cp_live_test"}
        )
        assert response.status_code == 401

    def test_protected_endpoint_with_empty_auth_header(self, db_session):
        """Test that empty Authorization header returns 401."""
        from fastapi import FastAPI, Depends
        from cyberpulse.api.auth import get_current_client

        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected(client=Depends(get_current_client)):
            return {"client_id": client.client_id}

        test_client = TestClient(test_app)

        response = test_client.get(
            "/protected",
            headers={"Authorization": "Bearer "}
        )
        assert response.status_code == 401

        response = test_client.get(
            "/protected",
            headers={"Authorization": ""}
        )
        assert response.status_code == 401