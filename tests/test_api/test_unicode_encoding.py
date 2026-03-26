"""Test that API responses preserve Unicode characters."""
import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.api.routers.content import get_db as content_get_db
from cyberpulse.models import ApiClient, ApiClientStatus, Content, ContentStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_api_client():
    """Create a mock API client for authentication."""
    client = Mock(spec=ApiClient)
    client.client_id = "cli_test_unicode"
    client.name = "Test Client"
    client.status = ApiClientStatus.ACTIVE
    client.permissions = ["read"]
    return client


class TestUnicodeEncoding:
    """Verify Unicode characters are not escaped in JSON responses."""

    def test_health_endpoint_unicode(self, client):
        """Health endpoint should not escape Unicode in response."""
        response = client.get("/health")
        assert response.status_code == 200
        # Response should contain actual characters, not escape sequences
        raw_text = response.text
        assert "\\u" not in raw_text, "Unicode characters should not be escaped"

    def test_error_response_encoding(self, client, db_session, mock_api_client):
        """Error responses should preserve Unicode in error messages."""
        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents/content_notfound")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        raw_text = response.text
        assert "\\u" not in raw_text, "Error messages should not escape Unicode"

    def test_chinese_content_unicode(self, client, db_session, mock_api_client):
        """Test that Chinese characters are preserved in content responses."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Create content with Chinese characters
        content = Content(
            content_id="cnt_test_chinese",
            canonical_hash="hash_test_unique",
            normalized_title="测试标题",
            normalized_body="这是一段中文内容，用于测试 Unicode 编码。",
            first_seen_at=now,
            last_seen_at=now,
            source_count=1,
            status=ContentStatus.ACTIVE,
        )
        db_session.add(content)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/contents")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        raw_text = response.text

        # Verify Chinese characters are present, not escaped
        assert "测试标题" in raw_text, "Chinese title should be preserved"
        assert "\\u" not in raw_text, "Unicode should not be escaped"
        assert "测试" in raw_text, "Chinese characters should be readable"