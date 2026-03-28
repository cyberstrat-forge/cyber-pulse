"""Tests for full content fetch tasks."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from cyberpulse.models import Item, ItemStatus, Source, SourceStatus, SourceTier


@pytest.fixture
def test_source():
    """Create a test source."""
    source = Source(
        source_id="src_full001",
        name="Test Source for Full Fetch",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
        config={"feed_url": "https://example.com/feed.xml"},
    )
    return source


@pytest.fixture
def test_item(test_source):
    """Create a test item for full content fetch."""
    now = datetime.now(UTC).replace(tzinfo=None)
    item = Item(
        item_id="item_full001",
        source_id=test_source.source_id,
        external_id="ext_full001",
        url="https://example.com/article/full-test",
        title="Article to Fetch Full",
        raw_content="Short summary",
        published_at=now,
        fetched_at=now,
        status=ItemStatus.NORMALIZED,
    )
    item.source = test_source
    return item


class TestFetchFullContentTask:
    """Test cases for fetch_full_content task."""

    def test_task_exists(self):
        """Test that the task is registered."""
        from cyberpulse.tasks.full_content_tasks import fetch_full_content
        assert fetch_full_content is not None

    def test_task_has_max_retries_2(self):
        """Test that task has max_retries=2."""
        from cyberpulse.tasks.full_content_tasks import fetch_full_content
        assert fetch_full_content.options.get("max_retries") == 2

    def test_task_has_max_concurrency_3(self):
        """Test that task has max_concurrency=3 for Jina AI 20 RPM limit."""
        from cyberpulse.tasks.full_content_tasks import fetch_full_content
        assert fetch_full_content.options.get("max_concurrency") == 3

    def test_fetch_full_content_success(self, test_item):
        """Test successful full content fetch."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        # Mock FullContentFetchService result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.content = "Full article content retrieved from URL"
        mock_result.level = "level1"

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.full_content_tasks.FullContentFetchService"
            ) as mock_service_class:
                mock_service = MagicMock()
                mock_service_class.return_value = mock_service

                with patch("asyncio.run", return_value=mock_result):
                    with patch(
                        "cyberpulse.tasks.normalization_tasks.normalize_item.send"
                    ) as mock_send:
                        from cyberpulse.tasks.full_content_tasks import (
                            fetch_full_content,
                        )

                        result = fetch_full_content(test_item.item_id)

        # Verify item was updated
        assert test_item.full_fetch_attempted is True
        assert test_item.full_fetch_succeeded is True
        assert test_item.raw_content == "Full article content retrieved from URL"
        assert test_item.status == ItemStatus.NORMALIZED

        # Verify result
        assert result["success"] is True
        assert result["item_id"] == test_item.item_id

        # Should trigger normalization
        mock_send.assert_called_once_with(test_item.item_id)

    def test_fetch_full_content_failure_sets_rejected(self, test_item):
        """Test that failed fetch sets REJECTED status."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        # Mock FullContentFetchService result - failure
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.content = ""
        mock_result.error = "Connection timeout"

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            with patch("asyncio.run", return_value=mock_result):
                from cyberpulse.tasks.full_content_tasks import fetch_full_content

                result = fetch_full_content(test_item.item_id)

        # Verify item was updated and REJECTED
        assert test_item.full_fetch_attempted is True
        assert test_item.full_fetch_succeeded is False
        assert test_item.status == ItemStatus.REJECTED

        # Verify result
        assert result["success"] is False
        assert result["status"] == "REJECTED"
        assert result["error"] == "Connection timeout"

    def test_fetch_full_content_no_url_sets_rejected(self, test_source):
        """Test that item with no URL is REJECTED."""
        now = datetime.now(UTC).replace(tzinfo=None)
        test_item = Item(
            item_id="item_no_url",
            source_id=test_source.source_id,
            external_id="ext_no_url",
            url=None,  # No URL
            title="Article No URL",
            raw_content="Content",
            published_at=now,
            fetched_at=now,
            status=ItemStatus.NORMALIZED,
        )

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.full_content_tasks import fetch_full_content

            result = fetch_full_content(test_item.item_id)

        # Verify item was REJECTED
        assert test_item.full_fetch_attempted is True
        assert test_item.full_fetch_succeeded is False
        assert test_item.status == ItemStatus.REJECTED

        # Verify result
        assert result["error"] == "No URL"
        assert result["status"] == "REJECTED"

    def test_fetch_full_content_item_not_found(self):
        """Test fetch with non-existent item."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.full_content_tasks import fetch_full_content

            result = fetch_full_content("item_nonexistent")

        # Should return error dict
        assert result["error"] == "Item not found"
        assert result["item_id"] == "item_nonexistent"

    def test_fetch_full_content_already_attempted_skips(self, test_item):
        """Test that already attempted fetch is skipped."""
        test_item.full_fetch_attempted = True

        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.full_content_tasks import fetch_full_content

            result = fetch_full_content(test_item.item_id)

        # Should skip
        assert result["skipped"] is True
        assert result["item_id"] == test_item.item_id

    def test_fetch_full_content_triggers_normalize_on_success(self, test_item):
        """Test that successful fetch triggers normalization."""
        mock_db = MagicMock()
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = test_item
        mock_db.query.return_value = mock_item_query

        # Mock FullContentFetchService result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.content = "Full content"
        mock_result.level = "level2"

        with patch(
            "cyberpulse.tasks.full_content_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.full_content_tasks.FullContentFetchService"
            ) as mock_service_class:
                mock_service = MagicMock()
                mock_service_class.return_value = mock_service

                with patch("asyncio.run", return_value=mock_result):
                    with patch(
                        "cyberpulse.tasks.normalization_tasks.normalize_item.send"
                    ) as mock_send:
                        from cyberpulse.tasks.full_content_tasks import (
                            fetch_full_content,
                        )

                        fetch_full_content(test_item.item_id)

        # Should trigger normalization
        mock_send.assert_called_once_with(test_item.item_id)
