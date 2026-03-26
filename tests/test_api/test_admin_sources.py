"""Tests for Source Admin API."""

import io
import pytest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.api.dependencies import get_db
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


class TestSourceList:
    """Tests for source list endpoint."""

    def test_list_sources_no_auth(self, client):
        """Test that listing sources requires authentication."""
        response = client.get("/api/v1/admin/sources")
        assert response.status_code == 401

    def test_list_sources_with_admin(self, client, db_session, mock_admin_client):
        """Test listing sources with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data
        assert "server_timestamp" in data

    def test_list_sources_filter_by_status(self, client, db_session, mock_admin_client):
        """Test filtering sources by status."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources?status=ACTIVE")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_sources_filter_by_tier(self, client, db_session, mock_admin_client):
        """Test filtering sources by tier."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources?tier=T1")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_sources_filter_by_scheduled(self, client, db_session, mock_admin_client):
        """Test filtering sources by scheduled status."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources?scheduled=true")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_sources_invalid_status(self, client, db_session, mock_admin_client):
        """Test invalid status filter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources?status=INVALID")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_list_sources_invalid_tier(self, client, db_session, mock_admin_client):
        """Test invalid tier filter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources?tier=T99")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestSourceCreate:
    """Tests for source create endpoint."""

    def test_create_source_no_auth(self, client):
        """Test that creating sources requires authentication."""
        response = client.post(
            "/api/v1/admin/sources",
            json={
                "name": "Test Source",
                "connector_type": "rss",
            }
        )
        assert response.status_code == 401

    def test_create_source_with_admin(self, client, db_session, mock_admin_client):
        """Test creating source with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources",
                json={
                    "name": "Test Source Create",
                    "connector_type": "rss",
                    "tier": "T1",
                    "config": {"feed_url": "https://example.com/feed.xml"}
                }
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Source Create"
        assert data["connector_type"] == "rss"
        assert data["tier"] == "T1"
        assert data["status"] == "ACTIVE"
        assert data["source_id"].startswith("src_")

    def test_create_source_with_tier_derived_score(self, client, db_session, mock_admin_client):
        """Test that score is derived from tier when not provided."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # T0 should get score 90
            response = client.post(
                "/api/v1/admin/sources",
                json={
                    "name": "T0 Source",
                    "connector_type": "rss",
                    "tier": "T0"
                }
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["tier"] == "T0"
        assert data["score"] == 90.0

    def test_create_source_with_t3_tier_score(self, client, db_session, mock_admin_client):
        """Test that T3 tier gets score < 40 (within T3 range)."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources",
                json={
                    "name": "T3 Source",
                    "connector_type": "rss",
                    "tier": "T3"
                }
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["tier"] == "T3"
        # T3 score should be < 40 (we use 20 as default)
        assert data["score"] < 40.0
        assert data["score"] == 20.0

    def test_create_source_missing_name(self, client, db_session, mock_admin_client):
        """Test creating source without name."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources",
                json={
                    "connector_type": "rss",
                }
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_create_source_missing_connector_type(self, client, db_session, mock_admin_client):
        """Test creating source without connector_type."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources",
                json={
                    "name": "Test Source",
                }
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestSourceSchedule:
    """Tests for source schedule endpoints."""

    def test_set_schedule_no_auth(self, client):
        """Test that setting schedule requires authentication."""
        response = client.post(
            "/api/v1/admin/sources/src_12345678/schedule",
            json={"interval": 3600}
        )
        assert response.status_code == 401

    def test_remove_schedule_no_auth(self, client):
        """Test that removing schedule requires authentication."""
        response = client.delete("/api/v1/admin/sources/src_12345678/schedule")
        assert response.status_code == 401

    def test_set_schedule_invalid_source_id(self, client, db_session, mock_admin_client):
        """Test setting schedule with invalid source_id format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/invalid_id/schedule",
                json={"interval": 3600}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Invalid source_id format" in response.json()["detail"]

    def test_set_schedule_nonexistent_source(self, client, db_session, mock_admin_client):
        """Test setting schedule for nonexistent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/src_deadbeef/schedule",
                json={"interval": 3600}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_set_schedule_invalid_interval(self, client, db_session, mock_admin_client):
        """Test setting schedule with interval below minimum."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/src_12345678/schedule",
                json={"interval": 60}  # Below minimum of 300
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestSourceTest:
    """Tests for source test endpoint."""

    def test_test_source_no_auth(self, client):
        """Test that testing source requires authentication."""
        response = client.post("/api/v1/admin/sources/src_12345678/test")
        assert response.status_code == 401

    def test_test_source_invalid_source_id(self, client, db_session, mock_admin_client):
        """Test testing source with invalid source_id format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/invalid_id/test")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Invalid source_id format" in response.json()["detail"]

    def test_test_source_nonexistent_source(self, client, db_session, mock_admin_client):
        """Test testing nonexistent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/src_deadbeef/test")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404


class TestSourceDefaults:
    """Tests for source defaults endpoints."""

    def test_get_defaults_no_auth(self, client):
        """Test that getting defaults requires authentication."""
        response = client.get("/api/v1/admin/sources/defaults")
        assert response.status_code == 401

    def test_update_defaults_no_auth(self, client):
        """Test that updating defaults requires authentication."""
        response = client.patch(
            "/api/v1/admin/sources/defaults",
            json={"default_fetch_interval": 1800}
        )
        assert response.status_code == 401

    def test_get_defaults_with_admin(self, client, db_session, mock_admin_client):
        """Test getting defaults with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/defaults")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "default_fetch_interval" in data

    def test_update_defaults_with_admin(self, client, db_session, mock_admin_client):
        """Test updating defaults with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/admin/sources/defaults",
                json={"default_fetch_interval": 1800}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["default_fetch_interval"] == 1800

    def test_update_defaults_invalid_interval(self, client, db_session, mock_admin_client):
        """Test updating defaults with invalid interval."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.patch(
                "/api/v1/admin/sources/defaults",
                json={"default_fetch_interval": 60}  # Below minimum of 300
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestSourceImport:
    """Tests for source import endpoint."""

    def test_import_sources_no_auth(self, client):
        """Test that importing sources requires authentication."""
        opml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline type="rss" xmlUrl="https://example.com/feed.xml" title="Test Feed"/>
  </body>
</opml>'''
        response = client.post(
            "/api/v1/admin/sources/import",
            files={"file": ("test.opml", io.BytesIO(opml_content), "application/xml")}
        )
        assert response.status_code == 401

    def test_import_sources_with_admin(self, client, db_session, mock_admin_client):
        """Test importing sources with admin permission."""
        opml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline type="rss" xmlUrl="https://example.com/feed.xml" title="Test Feed"/>
    <outline type="rss" xmlUrl="https://example2.com/feed.xml" title="Test Feed 2"/>
  </body>
</opml>'''
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/import",
                files={"file": ("test.opml", io.BytesIO(opml_content), "application/xml")}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_import_sources_with_options(self, client, db_session, mock_admin_client):
        """Test importing sources with force and skip_invalid options."""
        opml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline type="rss" xmlUrl="https://example.com/feed.xml" title="Test Feed"/>
  </body>
</opml>'''
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/import",
                files={"file": ("test.opml", io.BytesIO(opml_content), "application/xml")},
                data={"force": "true", "skip_invalid": "false"}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200

    def test_import_sources_empty_opml(self, client, db_session, mock_admin_client):
        """Test importing empty OPML file."""
        opml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
  </body>
</opml>'''
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/import",
                files={"file": ("empty.opml", io.BytesIO(opml_content), "application/xml")}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "No RSS feeds found" in response.json()["detail"]

    def test_import_sources_invalid_xml(self, client, db_session, mock_admin_client):
        """Test importing invalid XML file."""
        invalid_content = b"This is not valid XML"
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post(
                "/api/v1/admin/sources/import",
                files={"file": ("invalid.xml", io.BytesIO(invalid_content), "application/xml")}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Invalid OPML file" in response.json()["detail"]


class TestSourceExport:
    """Tests for source export endpoint."""

    def test_export_sources_no_auth(self, client):
        """Test that exporting sources requires authentication."""
        response = client.get("/api/v1/admin/sources/export")
        assert response.status_code == 401

    def test_export_sources_with_admin(self, client, db_session, mock_admin_client):
        """Test exporting sources with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/export")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"
        assert "attachment" in response.headers.get("content-disposition", "")

    def test_export_sources_filter_by_status(self, client, db_session, mock_admin_client):
        """Test exporting sources filtered by status."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/export?status=ACTIVE")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"

    def test_export_sources_filter_by_tier(self, client, db_session, mock_admin_client):
        """Test exporting sources filtered by tier."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/export?tier=T1")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml"

    def test_export_opml_structure(self, client, db_session, mock_admin_client):
        """Test that exported OPML has valid structure."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/export")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        content = response.text
        assert '<?xml version="1.0"' in content
        assert '<opml version="2.0">' in content
        assert '</opml>' in content


class TestSourceGetUpdateDelete:
    """Tests for get, update, delete source endpoints."""

    def test_get_source_no_auth(self, client):
        """Test that getting a source requires authentication."""
        response = client.get("/api/v1/admin/sources/src_12345678")
        assert response.status_code == 401

    def test_update_source_no_auth(self, client):
        """Test that updating a source requires authentication."""
        response = client.put(
            "/api/v1/admin/sources/src_12345678",
            json={"name": "Updated Name"}
        )
        assert response.status_code == 401

    def test_delete_source_no_auth(self, client):
        """Test that deleting a source requires authentication."""
        response = client.delete("/api/v1/admin/sources/src_12345678")
        assert response.status_code == 401

    def test_get_source_invalid_id(self, client, db_session, mock_admin_client):
        """Test getting source with invalid ID format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/invalid_id")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Invalid source_id format" in response.json()["detail"]

    def test_get_source_not_found(self, client, db_session, mock_admin_client):
        """Test getting nonexistent source."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/sources/src_deadbeef")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_update_source_invalid_id(self, client, db_session, mock_admin_client):
        """Test updating source with invalid ID format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.put(
                "/api/v1/admin/sources/invalid_id",
                json={"name": "Updated Name"}
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400

    def test_delete_source_invalid_id(self, client, db_session, mock_admin_client):
        """Test deleting source with invalid ID format."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/sources/invalid_id")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400