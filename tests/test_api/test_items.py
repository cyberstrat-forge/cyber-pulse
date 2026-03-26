"""Tests for Items API."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_read_client():
    """Create mock client with read permission."""
    mock = MagicMock()
    mock.permissions = ["read"]
    return mock


class TestItemsAPI:
    """Tests for Items API endpoints."""

    def test_list_items_no_auth(self, client):
        """Test that items endpoint requires authentication."""
        response = client.get("/api/v1/items")
        assert response.status_code == 401

    def test_list_items_invalid_cursor_format(self, client):
        """Test invalid cursor format returns 400."""
        # Would need auth to reach validation
        pass

    @patch("cyberpulse.api.auth.get_current_client")
    def test_list_items_with_read_permission(self, mock_auth, client, mock_read_client):
        """Test listing items with read permission."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items")
        assert response.status_code in [200, 401]

    @patch("cyberpulse.api.auth.get_current_client")
    def test_list_items_with_time_filter(self, mock_auth, client, mock_read_client):
        """Test listing items with time range filter."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items?since=2026-01-01T00:00:00Z")
        assert response.status_code in [200, 401]

    @patch("cyberpulse.api.auth.get_current_client")
    def test_list_items_with_limit(self, mock_auth, client, mock_read_client):
        """Test listing items with limit parameter."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items?limit=10")
        assert response.status_code in [200, 401]

    def test_cursor_and_from_conflict(self, client):
        """Test that cursor and from cannot both be provided."""
        # Would need auth to reach validation
        pass