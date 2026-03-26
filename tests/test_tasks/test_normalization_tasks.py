"""Tests for normalization tasks."""

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cyberpulse.models import Item, ItemStatus, Source, SourceStatus, SourceTier


@pytest.fixture
def test_source():
    """Create a test source."""
    source = Source(
        source_id="src_norm001",
        name="Test Source for Normalization",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
        config={"feed_url": "https://example.com/feed.xml"},
    )
    return source


@pytest.fixture
def test_item(test_source):
    """Create a test item for normalization."""
    item = Item(
        item_id="item_norm001",
        source_id=test_source.source_id,
        external_id="ext_norm001",
        url="https://example.com/article/normalization-test",
        title="Test Article for Normalization",
        raw_content="<html><body><p>This is test content for normalization.</p></body></html>",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        fetched_at=datetime.now(timezone.utc),
        status=ItemStatus.NEW,
        raw_metadata={"author": "Test Author", "tags": ["test"]},
    )
    return item


class TestNormalizeItem:
    """Tests for normalize_item task."""

    def test_normalize_item_success(self, test_item):
        """Test successful item normalization."""
        mock_db = MagicMock()

        # Mock query for item lookup (with options for joinedload)
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query  # for .options(joinedload(...))
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.normalization_tasks.broker.get_actor"
            ) as mock_get_actor:
                mock_quality_actor = MagicMock()
                mock_get_actor.return_value = mock_quality_actor

                from cyberpulse.tasks.normalization_tasks import normalize_item

                normalize_item(test_item.item_id)

        # Verify item status was updated
        assert test_item.status == ItemStatus.NORMALIZED

        # Verify commit was called
        mock_db.commit.assert_called()

        # Verify quality check was queued
        mock_get_actor.assert_called_once_with("quality_check_item")
        mock_quality_actor.send.assert_called_once()

        # Verify normalization result was passed
        call_kwargs = mock_quality_actor.send.call_args[1]
        assert call_kwargs["item_id"] == test_item.item_id
        assert "normalized_title" in call_kwargs
        assert "normalized_body" in call_kwargs
        assert "canonical_hash" in call_kwargs

    def test_normalize_item_not_found(self):
        """Test normalization with non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.normalization_tasks import normalize_item

            # Should not raise, just log error
            normalize_item("item_nonexistent")

        # Should not try to commit
        mock_db.commit.assert_not_called()

    def test_normalize_item_with_empty_content(self, test_item):
        """Test normalization with empty raw content."""
        test_item.raw_content = ""

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.normalization_tasks.broker.get_actor"
            ) as mock_get_actor:
                mock_quality_actor = MagicMock()
                mock_get_actor.return_value = mock_quality_actor

                from cyberpulse.tasks.normalization_tasks import normalize_item

                normalize_item(test_item.item_id)

        # Item should still be processed
        assert test_item.status == ItemStatus.NORMALIZED

    def test_normalize_item_failure(self, test_item):
        """Test normalization failure handling."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.normalization_tasks.NormalizationService"
            ) as MockNormService:
                mock_service = MagicMock()
                mock_service.normalize.side_effect = ValueError("Invalid content")
                MockNormService.return_value = mock_service

                from cyberpulse.tasks.normalization_tasks import normalize_item

                with pytest.raises(ValueError, match="Invalid content"):
                    normalize_item(test_item.item_id)

        # Verify rollback was called
        mock_db.rollback.assert_called()


class TestNormalizeItemWithResult:
    """Tests for normalize_item_with_result task."""

    def test_normalize_item_with_result_success(self, test_item):
        """Test successful normalization with result return."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.normalization_tasks import normalize_item_with_result

            result = normalize_item_with_result(test_item.item_id)

        assert result["item_id"] == test_item.item_id
        assert "normalized_title" in result
        assert "normalized_body" in result
        assert "canonical_hash" in result

        assert test_item.status == ItemStatus.NORMALIZED

    def test_normalize_item_with_result_not_found(self):
        """Test normalization with result for non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.normalization_tasks import normalize_item_with_result

            result = normalize_item_with_result("item_nonexistent")

        assert "error" in result
        assert result["item_id"] == "item_nonexistent"

    def test_normalize_item_with_result_failure(self, test_item):
        """Test normalization with result failure for expected errors."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.normalization_tasks.NormalizationService"
            ) as MockNormService:
                mock_service = MagicMock()
                # ValueError is an expected error, returns error dict
                mock_service.normalize.side_effect = ValueError("Invalid content")
                MockNormService.return_value = mock_service

                from cyberpulse.tasks.normalization_tasks import normalize_item_with_result

                result = normalize_item_with_result(test_item.item_id)

        assert "error" in result
        assert "Invalid content" in result["error"]

    def test_normalize_item_with_result_unexpected_error_reraises(self, test_item):
        """Test that unexpected errors are re-raised, not returned as error dict."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.options.return_value = mock_item_query
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.normalization_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.normalization_tasks.NormalizationService"
            ) as MockNormService:
                mock_service = MagicMock()
                # RuntimeError is unexpected, should re-raise
                mock_service.normalize.side_effect = RuntimeError("Processing error")
                MockNormService.return_value = mock_service

                from cyberpulse.tasks.normalization_tasks import normalize_item_with_result

                with pytest.raises(RuntimeError, match="Processing error"):
                    normalize_item_with_result(test_item.item_id)

        # Verify rollback was called
        mock_db.rollback.assert_called()