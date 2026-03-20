"""
Tests for Source API endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.models import Source, SourceTier, SourceStatus, ApiClient, ApiClientStatus


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
    client.permissions = ["read", "write"]
    return client


class TestListSources:
    """Tests for GET /api/v1/sources endpoint."""

    def test_list_sources_empty(self, client, db_session, mock_api_client):
        """Test listing sources when no sources exist."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["count"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 100
        assert "server_timestamp" in data

    def test_list_sources_with_items(self, client, db_session, mock_api_client):
        """Test listing sources with multiple items."""
        # Create test sources
        for i in range(3):
            source = Source(
                source_id=f"src_test{i:04d}",
                name=f"Test Source {i}",
                connector_type="rss",
                tier=SourceTier.T2,
                score=50.0,
                status=SourceStatus.ACTIVE,
                is_in_observation=True,
                config={"url": f"https://example.com/feed{i}.xml"},
            )
            db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3
        assert data["count"] == 3

    def test_list_sources_filter_by_tier(self, client, db_session, mock_api_client):
        """Test filtering by tier."""
        # Create sources with different tiers
        source_t0 = Source(
            source_id="src_tier_t0",
            name="T0 Source",
            connector_type="rss",
            tier=SourceTier.T0,
            score=90.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        source_t2 = Source(
            source_id="src_tier_t2",
            name="T2 Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add_all([source_t0, source_t2])
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Filter by T0
            response = client.get("/api/v1/sources?tier=T0")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["tier"] == "T0"

            # Filter by T2
            response = client.get("/api/v1/sources?tier=T2")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["tier"] == "T2"
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_filter_by_status(self, client, db_session, mock_api_client):
        """Test filtering by status."""
        # Create sources with different statuses
        source_active = Source(
            source_id="src_status_active",
            name="Active Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        source_frozen = Source(
            source_id="src_status_frozen",
            name="Frozen Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.FROZEN,
            is_in_observation=False,
            config={},
        )
        db_session.add_all([source_active, source_frozen])
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Filter by active
            response = client.get("/api/v1/sources?status=active")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["status"] == "ACTIVE"

            # Filter by frozen
            response = client.get("/api/v1/sources?status=frozen")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 1
            assert data["data"][0]["status"] == "FROZEN"
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_pagination(self, client, db_session, mock_api_client):
        """Test offset-based pagination."""
        # Create more sources than default limit
        for i in range(150):
            source = Source(
                source_id=f"src_page{i:04d}",
                name=f"Pagination Source {i}",
                connector_type="rss",
                tier=SourceTier.T2,
                score=50.0,
                status=SourceStatus.ACTIVE,
                is_in_observation=False,
                config={},
            )
            db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # First page
            response = client.get("/api/v1/sources?limit=50&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 50
            assert data["offset"] == 0
            assert data["limit"] == 50

            # Second page
            response = client.get("/api/v1/sources?limit=50&offset=50")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 50
            assert data["offset"] == 50

            # Verify pages don't overlap
            first_response = client.get("/api/v1/sources?limit=50&offset=0")
            second_response = client.get("/api/v1/sources?limit=50&offset=50")
            first_ids = {s["source_id"] for s in first_response.json()["data"]}
            second_ids = {s["source_id"] for s in second_response.json()["data"]}
            assert first_ids.isdisjoint(second_ids)
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_invalid_tier(self, client, db_session, mock_api_client):
        """Test with invalid tier parameter."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources?tier=INVALID")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_invalid_status(self, client, db_session, mock_api_client):
        """Test with invalid status parameter."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources?status=invalid")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_limit_bounds(self, client, db_session, mock_api_client):
        """Test limit parameter boundaries."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Minimum limit
            response = client.get("/api/v1/sources?limit=1")
            assert response.status_code == 200

            # Maximum limit
            response = client.get("/api/v1/sources?limit=500")
            assert response.status_code == 200

            # Over maximum
            response = client.get("/api/v1/sources?limit=501")
            assert response.status_code == 422

            # Under minimum
            response = client.get("/api/v1/sources?limit=0")
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_list_sources_requires_auth(self, client, db_session):
        """Test that authentication is required."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestCreateSource:
    """Tests for POST /api/v1/sources endpoint."""

    def test_create_source_success(self, client, db_session, mock_api_client):
        """Test creating a source successfully."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "New Source",
                    "connector_type": "rss",
                    "tier": "T1",
                    "score": 70.0,
                    "config": {"url": "https://example.com/feed.xml"},
                    "fetch_interval": 3600
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "New Source"
            assert data["connector_type"] == "rss"
            assert data["tier"] == "T1"
            assert data["score"] == 70.0
            assert data["status"] == "ACTIVE"
            assert data["is_in_observation"] is True
            assert "source_id" in data
            assert "observation_until" in data
        finally:
            app.dependency_overrides.clear()

    def test_create_source_with_score_only(self, client, db_session, mock_api_client):
        """Test creating source with score only - tier should be derived."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Score Only Source",
                    "connector_type": "rss",
                    "score": 85.0
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["tier"] == "T0"  # score >= 80 -> T0
            assert data["score"] == 85.0
        finally:
            app.dependency_overrides.clear()

    def test_create_source_with_tier_only(self, client, db_session, mock_api_client):
        """Test creating source with tier only - score should be derived."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Tier Only Source",
                    "connector_type": "rss",
                    "tier": "T0"
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["tier"] == "T0"
            assert data["score"] == 90.0  # T0 default score
        finally:
            app.dependency_overrides.clear()

    def test_create_source_defaults(self, client, db_session, mock_api_client):
        """Test creating source with defaults (no tier or score)."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Default Source",
                    "connector_type": "rss"
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["tier"] == "T2"  # Default tier
            assert data["score"] == 50.0  # T2 default score
        finally:
            app.dependency_overrides.clear()

    def test_create_source_duplicate_name(self, client, db_session, mock_api_client):
        """Test creating source with duplicate name."""
        # Create initial source
        source = Source(
            source_id="src_dup001",
            name="Duplicate Name",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Duplicate Name",
                    "connector_type": "rss"
                }
            )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_create_source_invalid_tier(self, client, db_session, mock_api_client):
        """Test creating source with invalid tier."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Invalid Tier Source",
                    "connector_type": "rss",
                    "tier": "T5"
                }
            )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_create_source_invalid_score(self, client, db_session, mock_api_client):
        """Test creating source with invalid score."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": "Invalid Score Source",
                    "connector_type": "rss",
                    "score": 150.0
                }
            )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_create_source_missing_required_fields(self, client, db_session, mock_api_client):
        """Test creating source without required fields."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/sources",
                json={}
            )

            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestGetSource:
    """Tests for GET /api/v1/sources/{source_id} endpoint."""

    def test_get_source_found(self, client, db_session, mock_api_client):
        """Test getting a source by ID."""
        source = Source(
            source_id="src_get001",
            name="Get Test Source",
            connector_type="rss",
            tier=SourceTier.T1,
            score=70.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={"url": "https://example.com/feed.xml"},
            total_items=100,
            total_contents=80,
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources/src_get001")

            assert response.status_code == 200
            data = response.json()
            assert data["source_id"] == "src_get001"
            assert data["name"] == "Get Test Source"
            assert data["tier"] == "T1"
            assert data["score"] == 70.0
            assert data["total_items"] == 100
            assert data["total_contents"] == 80
        finally:
            app.dependency_overrides.clear()

    def test_get_source_not_found(self, client, db_session, mock_api_client):
        """Test getting a non-existent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources/src_nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_get_source_requires_auth(self, client, db_session):
        """Test that authentication is required."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources/src_test123")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestUpdateSource:
    """Tests for PATCH /api/v1/sources/{source_id} endpoint."""

    def test_update_source_tier(self, client, db_session, mock_api_client):
        """Test updating source tier."""
        source = Source(
            source_id="src_upd001",
            name="Update Tier Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd001",
                json={"tier": "T0"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["tier"] == "T0"
            assert data["score"] == 90.0  # Auto-adjusted to T0 default
        finally:
            app.dependency_overrides.clear()

    def test_update_source_score(self, client, db_session, mock_api_client):
        """Test updating source score - tier should auto-adjust."""
        source = Source(
            source_id="src_upd002",
            name="Update Score Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd002",
                json={"score": 85.0}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["score"] == 85.0
            assert data["tier"] == "T0"  # Auto-adjusted from score
        finally:
            app.dependency_overrides.clear()

    def test_update_source_status(self, client, db_session, mock_api_client):
        """Test updating source status."""
        source = Source(
            source_id="src_upd003",
            name="Update Status Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd003",
                json={"status": "FROZEN"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "FROZEN"
        finally:
            app.dependency_overrides.clear()

    def test_update_source_config(self, client, db_session, mock_api_client):
        """Test updating source config."""
        source = Source(
            source_id="src_upd004",
            name="Update Config Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={"old": "value"},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd004",
                json={"config": {"new": "config", "url": "https://new.example.com/feed.xml"}}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["config"]["new"] == "config"
            assert data["config"]["url"] == "https://new.example.com/feed.xml"
        finally:
            app.dependency_overrides.clear()

    def test_update_source_not_found(self, client, db_session, mock_api_client):
        """Test updating a non-existent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_nonexistent",
                json={"score": 80.0}
            )

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_update_removed_source(self, client, db_session, mock_api_client):
        """Test updating a removed source - should fail."""
        source = Source(
            source_id="src_upd_removed",
            name="Removed Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.REMOVED,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd_removed",
                json={"score": 80.0}
            )

            assert response.status_code == 400
            assert "removed" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_update_source_empty_body(self, client, db_session, mock_api_client):
        """Test updating source with no fields."""
        source = Source(
            source_id="src_upd_empty",
            name="Empty Update Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd_empty",
                json={}
            )

            assert response.status_code == 400
            assert "no fields" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_update_source_multiple_fields(self, client, db_session, mock_api_client):
        """Test updating multiple fields at once."""
        source = Source(
            source_id="src_upd_multi",
            name="Multi Update Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=True,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/sources/src_upd_multi",
                json={
                    "fetch_interval": 1800,
                    "pending_review": True,
                    "review_reason": "Quality check needed"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["fetch_interval"] == 1800
            assert data["pending_review"] is True
            assert data["review_reason"] == "Quality check needed"
        finally:
            app.dependency_overrides.clear()


class TestDeleteSource:
    """Tests for DELETE /api/v1/sources/{source_id} endpoint."""

    def test_delete_source_success(self, client, db_session, mock_api_client):
        """Test soft deleting a source."""
        source = Source(
            source_id="src_del001",
            name="Delete Test Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/sources/src_del001")

            assert response.status_code == 204

            # Verify source is soft deleted (status = removed)
            db_session.refresh(source)
            assert source.status == SourceStatus.REMOVED
        finally:
            app.dependency_overrides.clear()

    def test_delete_source_not_found(self, client, db_session, mock_api_client):
        """Test deleting a non-existent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/sources/src_nonexistent")

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_delete_source_already_removed(self, client, db_session, mock_api_client):
        """Test deleting an already removed source - should succeed."""
        source = Source(
            source_id="src_del_already",
            name="Already Removed Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.REMOVED,
            is_in_observation=False,
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/sources/src_del_already")

            # Should succeed (idempotent)
            assert response.status_code == 204
        finally:
            app.dependency_overrides.clear()

    def test_delete_source_requires_auth(self, client, db_session):
        """Test that authentication is required."""
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/sources/src_test123")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()


class TestSourceResponseFormat:
    """Tests for response format and structure."""

    def test_response_datetime_format(self, client, db_session, mock_api_client):
        """Test that datetime fields are properly serialized."""
        source = Source(
            source_id="src_dt_format",
            name="DateTime Format Source",
            connector_type="rss",
            tier=SourceTier.T2,
            score=50.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=True,
            observation_until=datetime(2026, 4, 19, 0, 0, 0),
            config={},
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources/src_dt_format")

            assert response.status_code == 200
            data = response.json()
            # Datetime should be ISO 8601 format
            if data.get("observation_until"):
                assert "T" in data["observation_until"]
        finally:
            app.dependency_overrides.clear()

    def test_list_response_structure(self, client, db_session, mock_api_client):
        """Test the list response has all required fields."""
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources")

            assert response.status_code == 200
            data = response.json()

            # Check required top-level fields
            assert "data" in data
            assert "count" in data
            assert "offset" in data
            assert "limit" in data
            assert "server_timestamp" in data

            # Check types
            assert isinstance(data["data"], list)
            assert isinstance(data["count"], int)
            assert isinstance(data["offset"], int)
            assert isinstance(data["limit"], int)
        finally:
            app.dependency_overrides.clear()

    def test_source_response_all_fields(self, client, db_session, mock_api_client):
        """Test that all expected fields are returned."""
        source = Source(
            source_id="src_all_fields",
            name="All Fields Source",
            connector_type="api",
            tier=SourceTier.T1,
            score=70.0,
            status=SourceStatus.ACTIVE,
            is_in_observation=True,
            observation_until=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
            pending_review=False,
            review_reason=None,
            fetch_interval=1800,
            config={"url": "https://api.example.com"},
            total_items=50,
            total_contents=40,
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        from cyberpulse.api.dependencies import get_db
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/sources/src_all_fields")

            assert response.status_code == 200
            data = response.json()

            # Verify all expected fields are present
            assert data["source_id"] == "src_all_fields"
            assert data["name"] == "All Fields Source"
            assert data["connector_type"] == "api"
            assert data["tier"] == "T1"
            assert data["score"] == 70.0
            assert data["status"] == "ACTIVE"
            assert data["is_in_observation"] is True
            assert data["observation_until"] is not None
            assert data["pending_review"] is False
            assert data["fetch_interval"] == 1800
            assert data["config"]["url"] == "https://api.example.com"
            assert data["total_items"] == 50
            assert data["total_contents"] == 40
        finally:
            app.dependency_overrides.clear()