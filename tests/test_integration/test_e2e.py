"""
End-to-End Integration Tests for cyber-pulse.

Tests the complete data flow:
Source → Connector → Item → Normalization → Quality Gate → Content → API
"""

import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from cyberpulse.api.main import app
from cyberpulse.api.auth import get_current_client
from cyberpulse.api.routers.content import get_db as content_get_db
from cyberpulse.api.routers.health import get_db as health_get_db
from cyberpulse.models import (
    ApiClient,
    ApiClientStatus,
    Content,
    ItemStatus,
    SourceStatus,
    SourceTier,
)
from cyberpulse.services import (
    ContentService,
    ItemService,
    NormalizationService,
    QualityGateService,
    SourceService,
)


@pytest.fixture
def api_client():
    """Create a TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_api_client():
    """Create a mock API client for authentication."""
    client = Mock(spec=ApiClient)
    client.client_id = "cli_e2etest01"
    client.name = "E2E Test Client"
    client.status = ApiClientStatus.ACTIVE
    client.permissions = ["read"]
    return client


@pytest.fixture
def source_service(db_session):
    """Create a SourceService instance."""
    return SourceService(db_session)


@pytest.fixture
def item_service(db_session):
    """Create an ItemService instance."""
    return ItemService(db_session)


@pytest.fixture
def normalization_service():
    """Create a NormalizationService instance."""
    return NormalizationService()


@pytest.fixture
def quality_gate_service():
    """Create a QualityGateService instance."""
    return QualityGateService()


@pytest.fixture
def content_service(db_session):
    """Create a ContentService instance."""
    return ContentService(db_session)


@pytest.mark.integration
class TestE2EDataFlow:
    """
    End-to-end tests for the complete data flow.

    Tests: Source → Item → Normalization → Quality Gate → Content
    """

    def test_rss_source_to_content_flow(
        self,
        db_session,
        source_service,
        item_service,
        normalization_service,
        quality_gate_service,
        content_service,
    ):
        """
        Test complete flow for RSS source.

        Steps:
        1. Create source via SourceService
        2. Create item via ItemService
        3. Normalize item via NormalizationService
        4. Quality gate check via QualityGateService
        5. Verify content was created via ContentService
        6. Verify source statistics updated
        """
        # Step 1: Create source via SourceService
        source, message = source_service.add_source(
            name="E2E Test RSS Source",
            connector_type="rss",
            tier=SourceTier.T1,
            config={
                "url": "https://example.com/feed.xml",
                "fetch_interval": 3600,
            },
        )

        assert source is not None
        assert source.source_id.startswith("src_")
        assert source.name == "E2E Test RSS Source"
        assert source.connector_type == "rss"
        assert source.tier == SourceTier.T1
        assert source.status == SourceStatus.ACTIVE

        # Step 2: Create item via ItemService
        published_at = datetime.now(timezone.utc) - timedelta(hours=1)
        raw_content = """
        <html>
        <head><title>Test Article</title></head>
        <body>
        <h1>Important Security Update</h1>
        <p>This is a detailed article about an important security update.
        It contains multiple paragraphs with relevant information about
        the latest vulnerability disclosure and mitigation strategies.</p>
        <p>Additional context and technical details are provided here.</p>
        </body>
        </html>
        """

        item = item_service.create_item(
            source_id=source.source_id,
            external_id="rss-article-001",
            url="https://example.com/article/001",
            title="Important Security Update",
            raw_content=raw_content,
            published_at=published_at,
            content_hash=hashlib.sha256(raw_content.encode()).hexdigest(),
            raw_metadata={
                "author": "Security Team",
                "tags": ["security", "update"],
            },
        )

        assert item is not None
        assert item.item_id.startswith("item_")
        assert item.source_id == source.source_id
        assert item.status == ItemStatus.NEW

        # Step 3: Normalize item via NormalizationService
        normalization_result = normalization_service.normalize(
            title=item.title,
            raw_content=item.raw_content,
            url=item.url,
        )

        assert normalization_result is not None
        assert normalization_result.normalized_title == "Important Security Update"
        assert len(normalization_result.normalized_body) > 0
        assert normalization_result.canonical_hash is not None
        assert normalization_result.word_count > 0
        assert normalization_result.extraction_method in ("trafilatura", "raw")

        # Step 4: Quality gate check via QualityGateService
        quality_result = quality_gate_service.check(item, normalization_result)

        assert quality_result is not None
        # Quality gate should pass (valid date, title, body, URL)
        assert quality_result.decision.value == "pass"
        assert quality_result.metrics is not None
        assert "meta_completeness" in quality_result.metrics
        assert "content_completeness" in quality_result.metrics
        assert "noise_ratio" in quality_result.metrics

        # Update item status to NORMALIZED
        item_service.update_item_status(
            item.item_id,
            "normalized",
            quality_metrics={
                "meta_completeness": quality_result.metrics["meta_completeness"],
                "content_completeness": quality_result.metrics["content_completeness"],
                "noise_ratio": quality_result.metrics["noise_ratio"],
            },
        )

        # Step 5: Verify content was created via ContentService
        content, is_new = content_service.create_or_get_content(
            canonical_hash=normalization_result.canonical_hash,
            normalized_title=normalization_result.normalized_title,
            normalized_body=normalization_result.normalized_body,
            item=item,
        )

        assert content is not None
        assert is_new is True
        assert content.content_id.startswith("cnt_")
        assert content.canonical_hash == normalization_result.canonical_hash
        assert content.normalized_title == normalization_result.normalized_title
        assert content.source_count == 1

        # Verify item is linked to content
        db_session.refresh(item)
        assert item.content_id == content.content_id

        # Step 6: Verify source statistics updated
        # Note: In current implementation, source statistics are not auto-updated
        # This is a verification that the source exists and can be queried
        stats = source_service.get_source_statistics(source.source_id)
        assert stats is not None
        assert stats["source_id"] == source.source_id
        assert stats["name"] == "E2E Test RSS Source"

    def test_duplicate_content_deduplication(
        self,
        db_session,
        source_service,
        item_service,
        normalization_service,
        quality_gate_service,
        content_service,
    ):
        """
        Test that duplicate content is deduplicated.

        When two items have the same canonical_hash, they should map to the same Content.
        """
        # Create source
        source, _ = source_service.add_source(
            name="Deduplication Test Source",
            connector_type="rss",
            tier=SourceTier.T2,
        )

        # Create first item
        published_at = datetime.now(timezone.utc)
        raw_content = "<p>This is the original content for deduplication testing.</p>"

        item1 = item_service.create_item(
            source_id=source.source_id,
            external_id="dedup-001",
            url="https://example.com/dedup/001",
            title="Deduplication Test Article",
            raw_content=raw_content,
            published_at=published_at,
            content_hash=hashlib.sha256(b"content1").hexdigest(),
        )

        # Normalize and create content for first item
        norm_result1 = normalization_service.normalize(
            title=item1.title,
            raw_content=item1.raw_content,
            url=item1.url,
        )

        quality_result1 = quality_gate_service.check(item1, norm_result1)
        assert quality_result1.decision.value == "pass"

        content1, is_new1 = content_service.create_or_get_content(
            canonical_hash=norm_result1.canonical_hash,
            normalized_title=norm_result1.normalized_title,
            normalized_body=norm_result1.normalized_body,
            item=item1,
        )

        assert is_new1 is True
        original_content_id = content1.content_id

        # Create second item with same content (should deduplicate)
        item2 = item_service.create_item(
            source_id=source.source_id,
            external_id="dedup-002",
            url="https://example.com/dedup/002",
            title="Deduplication Test Article",  # Same title
            raw_content=raw_content,  # Same content
            published_at=published_at,
            content_hash=hashlib.sha256(b"content2").hexdigest(),
        )

        norm_result2 = normalization_service.normalize(
            title=item2.title,
            raw_content=item2.raw_content,
            url=item2.url,
        )

        quality_result2 = quality_gate_service.check(item2, norm_result2)
        assert quality_result2.decision.value == "pass"

        # Should find existing content (same canonical_hash)
        content2, is_new2 = content_service.create_or_get_content(
            canonical_hash=norm_result2.canonical_hash,
            normalized_title=norm_result2.normalized_title,
            normalized_body=norm_result2.normalized_body,
            item=item2,
        )

        assert is_new2 is False
        assert content2.content_id == original_content_id
        assert content2.source_count == 2  # Incremented from 1 to 2

        # Both items should point to same content
        db_session.refresh(item1)
        db_session.refresh(item2)
        assert item1.content_id == original_content_id
        assert item2.content_id == original_content_id

    def test_quality_gate_rejection(
        self,
        db_session,
        source_service,
        item_service,
        normalization_service,
        quality_gate_service,
    ):
        """
        Test that items failing quality gate are rejected.

        Items with invalid/missing required fields should be rejected.
        """
        # Create source
        source, _ = source_service.add_source(
            name="Quality Gate Test Source",
            connector_type="rss",
            tier=SourceTier.T2,
        )

        # Create item with short title (should fail quality gate)
        published_at = datetime.now(timezone.utc)
        raw_content = "<p>Some content here.</p>"

        item = item_service.create_item(
            source_id=source.source_id,
            external_id="quality-fail-001",
            url="https://example.com/quality/001",
            title="Bad",  # Too short (< 5 chars)
            raw_content=raw_content,
            published_at=published_at,
            content_hash=hashlib.sha256(b"quality_fail").hexdigest(),
        )

        norm_result = normalization_service.normalize(
            title=item.title,
            raw_content=item.raw_content,
            url=item.url,
        )

        quality_result = quality_gate_service.check(item, norm_result)

        # Should be rejected due to short title
        assert quality_result.decision.value == "reject"
        assert quality_result.rejection_reason is not None
        assert "Title too short" in quality_result.rejection_reason


@pytest.mark.integration
class TestAPIDataRetrieval:
    """
    End-to-end tests for API data retrieval.

    Tests the API layer with real database interactions.
    """

    def test_content_list_endpoint(
        self, api_client, db_session, mock_api_client
    ):
        """
        Test content can be retrieved via API.

        The endpoint requires authentication. Without auth, returns 401.
        With valid auth, returns 200 with content list.
        """
        # Create test content
        content = Content(
            content_id="cnt_20260319120000_e2etest",
            canonical_hash="e2e_test_hash_001",
            normalized_title="E2E Test Content",
            normalized_body="This is test content for E2E API testing.",
            first_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_seen_at=datetime.now(timezone.utc).replace(tzinfo=None),
            source_count=1,
        )
        db_session.add(content)
        db_session.commit()

        # Test without authentication - should return 401
        app.dependency_overrides[content_get_db] = lambda: db_session
        try:
            response = api_client.get("/api/v1/content")
            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

        # Test with authentication - should return 200
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            response = api_client.get("/api/v1/content")

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "next_cursor" in data
            assert "has_more" in data
            assert "count" in data
        finally:
            app.dependency_overrides.clear()

    def test_health_endpoint(self, api_client, db_session):
        """
        Test health endpoint returns 200.

        The health endpoint checks database connectivity and returns status.
        """
        # Override database dependency
        app.dependency_overrides[health_get_db] = lambda: db_session
        try:
            response = api_client.get("/health")

            assert response.status_code == 200
            data = response.json()

            assert "status" in data
            assert "version" in data
            assert "components" in data
            assert "database" in data["components"]
            assert "api" in data["components"]

            # With working database, status should be healthy
            assert data["status"] == "healthy"
            assert data["components"]["database"] == "healthy"
            assert data["components"]["api"] == "healthy"
        finally:
            app.dependency_overrides.clear()

    def test_full_flow_to_api_retrieval(
        self,
        api_client,
        db_session,
        mock_api_client,
        source_service,
        item_service,
        normalization_service,
        quality_gate_service,
        content_service,
    ):
        """
        Test complete flow from source creation to API retrieval.

        This is a comprehensive E2E test that:
        1. Creates a source and item
        2. Normalizes and passes quality gate
        3. Creates content
        4. Verifies content is retrievable via API
        """
        # Step 1: Create source and item
        source, _ = source_service.add_source(
            name="API Retrieval Test Source",
            connector_type="rss",
            tier=SourceTier.T0,
        )

        published_at = datetime.now(timezone.utc)
        raw_content = """
        <article>
        <h1>Critical Security Advisory</h1>
        <p>A critical security advisory has been released addressing multiple
        vulnerabilities in enterprise software. Organizations are advised to
        apply patches immediately to mitigate potential risks.</p>
        <p>The advisory includes technical details and remediation steps for
        each identified vulnerability.</p>
        </article>
        """

        item = item_service.create_item(
            source_id=source.source_id,
            external_id="api-retrieval-001",
            url="https://example.com/api-test/001",
            title="Critical Security Advisory",
            raw_content=raw_content,
            published_at=published_at,
            content_hash=hashlib.sha256(raw_content.encode()).hexdigest(),
            raw_metadata={"author": "Security Advisory Team"},
        )

        # Step 2: Normalize
        norm_result = normalization_service.normalize(
            title=item.title,
            raw_content=item.raw_content,
            url=item.url,
        )

        # Step 3: Quality gate
        quality_result = quality_gate_service.check(item, norm_result)
        assert quality_result.decision.value == "pass"

        # Step 4: Create content
        content, is_new = content_service.create_or_get_content(
            canonical_hash=norm_result.canonical_hash,
            normalized_title=norm_result.normalized_title,
            normalized_body=norm_result.normalized_body,
            item=item,
        )

        assert is_new is True

        # Step 5: Verify via API
        app.dependency_overrides[content_get_db] = lambda: db_session
        app.dependency_overrides[get_current_client] = lambda: mock_api_client
        try:
            # List content
            response = api_client.get("/api/v1/content")
            assert response.status_code == 200

            data = response.json()
            assert data["count"] >= 1

            # Find our created content
            content_ids = [c["content_id"] for c in data["data"]]
            assert content.content_id in content_ids

            # Get single content
            response = api_client.get(f"/api/v1/content/{content.content_id}")
            assert response.status_code == 200

            content_data = response.json()
            assert content_data["content_id"] == content.content_id
            assert content_data["normalized_title"] == norm_result.normalized_title
            assert content_data["source_count"] == 1
        finally:
            app.dependency_overrides.clear()