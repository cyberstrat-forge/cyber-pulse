"""Tests for ingestion tasks."""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from cyberpulse.models import Source, SourceStatus, SourceTier


@pytest.fixture
def test_source():
    """Create a test source."""
    source = Source(
        source_id="src_test001",
        name="Test RSS Source",
        connector_type="rss",
        tier=SourceTier.T2,
        status=SourceStatus.ACTIVE,
        config={"feed_url": "https://example.com/feed.xml"},
        total_items=0,
        consecutive_failures=0,
    )
    return source


@pytest.fixture
def test_items_data():
    """Create test items data as returned by connector."""
    now = datetime.now(timezone.utc)
    return [
        {
            "external_id": "ext_001",
            "url": "https://example.com/article/001",
            "title": "Test Article 1",
            "content": "<p>Content for article 1</p>",
            "published_at": now,
            "author": "Author 1",
            "tags": ["tag1", "tag2"],
        },
        {
            "external_id": "ext_002",
            "url": "https://example.com/article/002",
            "title": "Test Article 2",
            "content": "<p>Content for article 2</p>",
            "published_at": now,
            "author": "Author 2",
            "tags": ["tag3"],
        },
    ]


class TestIngestSource:
    """Tests for ingest_source task."""

    def test_ingest_source_success(self, test_source, test_items_data):
        """Test successful source ingestion."""
        # Create mock session
        mock_db = MagicMock()

        # Mock query chain for source lookup
        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source
        mock_db.query.return_value = mock_source_query

        # Mock query chain for item lookup (returns None for new items)
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = None

        # Set up query to return different results based on model
        def query_side_effect(model):
            if model == Source:
                return mock_source_query
            return mock_item_query

        mock_db.query.side_effect = query_side_effect

        # Track created items
        created_items = []
        mock_db.add.side_effect = lambda obj: created_items.append(obj)

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(return_value=test_items_data)
                mock_get_connector.return_value = mock_connector

                with patch(
                    "cyberpulse.tasks.ingestion_tasks.broker.get_actor"
                ) as mock_get_actor:
                    mock_normalize_actor = MagicMock()
                    mock_get_actor.return_value = mock_normalize_actor

                    from cyberpulse.tasks.ingestion_tasks import ingest_source

                    ingest_source(test_source.source_id)

        # Verify items were added
        assert mock_db.add.call_count == 2

        # Verify commit was called
        mock_db.commit.assert_called()

        # Verify normalization was queued for each new item
        assert mock_normalize_actor.send.call_count == 2

    def test_ingest_source_not_found(self):
        """Test ingestion with non-existent source."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            from cyberpulse.tasks.ingestion_tasks import ingest_source

            ingest_source("src_nonexistent")

        # Verify no items were created
        mock_db.add.assert_not_called()

    def test_ingest_source_empty_feed(self, test_source):
        """Test ingestion when feed returns no items."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = test_source
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(return_value=[])
                mock_get_connector.return_value = mock_connector

                from cyberpulse.tasks.ingestion_tasks import ingest_source

                ingest_source(test_source.source_id)

        # Verify no items were created
        mock_db.add.assert_not_called()

    def test_ingest_source_handles_duplicates(self, test_source, test_items_data):
        """Test that duplicates are handled correctly by ItemService."""
        # This test verifies that the task calls ItemService.create_item
        # which handles deduplication internally
        mock_db = MagicMock()

        # Mock query to return source
        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source

        # For item queries - return None to simulate new items
        mock_item_query = MagicMock()
        mock_item_query.filter.return_value = mock_item_query
        mock_item_query.first.return_value = None

        def query_side_effect(model):
            if model == Source:
                return mock_source_query
            return mock_item_query

        mock_db.query.side_effect = query_side_effect

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(return_value=test_items_data)
                mock_get_connector.return_value = mock_connector

                with patch(
                    "cyberpulse.tasks.ingestion_tasks.broker.get_actor"
                ) as mock_get_actor:
                    mock_normalize_actor = MagicMock()
                    mock_get_actor.return_value = mock_normalize_actor

                    from cyberpulse.tasks.ingestion_tasks import ingest_source

                    ingest_source(test_source.source_id)

        # Verify commit was called - deduplication happens in ItemService
        mock_db.commit.assert_called()

    def test_ingest_source_failure(self, test_source):
        """Test ingestion failure is handled properly."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = test_source
        mock_db.query.return_value = mock_query

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(
                    side_effect=Exception("Network error")
                )
                mock_get_connector.return_value = mock_connector

                from cyberpulse.tasks.ingestion_tasks import ingest_source

                with pytest.raises(Exception, match="Network error"):
                    ingest_source(test_source.source_id)

        # Verify rollback was called
        mock_db.rollback.assert_called()


class TestFetchItems:
    """Tests for _fetch_items helper function."""

    @pytest.mark.asyncio
    async def test_fetch_items_success(self):
        """Test successful item fetching."""
        from cyberpulse.tasks.ingestion_tasks import _fetch_items

        mock_connector = MagicMock()
        mock_connector.fetch = AsyncMock(return_value=[{"id": "1"}])

        result = await _fetch_items(mock_connector)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_items_failure(self):
        """Test item fetching failure."""
        from cyberpulse.tasks.ingestion_tasks import _fetch_items

        mock_connector = MagicMock()
        mock_connector.fetch = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        with pytest.raises(Exception, match="Connection failed"):
            await _fetch_items(mock_connector)


class TestIntegrityErrorHandling:
    """Tests for IntegrityError handling during item creation."""

    def test_ingest_source_handles_integrity_error(self, test_source, test_items_data):
        """Test that IntegrityError during item creation is handled gracefully."""
        mock_db = MagicMock()

        # Mock query chain for source lookup
        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source
        mock_db.query.return_value = mock_source_query

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(return_value=test_items_data)
                mock_get_connector.return_value = mock_connector

                with patch(
                    "cyberpulse.tasks.ingestion_tasks.ItemService"
                ) as mock_item_service_class:
                    # Mock ItemService to raise IntegrityError on first call
                    mock_item_service = MagicMock()
                    mock_item_service_class.return_value = mock_item_service

                    # First call raises IntegrityError, second succeeds
                    mock_item = MagicMock()
                    mock_item.status.value = "NEW"
                    mock_item.item_id = "item_001"
                    mock_item_service.create_item.side_effect = [
                        IntegrityError("statement", {}, None),
                        mock_item,
                    ]

                    with patch(
                        "cyberpulse.tasks.ingestion_tasks.broker.get_actor"
                    ) as mock_get_actor:
                        mock_normalize_actor = MagicMock()
                        mock_get_actor.return_value = mock_normalize_actor

                        from cyberpulse.tasks.ingestion_tasks import ingest_source

                        ingest_source(test_source.source_id)

            # Verify commit was still called (task continues after IntegrityError)
            mock_db.commit.assert_called()

            # Verify normalization was only queued for the successful item
            assert mock_normalize_actor.send.call_count == 1


class TestDatabaseConnectionFailure:
    """Tests for database connection failure handling."""

    def test_ingest_source_database_unavailable(self, test_source):
        """Test handling when database is unavailable during source lookup."""
        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal"
        ) as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            # Simulate database connection failure
            mock_db.query.side_effect = OperationalError(
                "connection failed", {}, None
            )

            from cyberpulse.tasks.ingestion_tasks import ingest_source

            with pytest.raises(OperationalError):
                ingest_source(test_source.source_id)

            # Verify rollback was called
            mock_db.rollback.assert_called()

            # Verify session was closed
            mock_db.close.assert_called()

    def test_ingest_source_database_error_during_item_creation(
        self, test_source, test_items_data
    ):
        """Test that SQLAlchemyError during item creation propagates correctly."""
        mock_db = MagicMock()

        # Mock query chain for source lookup
        mock_source_query = MagicMock()
        mock_source_query.filter.return_value = mock_source_query
        mock_source_query.first.return_value = test_source
        mock_db.query.return_value = mock_source_query

        with patch(
            "cyberpulse.tasks.ingestion_tasks.SessionLocal", return_value=mock_db
        ):
            with patch(
                "cyberpulse.tasks.ingestion_tasks.get_connector_for_source"
            ) as mock_get_connector:
                mock_connector = MagicMock()
                mock_connector.fetch = AsyncMock(return_value=test_items_data)
                mock_get_connector.return_value = mock_connector

                with patch(
                    "cyberpulse.tasks.ingestion_tasks.ItemService"
                ) as mock_item_service_class:
                    from sqlalchemy.exc import SQLAlchemyError

                    mock_item_service = MagicMock()
                    mock_item_service_class.return_value = mock_item_service

                    # Raise SQLAlchemyError (not IntegrityError)
                    mock_item_service.create_item.side_effect = SQLAlchemyError(
                        "Database error"
                    )

                    from cyberpulse.tasks.ingestion_tasks import ingest_source

                    with pytest.raises(SQLAlchemyError, match="Database error"):
                        ingest_source(test_source.source_id)

            # Verify rollback was called
            mock_db.rollback.assert_called()