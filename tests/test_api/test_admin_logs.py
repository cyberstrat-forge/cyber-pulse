"""Tests for Log Admin API."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.models import ApiClient, ApiClientStatus


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


class TestLogAdminAPI:
    """Tests for Log Admin API endpoints."""

    def test_list_logs_no_auth(self, client):
        """Test that logs endpoint requires authentication."""
        response = client.get("/api/v1/admin/logs")
        assert response.status_code == 401

    def test_list_logs_with_admin(self, client, db_session, mock_admin_client):
        """Test listing logs with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/logs?level=error&limit=10")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data
        assert "server_timestamp" in data

    def test_list_logs_by_source(self, client, db_session, mock_admin_client):
        """Test filtering logs by source."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/logs?source_id=src_test01")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_logs_invalid_level(self, client, db_session, mock_admin_client):
        """Test invalid log level."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/logs?level=invalid")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_list_logs_invalid_since(self, client, db_session, mock_admin_client):
        """Test invalid since format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/logs?since=invalid_time")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_list_logs_valid_time_ranges(self, client, db_session, mock_admin_client):
        """Test valid time range formats."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session

        try:
            for since in ["1h", "24h", "7d"]:
                response = client.get(f"/api/v1/admin/logs?since={since}")
                assert response.status_code == 200, f"Failed for since={since}"
        finally:
            app.dependency_overrides.clear()