"""Test that API responses preserve Unicode characters."""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.auth import get_current_client
from cyberpulse.api.main import app
from cyberpulse.api.routers.health import get_db as health_get_db
from cyberpulse.api.routers.items import get_db as items_get_db
from cyberpulse.models import (
    ApiClient,
    ApiClientStatus,
    Item,
    ItemStatus,
    Source,
    SourceStatus,
    SourceTier,
)


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


@pytest.fixture
def test_source(db_session):
    """Create a test source for items."""
    source = Source(
        source_id="src_unicode_test",
        name="Unicode Test Source",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


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
        app.dependency_overrides[health_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/health")
            assert response.status_code == 200
            raw_text = response.text
            assert "\\u" not in raw_text, "Error messages should not escape Unicode"
        finally:
            app.dependency_overrides.clear()

    def test_chinese_item_unicode(self, client, db_session, mock_api_client, test_source):
        """Test that Chinese characters are preserved in item responses."""
        now = datetime.now(UTC).replace(tzinfo=None)
        # Create item with Chinese characters
        item = Item(
            item_id="item_unicode_test",
            source_id=test_source.source_id,
            external_id="ext_unicode_test",
            url="https://example.com/unicode-test",
            title="测试标题",
            raw_content="原始内容",
            normalized_title="测试标题",
            normalized_body="这是一段中文内容，用于测试 Unicode 编码。",
            canonical_hash="hash_unicode_test",
            word_count=15,
            published_at=now - timedelta(hours=1),
            fetched_at=now,
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
        db_session.commit()

        # Override dependencies
        app.dependency_overrides[items_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = client.get("/api/v1/items")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        raw_text = response.text

        # Verify Chinese characters are present, not escaped
        assert "测试标题" in raw_text, "Chinese title should be preserved"
        assert "\\u" not in raw_text, "Unicode should not be escaped"
        assert "测试" in raw_text, "Chinese characters should be readable"
