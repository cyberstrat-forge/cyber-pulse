"""Tests for ContentService."""

import pytest
from datetime import datetime, timedelta, timezone
import hashlib

from cyberpulse.models import Content, ContentStatus, Item, ItemStatus, Source, SourceTier, SourceStatus
from cyberpulse.services import ContentService


@pytest.fixture
def content_service(db_session):
    """Create a ContentService instance."""
    return ContentService(db_session)


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


@pytest.fixture
def test_item(db_session, test_source):
    """Create a test item."""
    item = Item(
        item_id="item_test01",
        source_id=test_source.source_id,
        external_id="ext_001",
        url="https://example.com/article/001",
        title="Test Article",
        raw_content="Test content",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        fetched_at=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(b"test content").hexdigest(),
        status=ItemStatus.NORMALIZED,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def make_canonical_hash(content: str) -> str:
    """Generate a canonical hash for testing."""
    return hashlib.sha256(content.encode()).hexdigest()


class TestGenerateContentId:
    """Tests for generate_content_id method."""

    def test_generate_content_id_format(self, content_service):
        """Test that content ID follows the expected format."""
        content_id = content_service.generate_content_id()

        # Format: cnt_{YYYYMMDDHHMMSS}_{uuid8}
        assert content_id.startswith("cnt_")
        parts = content_id.split("_")
        assert len(parts) == 3
        assert len(parts[1]) == 14  # YYYYMMDDHHMMSS
        assert len(parts[2]) == 8  # uuid8

    def test_generate_content_id_timestamp(self, content_service):
        """Test that timestamp in content ID is valid."""
        content_id = content_service.generate_content_id()
        parts = content_id.split("_")
        timestamp_str = parts[1]

        # Should be parseable as datetime
        parsed = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
        assert parsed is not None

    def test_generate_content_id_uniqueness(self, content_service):
        """Test that generated IDs are unique."""
        id1 = content_service.generate_content_id()
        id2 = content_service.generate_content_id()

        assert id1 != id2


class TestCreateContentNew:
    """Tests for creating new content."""

    def test_create_content_new(self, content_service, test_item):
        """Test creating a new content."""
        canonical_hash = make_canonical_hash("unique content")
        normalized_title = "Normalized Title"
        normalized_body = "Normalized body content"

        content, is_new = content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            item=test_item,
        )

        assert is_new is True
        assert content is not None
        assert content.content_id.startswith("cnt_")
        assert content.canonical_hash == canonical_hash
        assert content.normalized_title == normalized_title
        assert content.normalized_body == normalized_body
        assert content.source_count == 1
        assert content.status == ContentStatus.ACTIVE
        assert content.first_seen_at is not None
        assert content.last_seen_at is not None

    def test_create_content_links_item(self, content_service, test_item):
        """Test that creating content links the item."""
        canonical_hash = make_canonical_hash("linking content")

        content, is_new = content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title="Title",
            normalized_body="Body",
            item=test_item,
        )

        # Refresh item to see the updated content_id
        content_service.db.refresh(test_item)

        assert test_item.content_id == content.content_id


class TestCreateContentDuplicate:
    """Tests for handling duplicate content."""

    def test_create_content_duplicate(self, content_service, test_source, db_session):
        """Test that duplicate content (same canonical_hash) updates existing."""
        canonical_hash = make_canonical_hash("duplicate content")

        # Create first item and content
        item1 = Item(
            item_id="item_dup1",
            source_id=test_source.source_id,
            external_id="ext_dup1",
            url="https://example.com/dup1",
            title="First Item",
            raw_content="Content",
            published_at=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc) - timedelta(hours=1),
            content_hash=hashlib.sha256(b"content1").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        db_session.add(item1)
        db_session.commit()
        db_session.refresh(item1)

        content1, is_new1 = content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title="Original Title",
            normalized_body="Original Body",
            item=item1,
        )

        assert is_new1 is True
        assert content1.source_count == 1

        # Create second item with same canonical_hash
        item2 = Item(
            item_id="item_dup2",
            source_id=test_source.source_id,
            external_id="ext_dup2",
            url="https://example.com/dup2",
            title="Second Item",
            raw_content="Content",
            published_at=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            content_hash=hashlib.sha256(b"content2").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        db_session.add(item2)
        db_session.commit()
        db_session.refresh(item2)

        # This should find the existing content
        content2, is_new2 = content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title="Updated Title",
            normalized_body="Updated Body",
            item=item2,
        )

        assert is_new2 is False
        assert content2.content_id == content1.content_id
        assert content2.source_count == 2

        # Verify last_seen_at was updated
        assert content2.last_seen_at >= content1.last_seen_at

    def test_duplicate_content_links_item(self, content_service, test_source, db_session):
        """Test that duplicate content links the new item to existing content."""
        canonical_hash = make_canonical_hash("link duplicate")

        # Create first item and content
        item1 = Item(
            item_id="item_link1",
            source_id=test_source.source_id,
            external_id="ext_link1",
            url="https://example.com/link1",
            title="First Item",
            raw_content="Content",
            published_at=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            content_hash=hashlib.sha256(b"content").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        db_session.add(item1)
        db_session.commit()
        db_session.refresh(item1)

        content1, _ = content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title="Title",
            normalized_body="Body",
            item=item1,
        )

        # Create second item with same canonical_hash
        item2 = Item(
            item_id="item_link2",
            source_id=test_source.source_id,
            external_id="ext_link2",
            url="https://example.com/link2",
            title="Second Item",
            raw_content="Content",
            published_at=datetime.now(timezone.utc),
            fetched_at=datetime.now(timezone.utc),
            content_hash=hashlib.sha256(b"content2").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        db_session.add(item2)
        db_session.commit()
        db_session.refresh(item2)

        content_service.create_or_get_content(
            canonical_hash=canonical_hash,
            normalized_title="Title",
            normalized_body="Body",
            item=item2,
        )

        # Refresh items
        db_session.refresh(item1)
        db_session.refresh(item2)

        assert item1.content_id == content1.content_id
        assert item2.content_id == content1.content_id


class TestGetContents:
    """Tests for get_contents method."""

    def test_get_contents_with_filters_since(self, content_service, test_source, db_session):
        """Test filtering contents by since timestamp."""
        # Create contents at different times
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for i in range(3):
            item = Item(
                item_id=f"item_filter_{i}",
                source_id=test_source.source_id,
                external_id=f"ext_filter_{i}",
                url=f"https://example.com/filter/{i}",
                title=f"Item {i}",
                raw_content="Content",
                published_at=now - timedelta(hours=i),
                fetched_at=now,
                content_hash=hashlib.sha256(f"content_{i}".encode()).hexdigest(),
                status=ItemStatus.NORMALIZED,
            )
            db_session.add(item)
            db_session.commit()
            db_session.refresh(item)

            content = Content(
                content_id=f"cnt_{i:014d}_abcd{i:04d}",
                canonical_hash=hashlib.sha256(f"hash_{i}".encode()).hexdigest(),
                normalized_title=f"Content {i}",
                normalized_body=f"Body {i}",
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(hours=i),
                source_count=1,
            )
            db_session.add(content)

        db_session.commit()

        # Filter by since
        since = now - timedelta(hours=1.5)
        contents = content_service.get_contents(since=since)

        # Should get only contents with first_seen_at >= since
        assert len(contents) == 2

    def test_get_contents_with_filters_until(self, content_service, test_source, db_session):
        """Test filtering contents by until timestamp."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for i in range(3):
            item = Item(
                item_id=f"item_until_{i}",
                source_id=test_source.source_id,
                external_id=f"ext_until_{i}",
                url=f"https://example.com/until/{i}",
                title=f"Item {i}",
                raw_content="Content",
                published_at=now - timedelta(hours=i),
                fetched_at=now,
                content_hash=hashlib.sha256(f"content_until_{i}".encode()).hexdigest(),
                status=ItemStatus.NORMALIZED,
            )
            db_session.add(item)

            content = Content(
                content_id=f"cnt_{i:014d}_efgh{i:04d}",
                canonical_hash=hashlib.sha256(f"hash_until_{i}".encode()).hexdigest(),
                normalized_title=f"Content {i}",
                normalized_body=f"Body {i}",
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(hours=i),
                source_count=1,
            )
            db_session.add(content)

        db_session.commit()

        # Filter by until
        until = now - timedelta(hours=1.5)
        contents = content_service.get_contents(until=until)

        # Should get only contents with first_seen_at <= until
        assert len(contents) == 1

    def test_get_contents_limit(self, content_service, test_source, db_session):
        """Test limiting results."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for i in range(5):
            content = Content(
                content_id=f"cnt_limit_{i:08d}_abc{i}",
                canonical_hash=hashlib.sha256(f"limit_hash_{i}".encode()).hexdigest(),
                normalized_title=f"Limit Content {i}",
                normalized_body=f"Body {i}",
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(hours=i),
                source_count=1,
            )
            db_session.add(content)

        db_session.commit()

        contents = content_service.get_contents(limit=3)
        assert len(contents) == 3

    def test_get_contents_cursor_pagination(self, content_service, test_source, db_session):
        """Test cursor-based pagination."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Create contents with timestamp-prefixed IDs
        for i in range(5):
            timestamp = (now - timedelta(hours=i)).strftime("%Y%m%d%H%M%S")
            content = Content(
                content_id=f"cnt_{timestamp}_abc{i:04d}",
                canonical_hash=hashlib.sha256(f"cursor_hash_{i}".encode()).hexdigest(),
                normalized_title=f"Cursor Content {i}",
                normalized_body=f"Body {i}",
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(hours=i),
                source_count=1,
            )
            db_session.add(content)

        db_session.commit()

        # Get first page
        first_page = content_service.get_contents(limit=2)

        assert len(first_page) == 2

        # Use last item's ID as cursor
        cursor = first_page[-1].content_id
        second_page = content_service.get_contents(limit=2, cursor=cursor)

        assert len(second_page) == 2
        # Second page should not include first page items
        first_page_ids = [c.content_id for c in first_page]
        second_page_ids = [c.content_id for c in second_page]
        assert not any(id_ in first_page_ids for id_ in second_page_ids)


class TestGetContentById:
    """Tests for get_content_by_id method."""

    def test_get_content_by_id(self, content_service, db_session):
        """Test getting content by ID."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        content = Content(
            content_id="cnt_20260319120000_abc12345",
            canonical_hash=hashlib.sha256(b"get_by_id").hexdigest(),
            normalized_title="Get By ID Content",
            normalized_body="Body content",
            first_seen_at=now,
            last_seen_at=now,
            source_count=1,
        )
        db_session.add(content)
        db_session.commit()

        found = content_service.get_content_by_id("cnt_20260319120000_abc12345")

        assert found is not None
        assert found.content_id == "cnt_20260319120000_abc12345"
        assert found.normalized_title == "Get By ID Content"

    def test_get_content_by_id_not_found(self, content_service):
        """Test getting non-existent content returns None."""
        found = content_service.get_content_by_id("cnt_nonexistent")
        assert found is None


class TestContentStatistics:
    """Tests for get_content_statistics method."""

    def test_content_statistics(self, content_service, test_source, db_session):
        """Test getting content statistics."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Create contents with different source counts
        for i in range(3):
            content = Content(
                content_id=f"cnt_stats_{i:08d}_xyz{i}",
                canonical_hash=hashlib.sha256(f"stats_hash_{i}".encode()).hexdigest(),
                normalized_title=f"Stats Content {i}",
                normalized_body=f"Body {i}",
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(hours=i),
                source_count=i + 1,  # 1, 2, 3
            )
            db_session.add(content)

        db_session.commit()

        stats = content_service.get_content_statistics()

        assert stats is not None
        assert stats["total_contents"] == 3
        assert stats["total_source_references"] == 6  # 1 + 2 + 3

    def test_content_statistics_empty(self, content_service):
        """Test statistics when no contents exist."""
        stats = content_service.get_content_statistics()

        assert stats is not None
        assert stats["total_contents"] == 0
        assert stats["total_source_references"] == 0