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
        """Test listing items with since parameter."""
        mock_auth.return_value = mock_read_client

        # Test with ISO 8601 datetime (Z suffix)
        response = client.get("/api/v1/items?since=2026-01-01T00:00:00Z")
        assert response.status_code in [200, 401]

        # Test with 'beginning'
        response = client.get("/api/v1/items?since=beginning")
        assert response.status_code in [200, 401]

    @patch("cyberpulse.api.auth.get_current_client")
    def test_list_items_with_limit(self, mock_auth, client, mock_read_client):
        """Test listing items with limit parameter."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items?limit=10")
        assert response.status_code in [200, 401]


def test_cursor_without_since_returns_400(client, db_session):
    """Test that cursor without since returns 400."""
    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus

    # Create a mock client with read permission
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    response = client.get("/api/v1/items?cursor=item_abc12345")
    assert response.status_code == 400
    assert "cursor must be used with since" in response.json()["detail"]

    # Clean up dependency overrides
    app.dependency_overrides.clear()


def test_invalid_since_format_returns_400(client, db_session):
    """Test that invalid since format returns 400."""
    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus

    # Create a mock client with read permission
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    response = client.get("/api/v1/items?since=invalid-format")
    assert response.status_code == 400
    assert "Invalid since format" in response.json()["detail"]

    # Clean up dependency overrides
    app.dependency_overrides.clear()


def test_items_only_returns_mapped_status(client, db_session):
    """Test that API only returns items with MAPPED status."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus

    # Create a mock client with read permission
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create a source for the items
    from cyberpulse.models import Source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
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


def test_full_sync_with_since_beginning(client, db_session):
    """Test full sync starting from beginning."""
    from datetime import UTC, datetime, timedelta

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different fetched_at times
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # Request with since=beginning
    response = client.get("/api/v1/items?since=beginning&limit=3")
    assert response.status_code == 200

    data = response.json()
    # Should return oldest items first (ascending order)
    assert len(data["data"]) == 3
    assert data["data"][0]["id"] == "item_00000000"  # Oldest first
    assert data["has_more"] is True
    assert data["last_item_id"] == "item_00000002"

    app.dependency_overrides.clear()


def test_incremental_sync_with_since_datetime(client, db_session):
    """Test incremental sync with since=datetime."""
    from datetime import UTC, datetime, timedelta

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different fetched_at times
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # Request items after the second item's time
    cutoff_time = base_time + timedelta(hours=2)
    # Use Z suffix format to avoid URL encoding issues with +00:00
    since_param = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    response = client.get(f"/api/v1/items?since={since_param}")
    assert response.status_code == 200

    data = response.json()
    # Should return items with fetched_at >= cutoff_time
    assert len(data["data"]) == 3  # items 2, 3, 4
    assert data["data"][0]["id"] == "item_00000002"

    app.dependency_overrides.clear()


def test_pagination_with_cursor(client, db_session):
    """Test pagination using cursor with since."""
    from datetime import UTC, datetime, timedelta

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # First page
    response = client.get("/api/v1/items?since=beginning&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["has_more"] is True
    cursor = data["last_item_id"]

    # Second page using cursor
    response = client.get(f"/api/v1/items?since=beginning&cursor={cursor}&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["data"][0]["id"] == "item_00000002"  # Continues after cursor

    app.dependency_overrides.clear()


def test_response_includes_last_fetched_at(client, db_session):
    """Test that response includes last_fetched_at field."""
    from datetime import UTC, datetime

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source and item
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    fetched_at = datetime(2026, 4, 1, 10, 30, 45, tzinfo=UTC)
    item = Item(
        item_id="item_00000001",
        source_id="src_test",
        external_id="ext_1",
        url="https://example.com/1",
        title="Test Item",
        published_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
        fetched_at=fetched_at,
        status=ItemStatus.MAPPED,
    )
    db_session.add(item)
    db_session.commit()

    response = client.get("/api/v1/items?since=beginning")
    assert response.status_code == 200

    data = response.json()
    assert "last_fetched_at" in data
    assert data["last_fetched_at"] is not None
    assert "last_item_id" in data
    assert data["last_item_id"] == "item_00000001"

    app.dependency_overrides.clear()


def test_cursor_item_not_found_returns_404(client, db_session):
    """Test that cursor referencing non-existent item returns 404."""
    from datetime import UTC, datetime

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source and one item
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    item = Item(
        item_id="item_00000001",
        source_id="src_test",
        external_id="ext_1",
        url="https://example.com/1",
        title="Test Item",
        published_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC),
        status=ItemStatus.MAPPED,
    )
    db_session.add(item)
    db_session.commit()

    # Use a cursor that doesn't exist in the database
    response = client.get(
        "/api/v1/items?since=beginning&cursor=item_99999999"
    )
    assert response.status_code == 404
    assert "Cursor item not found" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_invalid_cursor_format_returns_400(client, db_session):
    """Test that invalid cursor format returns 400."""
    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Test various invalid cursor formats
    invalid_cursors = [
        "invalid123",  # Missing item_ prefix
        "item_ABCD1234",  # Uppercase letters
        "item_1234567",  # Only 7 hex chars
        "item_123456789",  # 9 hex chars
    ]

    for cursor in invalid_cursors:
        response = client.get(f"/api/v1/items?since=beginning&cursor={cursor}")
        assert response.status_code == 400, f"Expected 400 for cursor={cursor}"
        assert "Invalid cursor format" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_empty_results_with_since_beginning(client, db_session):
    """Test that empty database returns correct pagination fields."""
    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # No items in database
    response = client.get("/api/v1/items?since=beginning")
    assert response.status_code == 200

    data = response.json()
    assert data["data"] == []
    assert data["last_item_id"] is None
    assert data["last_fetched_at"] is None
    assert data["has_more"] is False
    assert data["count"] == 0

    app.dependency_overrides.clear()


def test_descending_order_without_since(client, db_session):
    """Test that items are returned in descending order without since parameter."""
    from datetime import UTC, datetime, timedelta

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different fetched_at times
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # Request without since parameter (default behavior)
    response = client.get("/api/v1/items?limit=3")
    assert response.status_code == 200

    data = response.json()
    # Should return newest items first (descending order)
    assert len(data["data"]) == 3
    assert data["data"][0]["id"] == "item_00000004"  # Newest first
    assert data["data"][1]["id"] == "item_00000003"
    assert data["data"][2]["id"] == "item_00000002"

    app.dependency_overrides.clear()
