"""Tests for Client Admin API."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from cyberpulse.api.auth import get_current_client
from cyberpulse.api.dependencies import get_db
from cyberpulse.api.main import app
from cyberpulse.models import ApiClient, ApiClientStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_admin_client():
    """Create a mock admin API client for authentication."""
    mock_client = Mock(spec=ApiClient)
    mock_client.client_id = "cli_admin"
    mock_client.name = "Admin Client"
    mock_client.status = ApiClientStatus.ACTIVE
    mock_client.permissions = ["admin", "read"]
    return mock_client


class TestClientDelete:
    """Tests for client hard delete endpoint."""

    def test_delete_client_no_auth(self, client):
        """Test that deleting a client requires authentication."""
        response = client.delete("/api/v1/admin/clients/cli_0000000000000001")
        assert response.status_code == 401

    def test_delete_client_not_found(self, client, db_session, mock_admin_client):
        """Test deleting non-existent client returns 404."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/clients/cli_0000000000000002")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_client_invalid_id_format(self, client, mock_admin_client):
        """Test deleting client with invalid ID format returns 400."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        try:
            response = client.delete("/api/v1/admin/clients/invalid_id")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_delete_client_database_exception(
            self, client, db_session, mock_admin_client
        ):
        """Test database exception during deletion returns generic error message."""
        from unittest.mock import patch

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        try:
            # Mock db.execute to raise database exception
            with patch.object(db_session, 'execute') as mock_execute:
                mock_execute.side_effect = OperationalError(
                    "Database connection failed", {}, None
                )

                response = client.delete("/api/v1/admin/clients/cli_0000000000000003")

            # Should return 500 with generic message (not expose db error details)
            assert response.status_code == 500
            detail = response.json()["detail"]
            assert "internal error" in detail.lower()
            # Ensure no database error details leaked
            assert "OperationalError" not in detail
            assert "connection" not in detail.lower()
        finally:
            app.dependency_overrides.clear()

    def test_delete_client_success(self, client, db_session, mock_admin_client):
        """Test successful hard delete of an API client."""
        # Create a client to delete
        from cyberpulse.api.auth import hash_api_key

        test_client_model = ApiClient(
            client_id="cli_0000000000000003",
            name="Client to Delete",
            api_key=hash_api_key("cp_live_test1234567890abcdef1234567890"),
            status=ApiClientStatus.ACTIVE,
            permissions=["read"],
            created_at=datetime.now(UTC),
        )
        db_session.add(test_client_model)
        db_session.commit()

        # Verify client exists before deletion
        assert db_session.get(ApiClient, "cli_0000000000000003") is not None

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/clients/cli_0000000000000003")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()

        # Verify client is permanently deleted (hard delete)
        assert db_session.get(ApiClient, "cli_0000000000000003") is None

    def test_delete_suspended_client_success(
            self, client, db_session, mock_admin_client
        ):
        """Test that suspended clients can also be hard deleted."""
        from cyberpulse.api.auth import hash_api_key

        suspended_client = ApiClient(
            client_id="cli_0000000000000004",
            name="Suspended Client to Delete",
            api_key=hash_api_key("cp_live_test1234567890abcdef1234567891"),
            status=ApiClientStatus.SUSPENDED,
            permissions=["read"],
            created_at=datetime.now(UTC),
        )
        db_session.add(suspended_client)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/clients/cli_0000000000000004")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert db_session.get(ApiClient, "cli_0000000000000004") is None

    def test_delete_client_without_admin_permission(self, client, db_session):
        """Test that deleting a client requires admin permission."""
        # Create a non-admin client
        non_admin_client = Mock(spec=ApiClient)
        non_admin_client.client_id = "cli_readonly"
        non_admin_client.permissions = ["read"]  # No admin permission

        from cyberpulse.api.auth import hash_api_key

        test_client_model = ApiClient(
            client_id="cli_0000000000000005",
            name="Client to Delete",
            api_key=hash_api_key("cp_live_test1234567890abcdef1234567892"),
            status=ApiClientStatus.ACTIVE,
            permissions=["read"],
            created_at=datetime.now(UTC),
        )
        db_session.add(test_client_model)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: non_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/clients/cli_0000000000000005")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 403
        # Client should still exist (not deleted)
        assert db_session.get(ApiClient, "cli_0000000000000005") is not None

    def test_delete_client_verify_physical_delete(
            self, client, db_session, mock_admin_client
        ):
        """Test that hard delete is physical (not soft delete with status change)."""
        from cyberpulse.api.auth import hash_api_key

        test_client_model = ApiClient(
            client_id="cli_0000000000000006",
            name="Client for Physical Delete Test",
            api_key=hash_api_key("cp_live_test1234567890abcdef1234567893"),
            status=ApiClientStatus.ACTIVE,
            permissions=["read"],
            created_at=datetime.now(UTC),
        )
        db_session.add(test_client_model)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/clients/cli_0000000000000006")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200

        # Query all clients - deleted client should not appear in any status
        all_clients = db_session.execute(select(ApiClient)).scalars().all()
        client_ids = [c.client_id for c in all_clients]
        assert "cli_0000000000000006" not in client_ids


class TestClientList:
    """Tests for client list endpoint."""

    def test_list_clients_no_auth(self, client):
        """Test that listing clients requires authentication."""
        response = client.get("/api/v1/admin/clients")
        assert response.status_code == 401

    def test_list_clients_with_admin(self, client, db_session, mock_admin_client):
        """Test listing clients with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/clients")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data
        assert "server_timestamp" in data
