"""Tests for RSS Connector."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services import ConnectorError, RSSConnector


class MockFeedEntry(dict):
    """Mock feed entry that supports both dict and attribute access."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class TestRSSConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid(self):
        """Test validation passes with valid config."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
        assert connector.validate_config() is True

    def test_validate_config_missing_feed_url(self):
        """Test validation fails when feed_url is missing."""
        connector = RSSConnector({})
        with pytest.raises(ValueError, match="requires 'feed_url'"):
            connector.validate_config()

    def test_validate_config_empty_feed_url(self):
        """Test validation fails when feed_url is empty."""
        connector = RSSConnector({"feed_url": ""})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_feed_url_not_string(self):
        """Test validation fails when feed_url is not a string."""
        connector = RSSConnector({"feed_url": 123})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()


class TestRSSConnectorFetch:
    """Tests for fetch method."""

    @pytest.fixture
    def mock_feed(self):
        """Create a mock RSS feed entry."""
        return MockFeedEntry(
            guid="guid-123",
            link="https://example.com/article/123",
            title="Test Article",
            published_parsed=time.struct_time(
                (2024, 1, 15, 10, 30, 0, 0, 15, 0)
            ),
            summary="This is the summary content",
            content=[],
        )

    @pytest.fixture
    def mock_feedparser_result(self, mock_feed):
        """Create a mock feedparser result."""
        result = {
            "entries": [mock_feed],
            "bozo": False,
        }
        return result

    def _create_mock_response(self, content: bytes = b""):
        """Create a mock httpx response."""
        mock_response = MagicMock()
        mock_response.content = content
        mock_response.url = "https://example.com/feed.xml"
        mock_response.raise_for_status = MagicMock()
        return mock_response

    @pytest.mark.asyncio
    async def test_fetch_success(self, mock_feedparser_result):
        """Test successful fetch returns items."""
        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feedparser_result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                result = await connector.fetch()

        items = result.items
        assert len(items) == 1
        assert items[0]["external_id"] == "guid-123"
        assert items[0]["url"] == "https://example.com/article/123"
        assert items[0]["title"] == "Test Article"
        assert items[0]["content"] == "This is the summary content"
        assert items[0]["author"] == ""
        assert items[0]["tags"] == []

    @pytest.mark.asyncio
    async def test_fetch_uses_link_as_external_id(self):
        """Test that link is used as external_id when guid is missing."""
        entry = MockFeedEntry(
            guid=None,
            id=None,
            link="https://example.com/article/456",
            title="Article without guid",
            published_parsed=time.struct_time(
                (2024, 1, 15, 10, 30, 0, 0, 15, 0)
            ),
            summary="Content here",
            content=[],
        )

        result = {
            "entries": [entry],
            "bozo": False,
        }

        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                fetch_result = await connector.fetch()

        items = fetch_result.items
        assert len(items) == 1
        assert items[0]["external_id"] == "https://example.com/article/456"

    @pytest.mark.asyncio
    async def test_fetch_limits_to_max_items(self):
        """Test that fetch limits results to MAX_ITEMS."""
        entries = []
        for i in range(60):
            entry = MockFeedEntry(
                guid=f"guid-{i}",
                link=f"https://example.com/article/{i}",
                title=f"Article {i}",
                published_parsed=time.struct_time(
                    (2024, 1, 15, 10, 30, 0, 0, 15, 0)
                ),
                summary=f"Content {i}",
                content=[],
            )
            entries.append(entry)

        result = {
            "entries": entries,
            "bozo": False,
        }

        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                fetch_result = await connector.fetch()

        assert len(fetch_result.items) == RSSConnector.MAX_ITEMS

    @pytest.mark.asyncio
    async def test_fetch_skips_entries_without_url(self):
        """Test that entries without URL are skipped."""
        entry_no_link = MockFeedEntry(
            guid="no-link-guid",
            link=None,
            title="No Link",
        )

        entry_with_link = MockFeedEntry(
            guid="with-link-guid",
            link="https://example.com/article",
            title="Has Link",
            published_parsed=time.struct_time(
                (2024, 1, 15, 10, 30, 0, 0, 15, 0)
            ),
            summary="Content",
            content=[],
        )

        result = {
            "entries": [entry_no_link, entry_with_link],
            "bozo": False,
        }

        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                fetch_result = await connector.fetch()

        items = fetch_result.items
        assert len(items) == 1
        assert items[0]["external_id"] == "with-link-guid"

    @pytest.mark.asyncio
    async def test_fetch_handles_bozo_feed(self):
        """Test that bozo feeds are still processed."""
        entry = MockFeedEntry(
            guid="bozo-guid",
            link="https://example.com/article",
            title="Bozo Article",
            published_parsed=time.struct_time(
                (2024, 1, 15, 10, 30, 0, 0, 15, 0)
            ),
            summary="Content",
            content=[],
        )

        result = {
            "entries": [entry],
            "bozo": True,
            "bozo_exception": Exception("Malformed XML"),
        }

        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                fetch_result = await connector.fetch()

        items = fetch_result.items
        assert len(items) == 1
        assert items[0]["external_id"] == "bozo-guid"

    @pytest.mark.asyncio
    async def test_fetch_raises_connector_error_on_http_error(self):
        """Test that fetch raises ConnectorError on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=http_error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
            with pytest.raises(ConnectorError, match="Failed to fetch RSS feed"):
                await connector.fetch()

    @pytest.mark.asyncio
    async def test_fetch_raises_connector_error_on_request_error(self):
        """Test that fetch raises ConnectorError on request error."""
        request_error = httpx.RequestError("Connection refused")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=request_error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
            with pytest.raises(ConnectorError, match="Failed to fetch RSS feed"):
                await connector.fetch()

    @pytest.mark.asyncio
    async def test_fetch_with_author_and_tags(self):
        """Test that author and tags are extracted correctly."""
        tag1 = MockFeedEntry(term="security")
        tag2 = MockFeedEntry(term="python")

        entry = MockFeedEntry(
            guid="author-tags-test",
            link="https://example.com/article",
            title="Article with Author and Tags",
            author="John Doe",
            tags=[tag1, tag2],
            published_parsed=time.struct_time(
                (2024, 1, 15, 10, 30, 0, 0, 15, 0)
            ),
            summary="Content",
            content=[],
        )

        result = {
            "entries": [entry],
            "bozo": False,
        }

        mock_response = self._create_mock_response(b"<rss></rss>")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=result):
                connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})
                fetch_result = await connector.fetch()

        items = fetch_result.items
        assert len(items) == 1
        assert items[0]["author"] == "John Doe"
        assert items[0]["tags"] == ["security", "python"]


class TestRSSConnectorParseDate:
    """Tests for _parse_date method."""

    def test_parse_date_from_published_parsed(self):
        """Test parsing date from published_parsed field."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(
            published_parsed=time.struct_time(
                (2024, 3, 15, 14, 30, 0, 0, 75, 0)
            )
        )

        result = connector._parse_date(entry)

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.tzinfo == UTC

    def test_parse_date_from_published_string(self):
        """Test parsing date from published string."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(
            published_parsed=None,
            published="Mon, 15 Jan 2024 10:30:00 +0000",
        )

        result = connector._parse_date(entry)

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_date_fallback_to_current_time(self):
        """Test that missing date falls back to current UTC time."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(published_parsed=None)

        before = datetime.now(UTC)
        result = connector._parse_date(entry)
        after = datetime.now(UTC)

        assert before <= result <= after
        assert result.tzinfo == UTC


class TestRSSConnectorGetContent:
    """Tests for _get_content method."""

    def test_get_content_from_summary(self):
        """Test extracting content from summary."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(
            content=[],
            summary="Summary content",
            description=None,
        )

        result = connector._get_content(entry)

        assert result == "Summary content"

    def test_get_content_from_description(self):
        """Test extracting content from description."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(
            content=[],
            summary=None,
            description="Description content",
        )

        result = connector._get_content(entry)

        assert result == "Description content"

    def test_get_content_from_content_field(self):
        """Test extracting content from content field."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        content_obj = MockFeedEntry(value="Full content from content field")

        entry = MockFeedEntry(
            content=[content_obj],
            summary="Summary content",
        )

        result = connector._get_content(entry)

        assert result == "Full content from content field"

    def test_get_content_empty(self):
        """Test empty content returns empty string."""
        connector = RSSConnector({"feed_url": "https://example.com/feed.xml"})

        entry = MockFeedEntry(content=[], summary=None, description=None)

        result = connector._get_content(entry)

        assert result == ""


