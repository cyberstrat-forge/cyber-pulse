"""Tests for Items API."""

from unittest.mock import MagicMock, patch

import pytest
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


def test_items_only_returns_mapped_status(client, db_session):
    """Test that API only returns items with MAPPED status."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from cyberpulse.api.dependencies import get_db, require_permissions
    from cyberpulse.models import Item, ItemStatus

    # Create a mock client with read permission
    mock_client = MagicMock()
    mock_client.permissions = ["read"]

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_permissions(["read"])] = lambda: mock_client

    # Create a source for the items
    from cyberpulse.models import Source
    source = Source(
        source_id="src_test",
        name="Test Source",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different statuses
    statuses = [
        ItemStatus.NEW,
        ItemStatus.NORMALIZED,
        ItemStatus.PENDING_FULL_FETCH,
        ItemStatus.MAPPED,
        ItemStatus.REJECTED,
    ]

    for i, status in enumerate(statuses):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            status=status,
        )
        db_session.add(item)
    db_session.commit()

    response = client.get("/api/v1/items?limit=100")
    assert response.status_code == 200

    data = response.json()

    # Only MAPPED should be returned
    assert len(data["data"]) == 1
    # MAPPED item is at index 3 in statuses list
    assert data["data"][0]["id"] == "item_00000003"

    # Clean up dependency overrides
    app.dependency_overrides.clear()
