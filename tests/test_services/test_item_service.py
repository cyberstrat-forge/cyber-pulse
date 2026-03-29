from datetime import UTC, datetime, timedelta

import pytest

from cyberpulse.models import ItemStatus, Source, SourceStatus, SourceTier
from cyberpulse.services import ItemService


@pytest.fixture
def item_service(db_session):
    """Create an ItemService instance."""
    return ItemService(db_session)


@pytest.fixture
def test_source(db_session):
    """Create a test source for items."""
    source = Source(
        source_id="src_test01",
        name="Test Source",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


class TestCreateItem:
    """Tests for create_item method."""

    def test_create_item_success(self, item_service, test_source):
        """Test creating a new item."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        item = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_001",
            url="https://example.com/article/001",
            title="Test Article",
            raw_content="This is test content",
            published_at=published_at,
        )

        assert item is not None
        assert item.item_id.startswith("item_")
        assert item.source_id == test_source.source_id
        assert item.external_id == "ext_001"
        assert item.url == "https://example.com/article/001"
        assert item.title == "Test Article"
        assert item.raw_content == "This is test content"
        assert item.status == ItemStatus.NEW
        assert item.raw_metadata == {}
        assert item.fetched_at is not None

    def test_create_item_with_metadata(self, item_service, test_source):
        """Test creating an item with metadata."""
        published_at = datetime.now(UTC) - timedelta(hours=1)
        metadata = {"author": "John Doe", "tags": ["tech", "security"]}

        item = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_002",
            url="https://example.com/article/002",
            title="Article with Metadata",
            raw_content="Content with metadata",
            published_at=published_at,
            raw_metadata=metadata,
        )

        assert item is not None
        assert item.raw_metadata == metadata

    def test_create_duplicate_item_by_external_id(self, item_service, test_source):
        """Test that duplicate by external_id returns existing item."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        # Create first item
        item1 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_duplicate",
            url="https://example.com/article/duplicate",
            title="Original Article",
            raw_content="Original content",
            published_at=published_at,
        )

        # Try to create duplicate with same external_id but different url
        item2 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_duplicate",  # Same external_id
            url="https://example.com/article/different",  # Different URL
            title="Duplicate Article",
            raw_content="Different content",
            published_at=published_at,
        )

        # Should return the existing item
        assert item2.item_id == item1.item_id
        assert item2.title == "Original Article"
        assert item2.url == "https://example.com/article/duplicate"

    def test_create_duplicate_item_by_url(self, item_service, test_source):
        """Test that duplicate by url returns existing item."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        # Create first item
        item1 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_url_test_1",
            url="https://example.com/article/same-url",
            title="Original URL Article",
            raw_content="Original content",
            published_at=published_at,
        )

        # Try to create duplicate with same url but different external_id
        item2 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_url_test_2",  # Different external_id
            url="https://example.com/article/same-url",  # Same URL
            title="Duplicate URL Article",
            raw_content="Different content",
            published_at=published_at,
        )

        # Should return the existing item
        assert item2.item_id == item1.item_id
        assert item2.title == "Original URL Article"
        assert item2.external_id == "ext_url_test_1"

    def test_generate_item_id(self, item_service):
        """Test item ID generation."""
        id1 = item_service.generate_item_id()
        id2 = item_service.generate_item_id()

        assert id1.startswith("item_")
        assert id2.startswith("item_")
        assert id1 != id2  # IDs should be unique
        assert len(id1) == 13  # "item_" + 8 characters


class TestGetItemsBySource:
    """Tests for get_items_by_source method."""

    def test_get_items_by_source(self, item_service, test_source):
        """Test listing items for a source."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        # Create multiple items
        for i in range(3):
            item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_list_{i}",
                url=f"https://example.com/article/list_{i}",
                title=f"Article {i}",
                raw_content=f"Content {i}",
                published_at=published_at - timedelta(hours=i),
            )

        items = item_service.get_items_by_source(test_source.source_id)

        assert len(items) == 3

    def test_get_items_by_source_with_status_filter(self, item_service, test_source):
        """Test filtering items by status."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        # Create items
        item1 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_status_1",
            url="https://example.com/article/status_1",
            title="New Item",
            raw_content="Content",
            published_at=published_at,
        )
        item2 = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_status_2",
            url="https://example.com/article/status_2",
            title="To Be Normalized",
            raw_content="Content",
            published_at=published_at,
        )

        # Update one item's status
        item_service.update_item_status(item2.item_id, "normalized")

        # Filter by status
        new_items = item_service.get_items_by_source(
            test_source.source_id, status="new"
        )
        normalized_items = item_service.get_items_by_source(
            test_source.source_id, status="normalized"
        )

        assert len(new_items) == 1
        assert new_items[0].item_id == item1.item_id
        assert len(normalized_items) == 1
        assert normalized_items[0].item_id == item2.item_id

    def test_get_items_by_source_pagination(self, item_service, test_source):
        """Test pagination of items."""
        published_at = datetime.now(UTC)

        # Create 5 items
        for i in range(5):
            item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_page_{i}",
                url=f"https://example.com/article/page_{i}",
                title=f"Page Article {i}",
                raw_content=f"Content {i}",
                published_at=published_at - timedelta(hours=i),
            )

        # Test limit
        items = item_service.get_items_by_source(test_source.source_id, limit=3)
        assert len(items) == 3

        # Test offset
        items_offset = item_service.get_items_by_source(
            test_source.source_id, limit=3, offset=3
        )
        assert len(items_offset) == 2

    def test_get_items_by_source_empty(self, item_service):
        """Test listing items for source with no items."""
        items = item_service.get_items_by_source("src_nonexistent")
        assert items == []


class TestUpdateItemStatus:
    """Tests for update_item_status method."""

    def test_update_item_status(self, item_service, test_source):
        """Test updating item status."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        item = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_update_status",
            url="https://example.com/article/update_status",
            title="Update Status Test",
            raw_content="Content",
            published_at=published_at,
        )

        updated = item_service.update_item_status(item.item_id, "normalized")

        assert updated is not None
        assert updated.status == ItemStatus.NORMALIZED

    def test_update_item_status_with_quality_metrics(self, item_service, test_source):
        """Test updating item status with quality metrics."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        item = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_quality",
            url="https://example.com/article/quality",
            title="Quality Metrics Test",
            raw_content="Content",
            published_at=published_at,
        )

        quality_metrics = {
            "meta_completeness": 0.95,
            "content_completeness": 0.85,
        }

        updated = item_service.update_item_status(
            item.item_id, "normalized", quality_metrics=quality_metrics
        )

        assert updated is not None
        assert updated.status == ItemStatus.NORMALIZED
        assert updated.meta_completeness == 0.95
        assert updated.content_completeness == 0.85

    def test_update_item_status_partial_metrics(self, item_service, test_source):
        """Test updating item status with partial quality metrics."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        item = item_service.create_item(
            source_id=test_source.source_id,
            external_id="ext_partial",
            url="https://example.com/article/partial",
            title="Partial Metrics Test",
            raw_content="Content",
            published_at=published_at,
        )

        quality_metrics = {
            "meta_completeness": 0.90,
        }

        updated = item_service.update_item_status(
            item.item_id, "normalized", quality_metrics=quality_metrics
        )

        assert updated is not None
        assert updated.meta_completeness == 0.90
        assert updated.content_completeness is None

    def test_update_item_status_nonexistent(self, item_service):
        """Test updating a nonexistent item."""
        updated = item_service.update_item_status("item_nonexistent", "normalized")
        assert updated is None

    def test_update_item_status_all_statuses(self, item_service, test_source):
        """Test updating to all possible statuses."""
        published_at = datetime.now(UTC) - timedelta(hours=1)

        statuses = ["NEW", "NORMALIZED", "MAPPED", "REJECTED"]

        for status in statuses:
            item = item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_status_{status}",
                url=f"https://example.com/article/status_{status}",
                title=f"Status {status}",
                raw_content="Content",
                published_at=published_at,
            )

            updated = item_service.update_item_status(item.item_id, status)
            assert updated.status == ItemStatus(status)


class TestGetPendingItems:
    """Tests for get_pending_items method."""

    def test_get_pending_items(self, item_service, test_source):
        """Test getting items pending normalization."""
        published_at = datetime.now(UTC)

        # Create multiple items
        for i in range(5):
            item = item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_pending_{i}",
                url=f"https://example.com/article/pending_{i}",
                title=f"Pending Article {i}",
                raw_content=f"Content {i}",
                published_at=published_at - timedelta(hours=i),
            )

            # Update some items to normalized
            if i < 2:
                item_service.update_item_status(item.item_id, "normalized")

        pending = item_service.get_pending_items()

        assert len(pending) == 3
        for item in pending:
            assert item.status == ItemStatus.NEW

    def test_get_pending_items_order(self, item_service, test_source):
        """Test that pending items are ordered by fetched_at ascending."""
        published_at = datetime.now(UTC)

        # Create items (they will be fetched in this order)
        items = []
        for i in range(3):
            item = item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_order_{i}",
                url=f"https://example.com/article/order_{i}",
                title=f"Order Article {i}",
                raw_content=f"Content {i}",
                published_at=published_at - timedelta(hours=i),
            )
            items.append(item)

        pending = item_service.get_pending_items()

        # Should be ordered by fetched_at ascending (oldest first)
        assert pending[0].item_id == items[0].item_id
        assert pending[1].item_id == items[1].item_id
        assert pending[2].item_id == items[2].item_id

    def test_get_pending_items_limit(self, item_service, test_source):
        """Test limit parameter for pending items."""
        published_at = datetime.now(UTC)

        # Create 10 items
        for i in range(10):
            item_service.create_item(
                source_id=test_source.source_id,
                external_id=f"ext_limit_{i}",
                url=f"https://example.com/article/limit_{i}",
                title=f"Limit Article {i}",
                raw_content=f"Content {i}",
                published_at=published_at - timedelta(hours=i),
            )

        pending = item_service.get_pending_items(limit=5)
        assert len(pending) == 5

    def test_get_pending_items_empty(self, item_service):
        """Test getting pending items when none exist."""
        pending = item_service.get_pending_items()
        assert pending == []
