# tests/test_services/test_rss_connector_enhanced.py
"""Tests for enhanced RSS connector."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestRSSConnectorEnhanced:
    """Test RSS connector enhancements."""

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        """Test that fetch returns FetchResult with items and redirect_info."""
        from cyberpulse.services.rss_connector import FetchResult, RSSConnector

        connector = RSSConnector({"feed_url": "https://example.com/feed/"})

        # Mock successful response
        rss_content = b'''<?xml version="1.0"?>
        <rss><channel><title>Test</title>
        <item><title>Item 1</title><link>https://example.com/1</link><guid>1</guid></item>
        </channel></rss>'''

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = rss_content
            mock_response.url = "https://example.com/feed/"
            mock_response.history = []
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) == 1
        assert result.redirect_info is None

    @pytest.mark.asyncio
    async def test_fetch_detects_permanent_redirect(self):
        """Test that fetch detects 301 redirect and returns redirect_info."""
        from cyberpulse.services.rss_connector import FetchResult, RSSConnector

        connector = RSSConnector({"feed_url": "https://old.example.com/feed/"})

        rss_content = b'''<?xml version="1.0"?>
        <rss><channel><title>Test</title></channel></rss>'''

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            # Mock redirect history
            mock_hist = MagicMock()
            mock_hist.status_code = 301

            mock_response = MagicMock()
            mock_response.content = rss_content
            mock_response.url = "https://new.example.com/feed/"
            mock_response.history = [mock_hist]
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert result.redirect_info is not None
        assert result.redirect_info["status_code"] == 301
        assert result.redirect_info["original_url"] == "https://old.example.com/feed/"
        assert result.redirect_info["final_url"] == "https://new.example.com/feed/"

    @pytest.mark.asyncio
    async def test_fetch_includes_user_agent(self):
        """Test that fetch includes default User-Agent header."""
        from cyberpulse.services.rss_connector import RSSConnector

        connector = RSSConnector({"feed_url": "https://example.com/feed/"})

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = b'<rss><channel></channel></rss>'
            mock_response.url = "https://example.com/feed/"
            mock_response.history = []
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            await connector.fetch()

            # Verify User-Agent was set
            call_args = mock_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "User-Agent" in headers
            assert "Mozilla" in headers["User-Agent"]
