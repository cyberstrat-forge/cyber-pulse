"""Tests for quality check tasks."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cyberpulse.models import Item, ItemStatus, Source, SourceStatus, SourceTier


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
    )
    return source


@pytest.fixture
def test_item(test_source):
    """Create a test item for quality check."""
    # Use naive datetime to match how database stores it
    now = datetime.now(UTC).replace(tzinfo=None)
    item = Item(
        item_id="item_qual001",
        source_id=test_source.source_id,
        external_id="ext_qual001",
        url="https://example.com/article/quality-test",
        title="Test Article for Quality Check",
        raw_content="<html><body><p>This is sufficient content for quality check.</p></body></html>",
        published_at=now - timedelta(hours=1),
        fetched_at=now,
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
        mock_db.query.return_value = mock_item_query

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

        # Verify normalized fields were set on item
        assert test_item.normalized_title == valid_normalization_result["normalized_title"]
        assert test_item.normalized_body == valid_normalization_result["normalized_body"]
        assert test_item.canonical_hash == valid_normalization_result["canonical_hash"]

        # Verify commit was called
        mock_db.commit.assert_called()

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
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.quality_tasks import quality_check_item

            quality_check_item(
                item_id=test_item.item_id,
                **valid_normalization_result
            )

        # Verify source stats updated
        assert test_item.source.total_items is not None

    def test_quality_check_handles_duplicate_content(self, test_item, valid_normalization_result):
        """Test that items with same canonical_hash are handled correctly."""
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
                **valid_normalization_result
            )

        # Item should be updated with canonical_hash
        assert test_item.canonical_hash == valid_normalization_result["canonical_hash"]

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
            ) as mock_qg_service:
                mock_service = MagicMock()
                mock_service.check.side_effect = RuntimeError("Quality check failed")
                mock_qg_service.return_value = mock_service

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
        now = datetime.now(UTC).replace(tzinfo=None)
        test_item = Item(
            item_id="item_recheck",
            source_id=test_source.source_id,
            external_id="ext_recheck",
            url="https://example.com/article/recheck",
            title="Article to Recheck",
            raw_content="Content to recheck",
            published_at=now,
            fetched_at=now,
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


class TestPendingFullFetchStatus:
    """Test PENDING_FULL_FETCH status handling."""

    def test_quality_check_sets_pending_full_fetch_for_short_content(
        self, test_source
    ):
        """Test that short content sets PENDING_FULL_FETCH status."""
        # Create item with short content
        now = datetime.now(UTC).replace(tzinfo=None)
        test_item = Item(
            item_id="item_test_001",
            source_id=test_source.source_id,
            external_id="ext_001",
            url="https://example.com/article",
            title="Test Article",
            raw_content="Short content",  # < 100 chars
            published_at=now,
            fetched_at=now,
            status=ItemStatus.NORMALIZED,
        )
        test_item.source = test_source

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.quality_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.full_content_tasks.fetch_full_content.send"
            ) as mock_send:
                from cyberpulse.tasks.quality_tasks import quality_check_item

                quality_check_item(
                    item_id=test_item.item_id,
                    normalized_title="Test Article",
                    normalized_body="Short content",
                    canonical_hash="abc123",
                )

        # Verify status
        assert test_item.status == ItemStatus.PENDING_FULL_FETCH

        # Verify fetch_full_content was triggered
        mock_send.assert_called_once_with(test_item.item_id)

    def test_quality_check_sets_mapped_for_good_content(self, test_source):
        """Test that good content sets MAPPED status."""
        now = datetime.now(UTC).replace(tzinfo=None)
        long_content = (
            "This is a long enough content that should pass the minimum length "
            "check of one hundred characters. Adding more text to ensure we "
            "have sufficient length."
        )
        test_item = Item(
            item_id="item_test_002",
            source_id=test_source.source_id,
            external_id="ext_002",
            url="https://example.com/article2",
            title="Test Article 2",
            raw_content=long_content,
            published_at=now,
            fetched_at=now,
            status=ItemStatus.NORMALIZED,
        )
        test_item.source = test_source

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
                normalized_title="Test Article 2",
                normalized_body=long_content,
                canonical_hash="def456",
            )

        # Verify status
        assert test_item.status == ItemStatus.MAPPED

    def test_quality_check_rejects_no_url_item(self, test_source):
        """Test that item without URL gets REJECTED when content insufficient."""
        now = datetime.now(UTC).replace(tzinfo=None)
        test_item = Item(
            item_id="item_test_003",
            source_id=test_source.source_id,
            external_id="ext_003",
            url=None,  # No URL
            title="Test Article 3",
            raw_content="Short",
            published_at=now,
            fetched_at=now,
            status=ItemStatus.NORMALIZED,
        )
        test_item.source = test_source

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
                normalized_title="Test Article 3",
                normalized_body="Short",
                canonical_hash="ghi789",
            )

        # Verify status
        assert test_item.status == ItemStatus.REJECTED


