"""Tests for Source Admin API."""

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.auth import get_current_client
from cyberpulse.api.dependencies import get_db
from cyberpulse.api.main import app
from cyberpulse.models import (
    ApiClient,
    ApiClientStatus,
    Item,
    Job,
    JobStatus,
    JobTrigger,
    JobType,
    Source,
    SourceStatus,
)
from cyberpulse.services.source_quality_validator import SourceValidationResult


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


class TestSourceTestWeb:
    """Tests for web source test endpoint."""

    def _create_web_source(self, db_session, source_id, config):
        source = Source(
            source_id=source_id,
            name=f"Web-{source_id}",
            connector_type="web",
            config=config,
        )
        db_session.add(source)
        db_session.commit()
        return source

    def test_web_source_test_success(self, client, db_session, mock_admin_client):
        """web test 成功：items_found = _extract_links 链接数 + 无 link_pattern warning。"""
        source = self._create_web_source(
            db_session, "src_a1000001", {"base_url": "https://example.com/"}
        )
        html = '<html><body><a href="https://example.com/a">A</a></body></html>'
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status = MagicMock()
            r.text = html
            mock_client.get.return_value = r
            mock_cls.return_value = mock_client
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(f"/api/v1/admin/sources/{source.source_id}/test")
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["test_result"] == "success"
        assert data["items_found"] == 1
        assert any("link_pattern" in w for w in data["warnings"])

    def test_web_source_test_http_403(self, client, db_session, mock_admin_client):
        """web test 403 -> error_type=http_403 + 反爬建议。"""
        source = self._create_web_source(
            db_session, "src_a1000002", {"base_url": "https://example.com/"}
        )
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            r = MagicMock()
            r.status_code = 403
            r.reason_phrase = "Forbidden"
            r.raise_for_status.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=r
            )
            mock_client.get.return_value = r
            mock_cls.return_value = mock_client
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(f"/api/v1/admin/sources/{source.source_id}/test")
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["test_result"] == "failed"
        assert resp.json()["error_type"] == "http_403"
        assert "反爬" in resp.json()["suggestion"]

    def test_web_source_test_missing_base_url(self, client, db_session, mock_admin_client):
        """web test 缺 base_url -> config 错误。"""
        source = self._create_web_source(db_session, "src_a1000003", {})
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            resp = client.post(f"/api/v1/admin/sources/{source.source_id}/test")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert data["test_result"] == "failed"
        assert data["error_type"] == "config"


class TestSourceValidateWeb:
    """Tests for web source validate endpoint."""

    def test_web_source_validate_success(self, client, db_session, mock_admin_client):
        """web validate 成功：写入 content_type/avg_content_length，有 link_pattern 无 warning。"""
        source = Source(
            source_id="src_a1000004",
            name="WebValidate",
            connector_type="web",
            config={"base_url": "https://example.com/", "link_pattern": r"/a"},
        )
        db_session.add(source)
        db_session.commit()
        with patch(
            "cyberpulse.api.routers.admin.sources.SourceQualityValidator"
        ) as mock_vc:
            instance = mock_vc.return_value
            result = SourceValidationResult(
                is_valid=True,
                content_type="article",
                sample_completeness=1.0,
                avg_content_length=500,
                samples_analyzed=2,
            )
            instance.validate_web_source = AsyncMock(return_value=result)
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(f"/api/v1/admin/sources/{source.source_id}/validate")
            finally:
                app.dependency_overrides.clear()

        data = resp.json()
        assert data["is_valid"] is True
        assert data["content_type"] == "article"
        assert data["warnings"] == []  # 有 link_pattern -> 无 warning
        db_session.refresh(source)
        assert source.content_type == "article"
        assert source.avg_content_length == 500

    def test_web_source_validate_sets_pending_review(self, client, db_session, mock_admin_client):
        """web validate 失败 -> 置 pending_review。"""
        source = Source(
            source_id="src_a1000005",
            name="WebValidateBad",
            connector_type="web",
            config={"base_url": "https://example.com/"},
        )
        db_session.add(source)
        db_session.commit()
        with patch(
            "cyberpulse.api.routers.admin.sources.SourceQualityValidator"
        ) as mock_vc:
            instance = mock_vc.return_value
            result = SourceValidationResult(
                is_valid=False,
                content_type="empty",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Could not fetch any article samples from listing",
            )
            instance.validate_web_source = AsyncMock(return_value=result)
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(f"/api/v1/admin/sources/{source.source_id}/validate")
            finally:
                app.dependency_overrides.clear()

        data = resp.json()
        assert data["is_valid"] is False
        assert any("link_pattern" in w for w in data["warnings"])  # 无 pattern -> warning
        db_session.refresh(source)
        assert source.pending_review is True
        assert source.review_reason is not None


class TestSourceCreateWeb:
    """Tests for web source create with quality validation (R18)."""

    def test_create_web_source_validation_passed(self, client, db_session, mock_admin_client):
        """验证通过：content_type 写入，无 pending_review，有 link_pattern 无 warning。"""
        with patch(
            "cyberpulse.api.routers.admin.sources.SourceQualityValidator"
        ) as mock_vc:
            instance = mock_vc.return_value
            result = SourceValidationResult(
                is_valid=True,
                content_type="article",
                sample_completeness=1.0,
                avg_content_length=500,
            )
            instance.validate_web_source = AsyncMock(return_value=result)
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(
                    "/api/v1/admin/sources",
                    json={
                        "name": "Web Create Pass",
                        "connector_type": "web",
                        "tier": "T1",
                        "config": {
                            "base_url": "https://example.com/",
                            "link_pattern": r"/a",
                        },
                    },
                )
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["content_type"] == "article"
        assert data["pending_review"] is False
        assert data["warnings"] == []

    def test_create_web_source_validation_failure_tolerated(self, client, db_session, mock_admin_client):
        """验证失败仅置 pending_review，不阻断创建。"""
        with patch(
            "cyberpulse.api.routers.admin.sources.SourceQualityValidator"
        ) as mock_vc:
            instance = mock_vc.return_value
            result = SourceValidationResult(
                is_valid=False,
                content_type="empty",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Could not fetch any article samples from listing",
            )
            instance.validate_web_source = AsyncMock(return_value=result)
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(
                    "/api/v1/admin/sources",
                    json={
                        "name": "Web Create Fail",
                        "connector_type": "web",
                        "tier": "T1",
                        "config": {"base_url": "https://example.com/"},
                    },
                )
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 201
        data = resp.json()
        assert data["pending_review"] is True
        assert data["review_reason"] is not None
        assert any("link_pattern" in w for w in data["warnings"])  # 无 pattern -> warning

    def test_create_web_source_validation_error_tolerated(self, client, db_session, mock_admin_client):
        """验证异常也容错：pending_review 但创建成功。"""
        with patch(
            "cyberpulse.api.routers.admin.sources.SourceQualityValidator"
        ) as mock_vc:
            instance = mock_vc.return_value
            instance.validate_web_source = AsyncMock(side_effect=Exception("boom"))
            app.dependency_overrides[get_current_client] = lambda: mock_admin_client
            app.dependency_overrides[get_db] = lambda: db_session
            try:
                resp = client.post(
                    "/api/v1/admin/sources",
                    json={
                        "name": "Web Create Error",
                        "connector_type": "web",
                        "tier": "T1",
                        "config": {"base_url": "https://example.com/"},
                    },
                )
            finally:
                app.dependency_overrides.clear()

        assert resp.status_code == 201
        assert resp.json()["pending_review"] is True

    def test_create_web_source_without_base_url_skips_validation(self, client, db_session, mock_admin_client):
        """无 base_url -> 跳过验证，直接创建（无 pending_review）。"""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            resp = client.post(
                "/api/v1/admin/sources",
                json={
                    "name": "Web Create NoUrl",
                    "connector_type": "web",
                    "tier": "T1",
                    "config": {},
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 201
        assert resp.json()["pending_review"] is False


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


class TestSourceCleanup:
    """Tests for source cleanup endpoint."""

    def test_cleanup_sources_no_auth(self, client):
        """Test that cleanup requires authentication."""
        response = client.post("/api/v1/admin/sources/cleanup")
        assert response.status_code == 401

    def test_cleanup_sources_with_removed_sources(self, client, db_session, mock_admin_client):
        """Test cleanup removes REMOVED sources and their items/jobs."""
        # Create a REMOVED source with items and jobs
        source = Source(
            source_id="src_removed01",
            name="Removed Source",
            connector_type="rss",
            status=SourceStatus.REMOVED,
        )
        db_session.add(source)

        # Add items
        item1 = Item(
            item_id="item_src01_01",
            source_id="src_removed01",
            external_id="ext1",
            url="https://example.com/1",
            title="Item 1",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
        )
        item2 = Item(
            item_id="item_src01_02",
            source_id="src_removed01",
            external_id="ext2",
            url="https://example.com/2",
            title="Item 2",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
        )
        db_session.add_all([item1, item2])

        # Add job
        job = Job(
            job_id="job_src01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id="src_removed01",
        )
        db_session.add(job)

        # Create an ACTIVE source that should NOT be deleted
        active_source = Source(
            source_id="src_active01",
            name="Active Source",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(active_source)

        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/cleanup")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_sources"] == 1
        assert data["deleted_items"] == 2
        assert data["deleted_jobs"] == 1

        # Verify REMOVED source is deleted
        assert db_session.get(Source, "src_removed01") is None

        # Verify ACTIVE source still exists
        assert db_session.get(Source, "src_active01") is not None

    def test_cleanup_sources_no_removed_sources(self, client, db_session, mock_admin_client):
        """Test cleanup when no REMOVED sources exist."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/cleanup")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_sources"] == 0
        assert data["deleted_items"] == 0
        assert data["deleted_jobs"] == 0


class TestSourceUpdateURLTrigger:
    """Tests for URL change triggering ingestion jobs."""

    def test_update_source_url_triggers_ingestion(self, client, db_session, mock_admin_client):
        """Test that updating source URL triggers ingestion job."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        # Create source
        source = Source(
            source_id="src_test001",
            name="Test Source",
            connector_type="rss",
            config={"feed_url": "https://old.example.com/feed"},
        )
        db_session.add(source)
        db_session.commit()

        try:
            # Update URL
            response = client.put(
                "/api/v1/admin/sources/src_test001",
                json={"config": {"feed_url": "https://new.example.com/feed"}},
            )
            assert response.status_code == 200

            # Verify job was created with URL_UPDATE trigger
            job = db_session.query(Job).filter(
                Job.source_id == "src_test001",
                Job.trigger == JobTrigger.URL_UPDATE
            ).first()
            assert job is not None
        finally:
            app.dependency_overrides.clear()

    def test_update_source_same_url_no_job(self, client, db_session, mock_admin_client):
        """Test that updating with same URL does not trigger job."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        # Create source
        source = Source(
            source_id="src_test002",
            name="Test Source 2",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed"},
        )
        db_session.add(source)
        db_session.commit()

        try:
            # Update with same URL
            response = client.put(
                "/api/v1/admin/sources/src_test002",
                json={"config": {"feed_url": "https://example.com/feed"}},
            )
            assert response.status_code == 200

            # Verify no job was created
            job = db_session.query(Job).filter(
                Job.source_id == "src_test002",
                Job.trigger == JobTrigger.URL_UPDATE
            ).first()
            assert job is None
        finally:
            app.dependency_overrides.clear()
