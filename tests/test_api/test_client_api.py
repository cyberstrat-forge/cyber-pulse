"""
Tests for Client API endpoints.
"""

import pytest
from datetime import datetime

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import generate_api_key, hash_api_key
from cyberpulse.models import ApiClient, ApiClientStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def admin_client(db_session):
    """Create an admin API client for authentication."""
    plain_key = generate_api_key()
    hashed_key = hash_api_key(plain_key)
    admin = ApiClient(
        client_id="cli_admin_test",
        name="Admin Test Client",
        api_key=hashed_key,
        status=ApiClientStatus.ACTIVE,
        permissions=["admin"],
    )
    db_session.add(admin)
    db_session.commit()
    return plain_key


class TestCreateClient:
    """Tests for POST /api/v1/clients endpoint."""

    def test_create_client_success(self, client, db_session, admin_client):
        """Test creating a client successfully."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "Test Client",
                    "permissions": ["read", "write"],
                    "description": "Test client for API"
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()

            # Check response structure
            assert "client" in data
            assert "api_key" in data
            assert "warning" in data

            # Check client data
            client_data = data["client"]
            assert client_data["name"] == "Test Client"
            assert client_data["status"] == "ACTIVE"
            assert set(client_data["permissions"]) == {"read", "write"}
            assert client_data["description"] == "Test client for API"
            assert "client_id" in client_data
            assert client_data["client_id"].startswith("cli_")

            # Check API key format
            assert data["api_key"].startswith("cp_live_")
            assert len(data["api_key"]) > 10  # Reasonable length

            # Check warning message
            assert "only be shown once" in data["warning"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_client_minimal(self, client, db_session, admin_client):
        """Test creating a client with minimal required fields."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "Minimal Client"
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()

            assert data["client"]["name"] == "Minimal Client"
            assert data["client"]["permissions"] == []
            assert data["client"]["description"] is None
        finally:
            app.dependency_overrides.clear()

    def test_create_client_empty_name(self, client, db_session, admin_client):
        """Test creating a client with empty name."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": ""
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_create_client_missing_name(self, client, db_session, admin_client):
        """Test creating a client without name."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={},
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_create_client_stores_hashed_key(self, client, db_session, admin_client):
        """Test that the API key is stored hashed, not plain."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={"name": "Hash Test Client"},
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()
            plain_key = data["api_key"]
            client_id = data["client"]["client_id"]

            # Verify the stored key is hashed (not the plain key)
            stored_client = db_session.query(ApiClient).filter(
                ApiClient.client_id == client_id
            ).first()

            assert stored_client is not None
            assert stored_client.api_key != plain_key
            # bcrypt hashes start with $2b$
            assert stored_client.api_key.startswith("$2b$")
        finally:
            app.dependency_overrides.clear()

    def test_create_client_requires_admin(self, client, db_session):
        """Test that creating a client requires admin permission."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Create a non-admin client
            plain_key = generate_api_key()
            hashed_key = hash_api_key(plain_key)
            non_admin = ApiClient(
                client_id="cli_nonadmin_test",
                name="Non-Admin Test Client",
                api_key=hashed_key,
                status=ApiClientStatus.ACTIVE,
                permissions=["read"],
            )
            db_session.add(non_admin)
            db_session.commit()

            response = client.post(
                "/api/v1/clients",
                json={"name": "Should Fail"},
                headers={"Authorization": f"Bearer {plain_key}"}
            )

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_create_client_no_auth(self, client, db_session):
        """Test that creating a client without auth fails."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={"name": "Should Fail"}
            )

            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestListClients:
    """Tests for GET /api/v1/clients endpoint."""

    def test_list_clients_empty(self, client, db_session, admin_client):
        """Test listing clients when no clients exist (except admin)."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 200
            data = response.json()
            # Should only contain the admin client created by the fixture
            assert data["count"] == 1
            assert data["data"][0]["client_id"] == "cli_admin_test"
            assert "server_timestamp" in data
        finally:
            app.dependency_overrides.clear()

    def test_list_clients_with_items(self, client, db_session, admin_client):
        """Test listing clients with multiple items."""
        # Create test clients
        for i in range(3):
            client_obj = ApiClient(
                client_id=f"cli_test{i:04d}",
                name=f"Test Client {i}",
                api_key=f"hashed_key_{i}",
                status=ApiClientStatus.ACTIVE,
                permissions=["read"],
            )
            db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 200
            data = response.json()
            # Will include the admin client plus the 3 test clients
            assert data["count"] >= 3

            # Verify no API keys are returned
            for client_data in data["data"]:
                assert "api_key" not in client_data or client_data.get("api_key") is None
        finally:
            app.dependency_overrides.clear()

    def test_list_clients_filter_by_status(self, client, db_session, admin_client):
        """Test filtering by status."""
        # Create clients with different statuses
        active_client = ApiClient(
            client_id="cli_status_active",
            name="Active Client",
            api_key="hashed_active",
            status=ApiClientStatus.ACTIVE,
            permissions=[],
        )
        revoked_client = ApiClient(
            client_id="cli_status_revoked",
            name="Revoked Client",
            api_key="hashed_revoked",
            status=ApiClientStatus.REVOKED,
            permissions=[],
        )
        suspended_client = ApiClient(
            client_id="cli_status_suspended",
            name="Suspended Client",
            api_key="hashed_suspended",
            status=ApiClientStatus.SUSPENDED,
            permissions=[],
        )
        db_session.add_all([active_client, revoked_client, suspended_client])
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Filter by active
            response = client.get(
                "/api/v1/clients?status=active",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 200
            data = response.json()
            # Will include admin client as well
            assert all(c["status"] == "ACTIVE" for c in data["data"])

            # Filter by revoked
            response = client.get(
                "/api/v1/clients?status=revoked",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["status"] == "REVOKED"

            # Filter by suspended
            response = client.get(
                "/api/v1/clients?status=suspended",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["status"] == "SUSPENDED"
        finally:
            app.dependency_overrides.clear()

    def test_list_clients_invalid_status(self, client, db_session, admin_client):
        """Test with invalid status parameter."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get(
                "/api/v1/clients?status=invalid",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 422
            assert "invalid status" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_list_clients_response_structure(self, client, db_session, admin_client):
        """Test the list response has all required fields."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 200
            data = response.json()

            # Check required top-level fields
            assert "data" in data
            assert "count" in data
            assert "server_timestamp" in data

            # Check types
            assert isinstance(data["data"], list)
            assert isinstance(data["count"], int)
        finally:
            app.dependency_overrides.clear()

    def test_list_clients_requires_admin(self, client, db_session):
        """Test that listing clients requires admin permission."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Create a non-admin client
            plain_key = generate_api_key()
            hashed_key = hash_api_key(plain_key)
            non_admin = ApiClient(
                client_id="cli_nonadmin_list",
                name="Non-Admin Test Client",
                api_key=hashed_key,
                status=ApiClientStatus.ACTIVE,
                permissions=["read"],
            )
            db_session.add(non_admin)
            db_session.commit()

            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {plain_key}"}
            )

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestDeleteClient:
    """Tests for DELETE /api/v1/clients/{client_id} endpoint."""

    def test_delete_client_success(self, client, db_session, admin_client):
        """Test revoking a client."""
        # Create a client to delete (valid client_id format: cli_ + 16 hex chars)
        client_obj = ApiClient(
            client_id="cli_aaaa1111bbbb2222",
            name="Client to Delete",
            api_key="hashed_delete",
            status=ApiClientStatus.ACTIVE,
            permissions=["read"],
        )
        db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete(
                "/api/v1/clients/cli_aaaa1111bbbb2222",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 204

            # Verify client is revoked
            db_session.refresh(client_obj)
            assert client_obj.status == ApiClientStatus.REVOKED
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_not_found(self, client, db_session, admin_client):
        """Test deleting a non-existent client."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete(
                "/api/v1/clients/cli_ffff0000eeee1111",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_already_revoked(self, client, db_session, admin_client):
        """Test revoking an already revoked client - should succeed."""
        # Create a revoked client
        client_obj = ApiClient(
            client_id="cli_cccc3333dddd4444",
            name="Already Revoked Client",
            api_key="hashed_revoked",
            status=ApiClientStatus.REVOKED,
            permissions=[],
        )
        db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete(
                "/api/v1/clients/cli_cccc3333dddd4444",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            # Should succeed (idempotent)
            assert response.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_idempotent(self, client, db_session, admin_client):
        """Test that deleting twice works (idempotent)."""
        client_obj = ApiClient(
            client_id="cli_5555aaaa6666bbbb",
            name="Idempotent Test",
            api_key="hashed_idempotent",
            status=ApiClientStatus.ACTIVE,
            permissions=[],
        )
        db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # First delete
            response = client.delete(
                "/api/v1/clients/cli_5555aaaa6666bbbb",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 204

            # Second delete (idempotent)
            response = client.delete(
                "/api/v1/clients/cli_5555aaaa6666bbbb",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_invalid_format(self, client, db_session, admin_client):
        """Test deleting a client with invalid client_id format."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Invalid client_id format (missing cli_ prefix)
            response = client.delete(
                "/api/v1/clients/invalid_id",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 400
            assert "invalid client_id format" in response.json()["detail"].lower()

            # Invalid client_id format (wrong hex length)
            response = client.delete(
                "/api/v1/clients/cli_short",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 400

            # Invalid client_id format (non-hex characters)
            response = client.delete(
                "/api/v1/clients/cli_ghijklmnopqrstuvwxyz",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_requires_admin(self, client, db_session):
        """Test that deleting a client requires admin permission."""
        # Create a non-admin client
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)
        non_admin = ApiClient(
            client_id="cli_nonadmin_del",
            name="Non-Admin Test Client",
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=["read"],
        )
        db_session.add(non_admin)

        # Create a client to delete
        client_obj = ApiClient(
            client_id="cli_to_delete_non",
            name="Client to Delete",
            api_key="hashed_del",
            status=ApiClientStatus.ACTIVE,
            permissions=[],
        )
        db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete(
                "/api/v1/clients/cli_to_delete_non",
                headers={"Authorization": f"Bearer {plain_key}"}
            )

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestClientResponseFormat:
    """Tests for response format and structure."""

    def test_client_response_no_api_key(self, client, db_session, admin_client):
        """Test that API key is never returned in client response."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Create a client
            response = client.post(
                "/api/v1/clients",
                json={"name": "No Key Test"},
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            assert response.status_code == 201

            # List clients
            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {admin_client}"}
            )
            data = response.json()

            # Verify no api_key in response
            for client_data in data["data"]:
                assert "api_key" not in client_data
        finally:
            app.dependency_overrides.clear()

    def test_created_response_has_warning(self, client, db_session, admin_client):
        """Test that create response includes warning about API key."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={"name": "Warning Test"},
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()

            # Warning should be present
            assert "warning" in data
            assert len(data["warning"]) > 0
            # Warning should mention one-time visibility
            assert "once" in data["warning"].lower() or "one" in data["warning"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_response_datetime_format(self, client, db_session, admin_client):
        """Test that datetime fields are properly serialized."""
        client_obj = ApiClient(
            client_id="cli_datetime",
            name="DateTime Test",
            api_key="hashed_datetime",
            status=ApiClientStatus.ACTIVE,
            permissions=[],
            last_used_at=datetime(2026, 3, 19, 10, 30, 0),
        )
        db_session.add(client_obj)
        db_session.commit()

        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get(
                "/api/v1/clients",
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 200
            data = response.json()

            # Find our client
            client_data = next(
                (c for c in data["data"] if c["client_id"] == "cli_datetime"),
                None
            )
            assert client_data is not None

            # Datetime should be ISO 8601 format
            if client_data.get("last_used_at"):
                assert "T" in client_data["last_used_at"]
        finally:
            app.dependency_overrides.clear()

    def test_client_all_fields_present(self, client, db_session, admin_client):
        """Test that all expected fields are returned."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "All Fields Test",
                    "permissions": ["read", "write", "admin"],
                    "description": "Testing all fields"
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()
            client_data = data["client"]

            # Verify all expected fields are present
            assert "client_id" in client_data
            assert "name" in client_data
            assert "status" in client_data
            assert "permissions" in client_data
            assert "description" in client_data
            assert "last_used_at" in client_data
            assert "created_at" in client_data
            assert "updated_at" in client_data

            # Verify values
            assert client_data["name"] == "All Fields Test"
            assert set(client_data["permissions"]) == {"read", "write", "admin"}
            assert client_data["description"] == "Testing all fields"
            assert client_data["status"] == "ACTIVE"
        finally:
            app.dependency_overrides.clear()


class TestClientPermissions:
    """Tests for client permission handling."""

    def test_create_client_with_permissions(self, client, db_session, admin_client):
        """Test creating a client with various permissions."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "Permissioned Client",
                    "permissions": ["read", "write", "admin", "delete"]
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()
            assert set(data["client"]["permissions"]) == {"read", "write", "admin", "delete"}
        finally:
            app.dependency_overrides.clear()

    def test_create_client_empty_permissions(self, client, db_session, admin_client):
        """Test creating a client with empty permissions list."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "No Permissions Client",
                    "permissions": []
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()
            assert data["client"]["permissions"] == []
        finally:
            app.dependency_overrides.clear()

    def test_create_client_default_permissions(self, client, db_session, admin_client):
        """Test that permissions default to empty list."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/clients",
                json={
                    "name": "Default Permissions Client"
                },
                headers={"Authorization": f"Bearer {admin_client}"}
            )

            assert response.status_code == 201
            data = response.json()
            assert data["client"]["permissions"] == []
        finally:
            app.dependency_overrides.clear()