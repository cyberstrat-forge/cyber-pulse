"""
Tests for Content API endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.api.routers.content import get_db as content_get_db
from cyberpulse.models import Content, ContentStatus, ApiClient, ApiClientStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_api_client():
    """Create a mock API client for authentication."""
    client = Mock(spec=ApiClient)
    client.client_id = "cli_test123"
    client.name = "Test Client"
    client.status = ApiClientStatus.ACTIVE
    client.permissions = ["read"]
    return client


@pytest.fixture
def auth_headers(mock_api_client):
    """Create authentication headers with a valid API key."""
    api_key = "cp_live_test1234567890abcdef1234567890"
    return {"Authorization": f"Bearer {api_key}"}


class TestListContent:
    """Tests for GET /api/v1/contents endpoint."""

    def test_list_content_empty(self, client, db_session, mock_api_client):
        """Test listing content when no content exists."""
        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["next_cursor"] is None
        assert data["has_more"] is False
        assert data["count"] == 0
        assert "server_timestamp" in data

    def test_list_content_with_items(self, client, db_session, mock_api_client):
        """Test listing content with multiple items."""
        # Create test contents
        contents = []
        for i in range(3):
            content = Content(
                content_id=f"cnt_20260319{i:06d}_abc{i}",
                canonical_hash=f"hash_{i}",
                normalized_title=f"Test Content {i}",
                normalized_body=f"Body content {i}",
                first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                source_count=1,
                status=ContentStatus.ACTIVE,
            )
            db_session.add(content)
            contents.append(content)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3
        assert data["count"] == 3
        # Items are ordered by content_id DESC (newest first)
        # Since we're ordering DESC, the last item in response should be the smallest
        assert data["next_cursor"] == "cnt_20260319000000_abc0"
        assert data["has_more"] is False

    def test_list_content_pagination(self, client, db_session, mock_api_client):
        """Test cursor-based pagination."""
        # Create more contents than the default limit
        for i in range(150):
            content = Content(
                content_id=f"cnt_20260319{i:06d}_abc{i}",
                canonical_hash=f"hash_{i}",
                normalized_title=f"Test Content {i}",
                normalized_body=f"Body content {i}",
                first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                source_count=1,
                status=ContentStatus.ACTIVE,
            )
            db_session.add(content)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # First page
            response = client.get("/api/v1/contents?limit=50")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 50
            assert data["count"] == 50
            assert data["has_more"] is True
            assert data["next_cursor"] is not None

            # Second page using cursor
            cursor = data["next_cursor"]
            response2 = client.get(f"/api/v1/contents?cursor={cursor}&limit=50")
            assert response2.status_code == 200
            data2 = response2.json()
            assert len(data2["data"]) == 50
            assert data2["has_more"] is True

            # Verify pages don't overlap
            first_page_ids = {item["content_id"] for item in data["data"]}
            second_page_ids = {item["content_id"] for item in data2["data"]}
            assert first_page_ids.isdisjoint(second_page_ids)
        finally:
            app.dependency_overrides.clear()

    def test_list_content_with_since_filter(self, client, db_session, mock_api_client):
        """Test filtering by since timestamp."""
        # Create contents with different timestamps
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_time = now - timedelta(days=7)
        new_time = now - timedelta(hours=1)

        # Old content
        old_content = Content(
            content_id="cnt_20260312000000_old1",
            canonical_hash="old_hash",
            normalized_title="Old Content",
            normalized_body="Old body",
            first_seen_at=old_time,
            last_seen_at=old_time,
            source_count=1,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(old_content)

        # New content
        new_content = Content(
            content_id="cnt_20260319000000_new1",
            canonical_hash="new_hash",
            normalized_title="New Content",
            normalized_body="New body",
            first_seen_at=new_time,
            last_seen_at=new_time,
            source_count=1,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(new_content)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # Filter for content from last 3 days
            # Use URL-encoded ISO datetime (the + in timezone needs encoding)
            since_dt = datetime.now(timezone.utc) - timedelta(days=3)
            since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # Use Z suffix for UTC
            response = client.get(f"/api/v1/contents?since={since_iso}")

            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["content_id"] == "cnt_20260319000000_new1"
        finally:
            app.dependency_overrides.clear()

    def test_list_content_limit_bounds(self, client, db_session, mock_api_client):
        """Test limit parameter boundaries."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # Minimum limit
            response = client.get("/api/v1/contents?limit=1")
            assert response.status_code == 200

            # Maximum limit
            response = client.get("/api/v1/contents?limit=1000")
            assert response.status_code == 200

            # Over maximum - should fail validation
            response = client.get("/api/v1/contents?limit=1001")
            assert response.status_code == 422

            # Under minimum - should fail validation
            response = client.get("/api/v1/contents?limit=0")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_list_content_requires_auth(self, client, db_session):
        """Test that authentication is required."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/contents")
            # Without valid auth header, should get 401
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestGetContent:
    """Tests for GET /api/v1/contents/{content_id} endpoint."""

    def test_get_content_found(self, client, db_session, mock_api_client):
        """Test getting a content by ID."""
        # Create test content
        content = Content(
            content_id="cnt_20260319143052_test1",
            canonical_hash="test_hash",
            normalized_title="Test Content",
            normalized_body="Test body content",
            first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            source_count=3,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(content)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents/cnt_20260319143052_test1")

            assert response.status_code == 200
            data = response.json()
            assert data["content_id"] == "cnt_20260319143052_test1"
            assert data["canonical_hash"] == "test_hash"
            assert data["normalized_title"] == "Test Content"
            assert data["normalized_body"] == "Test body content"
            assert data["source_count"] == 3
            assert data["status"] == "ACTIVE"
            assert "first_seen_at" in data
            assert "last_seen_at" in data
        finally:
            app.dependency_overrides.clear()

    def test_get_content_not_found(self, client, db_session, mock_api_client):
        """Test getting a non-existent content."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents/cnt_nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_get_content_requires_auth(self, client, db_session):
        """Test that authentication is required."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/contents/cnt_test123")
            # Without valid auth header, should get 401
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_get_content_all_fields(self, client, db_session, mock_api_client):
        """Test that all expected fields are returned."""
        # Create test content with specific values
        first_seen = datetime(2026, 3, 19, 14, 30, 52)
        last_seen = datetime(2026, 3, 19, 15, 45, 0)

        content = Content(
            content_id="cnt_20260319143052_full",
            canonical_hash="sha256_abcd1234",
            normalized_title="Full Test Content",
            normalized_body="Full test body with multiple lines.\nLine 2.\nLine 3.",
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            source_count=5,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(content)
        db_session.commit()

        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents/cnt_20260319143052_full")

            assert response.status_code == 200
            data = response.json()

            # Verify all expected fields are present
            assert data["content_id"] == "cnt_20260319143052_full"
            assert data["canonical_hash"] == "sha256_abcd1234"
            assert data["normalized_title"] == "Full Test Content"
            assert data["normalized_body"] == "Full test body with multiple lines.\nLine 2.\nLine 3."
            assert data["source_count"] == 5
            assert data["status"] == "ACTIVE"
            assert "first_seen_at" in data
            assert "last_seen_at" in data
        finally:
            app.dependency_overrides.clear()


class TestContentResponseFormat:
    """Tests for response format and structure."""

    def test_response_datetime_format(self, client, db_session, mock_api_client):
        """Test that datetime fields are properly serialized."""
        content = Content(
            content_id="cnt_20260319143052_datetime",
            canonical_hash="dt_hash",
            normalized_title="DateTime Test",
            normalized_body="Body",
            first_seen_at=datetime(2026, 3, 19, 14, 30, 52),
            last_seen_at=datetime(2026, 3, 19, 15, 45, 0),
            source_count=1,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(content)
        db_session.commit()

        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents/cnt_20260319143052_datetime")

            assert response.status_code == 200
            data = response.json()
            # Datetime should be ISO 8601 format
            assert "T" in data["first_seen_at"]
            assert "T" in data["last_seen_at"]
        finally:
            app.dependency_overrides.clear()

    def test_list_response_structure(self, client, db_session, mock_api_client):
        """Test the list response has all required fields."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents")

            assert response.status_code == 200
            data = response.json()

            # Check required top-level fields
            assert "data" in data
            assert "next_cursor" in data
            assert "has_more" in data
            assert "count" in data
            assert "server_timestamp" in data

            # Check types
            assert isinstance(data["data"], list)
            assert isinstance(data["has_more"], bool)
            assert isinstance(data["count"], int)
        finally:
            app.dependency_overrides.clear()

    def test_server_timestamp_includes_timezone(self, client, db_session, mock_api_client):
        """Test that server_timestamp includes timezone info."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents")

            assert response.status_code == 200
            data = response.json()

            # Should be ISO 8601 with timezone
            timestamp = data["server_timestamp"]
            assert "T" in timestamp
            # Should end with Z or have timezone offset
            assert timestamp.endswith("Z") or "+" in timestamp or "-" in timestamp[-6:]
        finally:
            app.dependency_overrides.clear()


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""

    def test_cursor_at_boundary(self, client, db_session, mock_api_client):
        """Test pagination with cursor at exact boundary.

        Note: With cursor-based pagination, we can't know for certain if there are
        more items without an additional query. So has_more=True when we get exactly
        limit items. The client discovers there are no more when the next page is empty.
        """
        # Create exactly 100 items (default limit)
        for i in range(100):
            content = Content(
                content_id=f"cnt_20260319{i:06d}_b{i}",
                canonical_hash=f"boundary_hash_{i}",
                normalized_title=f"Boundary Test {i}",
                normalized_body=f"Body {i}",
                first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
                source_count=1,
                status=ContentStatus.ACTIVE,
            )
            db_session.add(content)
        db_session.commit()

        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # Get first page
            response = client.get("/api/v1/contents")
            assert response.status_code == 200
            data = response.json()
            # When we get exactly limit items, has_more is True (conservative)
            assert data["has_more"] is True
            assert data["count"] == 100

            # Use cursor - should return empty (proving there were no more)
            cursor = data["next_cursor"]
            response2 = client.get(f"/api/v1/contents?cursor={cursor}")
            assert response2.status_code == 200
            data2 = response2.json()
            assert len(data2["data"]) == 0
            assert data2["has_more"] is False
        finally:
            app.dependency_overrides.clear()

    def test_invalid_cursor_returns_empty(self, client, db_session, mock_api_client):
        """Test that invalid cursor returns empty results (no error)."""
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # Use a cursor that doesn't match any content
            response = client.get("/api/v1/contents?cursor=cnt_20999999999999_xxx")
            assert response.status_code == 200
            data = response.json()
            # No content should match this cursor
            assert len(data["data"]) == 0
            assert data["has_more"] is False
        finally:
            app.dependency_overrides.clear()