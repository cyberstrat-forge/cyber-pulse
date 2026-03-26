"""Tests for quality check tasks."""

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cyberpulse.models import Content, Item, ItemStatus, Source, SourceStatus, SourceTier


@pytest.fixture
def test_source():
    """Create a test source."""
    source = Source(
        source_id="src_qual001",
        name="Test Source for Quality",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
        config={"feed_url": "https://example.com/feed.xml"},
        total_contents=0,
    )
    return source


@pytest.fixture
def test_item(test_source):
    """Create a test item for quality check."""
    # Use naive datetime to match how database stores it
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    item = Item(
        item_id="item_qual001",
        source_id=test_source.source_id,
        external_id="ext_qual001",
        url="https://example.com/article/quality-test",
        title="Test Article for Quality Check",
        raw_content="<html><body><p>This is sufficient content for quality check.</p></body></html>",
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        content_hash=hashlib.md5(b"test_content").hexdigest(),
        status=ItemStatus.NORMALIZED,
        raw_metadata={"author": "Test Author"},
    )
    # Set the relationship after creation
    item.source = test_source
    return item


@pytest.fixture
def valid_normalization_result():
    """Create a valid normalization result."""
    return {
        "normalized_title": "Test Article for Quality Check",
        "normalized_body": "This is sufficient content for quality check. " * 20,
        "canonical_hash": hashlib.md5(b"normalized_content").hexdigest(),
        "language": "en",
        "word_count": 100,
        "extraction_method": "trafilatura",
    }


class TestQualityCheckItem:
    """Tests for quality_check_item task."""

    def test_quality_check_pass(self, test_item, valid_normalization_result):
        """Test quality check passes for valid item."""
        mock_db = MagicMock()

        # Mock item query
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item

        # Mock content query (returns None for new content)
        mock_content_query = MagicMock()
        mock_content_query.filter.return_value = mock_content_query
        mock_content_query.first.return_value = None

        def query_side_effect(model):
            if model == Item:
                return mock_item_query
            return mock_content_query

        mock_db.query.side_effect = query_side_effect

        # Track created content
        created_content = []
        mock_db.add.side_effect = lambda obj: created_content.append(obj)

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            quality_check_item(
                item_id=test_item.item_id,
                **valid_normalization_result
            )

        # Verify item status was updated to MAPPED
        assert test_item.status == ItemStatus.MAPPED

        # Verify quality metrics were set
        assert test_item.meta_completeness is not None
        assert test_item.content_completeness is not None

        # Verify commit was called
        mock_db.commit.assert_called()

        # Verify content was created
        assert len(created_content) == 1
        content = created_content[0]
        assert isinstance(content, Content)

    def test_quality_check_reject(self, test_item):
        """Test quality check rejects invalid item."""
        # Create an item with empty body that will be rejected
        test_item.title = "Abc"  # Too short

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            quality_check_item(
                item_id=test_item.item_id,
                normalized_title="Abc",
                normalized_body="",  # Empty body - will be rejected
                canonical_hash=hashlib.md5(b"reject").hexdigest(),
                language="en",
                word_count=0,
                extraction_method="raw",
            )

        # Verify item was rejected
        assert test_item.status == ItemStatus.REJECTED
        assert test_item.raw_metadata.get("rejection_reason") is not None

    def test_quality_check_item_not_found(self):
        """Test quality check with non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            # Should not raise, just log error
            quality_check_item(
                item_id="item_nonexistent",
                normalized_title="Test",
                normalized_body="Test body",
                canonical_hash="hash123",
            )

        # Should not try to commit
        mock_db.commit.assert_not_called()

    def test_quality_check_updates_source_stats(self, test_item, valid_normalization_result):
        """Test that passing quality check updates source statistics."""
        mock_db = MagicMock()

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item

        mock_content_query = MagicMock()
        mock_content_query.filter.return_value = mock_content_query
        mock_content_query.first.return_value = None

        def query_side_effect(model):
            if model == Item:
                return mock_item_query
            return mock_content_query

        mock_db.query.side_effect = query_side_effect

        initial_total = test_item.source.total_contents or 0

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            quality_check_item(
                item_id=test_item.item_id,
                **valid_normalization_result
            )

        # Verify source stats updated
        assert test_item.source.total_contents == initial_total + 1

    def test_quality_check_handles_duplicate_content(self, test_item, valid_normalization_result):
        """Test that duplicate content is handled correctly."""
        # Create existing content
        existing_content = Content(
            content_id="cnt_existing",
            canonical_hash=valid_normalization_result["canonical_hash"],
            normalized_title="Existing Content",
            normalized_body="Existing body",
            source_count=1,
        )

        mock_db = MagicMock()

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item

        mock_content_query = MagicMock()
        mock_content_query.filter.return_value = mock_content_query
        mock_content_query.first.return_value = existing_content  # Return existing content

        def query_side_effect(model):
            if model == Item:
                return mock_item_query
            return mock_content_query

        mock_db.query.side_effect = query_side_effect

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            quality_check_item(
                item_id=test_item.item_id,
                **valid_normalization_result
            )

        # Content should be updated, not created
        assert existing_content.source_count == 2

        # Item should be linked to existing content
        assert test_item.content_id == existing_content.content_id

    def test_quality_check_failure(self, test_item, valid_normalization_result):
        """Test quality check failure handling."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.quality_tasks.QualityGateService"
            ) as MockQGService:
                mock_service = MagicMock()
                mock_service.check.side_effect = RuntimeError("Quality check failed")
                MockQGService.return_value = mock_service

                from cyberpulse.tasks.quality_tasks import quality_check_item

                with pytest.raises(RuntimeError, match="Quality check failed"):
                    quality_check_item(
                        item_id=test_item.item_id,
                        **valid_normalization_result
                    )

        # Verify rollback was called
        mock_db.rollback.assert_called()


class TestRecheckItem:
    """Tests for recheck_item task."""

    def test_recheck_item_success(self, test_source):
        """Test successful item recheck."""
        # Create a rejected item
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        test_item = Item(
            item_id="item_recheck",
            source_id=test_source.source_id,
            external_id="ext_recheck",
            url="https://example.com/article/recheck",
            title="Article to Recheck",
            raw_content="Content to recheck",
            published_at=now,
            fetched_at=now,
            content_hash=hashlib.md5(b"recheck").hexdigest(),
            status=ItemStatus.REJECTED,
            raw_metadata={"rejection_reason": "Test rejection"},
        )

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.quality_tasks.broker.get_actor"
            ) as mock_get_actor:
                mock_normalize_actor = MagicMock()
                mock_get_actor.return_value = mock_normalize_actor

                from cyberpulse.tasks.quality_tasks import recheck_item

                recheck_item(test_item.item_id)

        # Item status should be reset to NEW
        assert test_item.status == ItemStatus.NEW

        # Normalize actor should have been called
        mock_normalize_actor.send.assert_called_once_with(test_item.item_id)

    def test_recheck_item_not_found(self):
        """Test recheck with non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import recheck_item

            # Should not raise, just log error
            recheck_item("item_nonexistent")


class TestFetchFullContent:
    """Tests for fetch_full_content task."""

    def test_fetch_full_content_success(self, test_source):
        """Test successful full content fetch."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        test_item = Item(
            item_id="item_fetch001",
            source_id=test_source.source_id,
            external_id="ext_fetch001",
            url="https://example.com/article/full",
            title="Article to Fetch",
            raw_content="Short summary",
            published_at=now,
            fetched_at=now,
            content_hash=hashlib.md5(b"fetch").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        test_item.source = test_source

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item

        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source

        def query_side_effect(model):
            if model == Item:
                return mock_item_query
            elif model == Source:
                return mock_source_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.quality_tasks.FullContentFetchService"
            ) as MockFetchService:
                mock_fetch_service = MagicMock()
                mock_result = MagicMock()
                mock_result.success = True
                mock_result.content = "Full article content retrieved from URL"
                mock_fetch_service.fetch_with_retry.return_value = mock_result

                # Mock asyncio.run
                with patch("asyncio.run", return_value=mock_result):
                    with patch(
                        "cyberpulse.tasks.quality_tasks.broker.get_actor"
                    ) as mock_get_actor:
                        mock_normalize_actor = MagicMock()
                        mock_get_actor.return_value = mock_normalize_actor

                        from cyberpulse.tasks.quality_tasks import fetch_full_content

                        fetch_full_content(test_item.item_id)

        # Verify item was updated
        assert test_item.full_fetch_attempted is True
        assert test_item.full_fetch_succeeded is True

        # Verify source stats updated
        assert test_source.full_fetch_success_count == 1

    def test_fetch_full_content_failure(self, test_source):
        """Test failed full content fetch."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        test_item = Item(
            item_id="item_fetch002",
            source_id=test_source.source_id,
            external_id="ext_fetch002",
            url="https://example.com/article/fail",
            title="Article Fetch Fail",
            raw_content="Short summary",
            published_at=now,
            fetched_at=now,
            content_hash=hashlib.md5(b"fail").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )
        test_item.source = test_source

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item

        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source

        def query_side_effect(model):
            if model == Item:
                return mock_item_query
            elif model == Source:
                return mock_source_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.error = "Connection timeout"
            mock_result.content = ""

            with patch("asyncio.run", return_value=mock_result):
                from cyberpulse.tasks.quality_tasks import fetch_full_content

                fetch_full_content(test_item.item_id)

        # Verify item was updated
        assert test_item.full_fetch_attempted is True
        assert test_item.full_fetch_succeeded is False

        # Verify source stats updated
        assert test_source.full_fetch_failure_count == 1

    def test_fetch_full_content_no_url(self, test_source):
        """Test fetch with no URL."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        test_item = Item(
            item_id="item_fetch003",
            source_id=test_source.source_id,
            external_id="ext_fetch003",
            url=None,  # No URL
            title="Article No URL",
            raw_content="Content",
            published_at=now,
            fetched_at=now,
            content_hash=hashlib.md5(b"nourl").hexdigest(),
            status=ItemStatus.NORMALIZED,
        )

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import fetch_full_content

            fetch_full_content(test_item.item_id)

        # Should not attempt fetch
        assert test_item.full_fetch_attempted is True

    def test_fetch_full_content_item_not_found(self):
        """Test fetch with non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import fetch_full_content

            # Should not raise, just log error
            fetch_full_content("item_nonexistent")