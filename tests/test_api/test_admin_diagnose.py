"""Tests for Diagnose Admin API."""

import pytest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.models import ApiClient, ApiClientStatus
from cyberpulse import __version__


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_admin_client():
    """Create a mock admin API client for authentication."""
    client = Mock(spec=ApiClient)
    client.client_id = "cli_admin"
    client.name = "Admin Client"
    client.status = ApiClientStatus.ACTIVE
    client.permissions = ["admin", "read"]
    return client


class TestDiagnoseAdminAPI:
    """Tests for Diagnose Admin API endpoints."""

    def test_diagnose_no_auth(self, client):
        """Test that diagnose endpoint requires authentication."""
        response = client.get("/api/v1/admin/diagnose")
        assert response.status_code == 401

    def test_diagnose_with_admin(self, client, db_session, mock_admin_client):
        """Test diagnose with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/diagnose")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "statistics" in data

    def test_diagnose_response_structure(self, client, db_session, mock_admin_client):
        """Test diagnose response contains expected fields."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/diagnose")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        # Check components
        assert "database" in data["components"]
        assert "redis" in data["components"]
        assert "scheduler" in data["components"]
        # Check statistics structure
        assert "sources" in data["statistics"]
        assert "jobs" in data["statistics"]
        assert "items" in data["statistics"]
        assert "errors" in data["statistics"]

    def test_diagnose_status_values(self, client, db_session, mock_admin_client):
        """Test diagnose status can be healthy, degraded, or unhealthy."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/diagnose")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_diagnose_includes_version(self, client, db_session, mock_admin_client):
        """Test diagnose response includes version."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/diagnose")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["version"] == __version__

    def test_diagnose_statistics_structure(self, client, db_session, mock_admin_client):
        """Test statistics have expected nested structure."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/diagnose")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        stats = data["statistics"]

        # Check sources statistics
        assert "active" in stats["sources"]
        assert "frozen" in stats["sources"]

        # Check jobs statistics
        assert "pending" in stats["jobs"]
        assert "running" in stats["jobs"]
        assert "failed_24h" in stats["jobs"]

        # Check items statistics
        assert "total" in stats["items"]
        assert "last_24h" in stats["items"]

        # Check errors statistics
        assert "total_24h" in stats["errors"]
        assert "by_type" in stats["errors"]
        assert "top_sources" in stats["errors"]