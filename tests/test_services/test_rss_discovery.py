# tests/test_services/test_rss_discovery.py
"""Tests for RSS discovery service."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


class TestRSSDiscovery:
    """Test RSS auto-discovery functionality."""

    @pytest.mark.asyncio
    async def test_discover_from_html_link(self):
        """Test discovering RSS from HTML link tags."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_excludes_comments_feed(self):
        """Test that comments feeds are excluded in favor of main feed."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="/comments/feed/">
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_returns_none_when_no_rss_found(self):
        """Test that None is returned when no RSS is found."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '<html><head></head></html>'
        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.head = AsyncMock(return_value=MagicMock(status_code=404))

            result = await service.discover("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_discover_handles_relative_urls(self):
        """Test that relative RSS URLs are converted to absolute."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="feed.xml">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com/blog/")
            assert result == "https://example.com/blog/feed.xml"
