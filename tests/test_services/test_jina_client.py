"""Tests for JinaAIClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services.jina_client import JinaAIClient


class TestJinaAIClient:
    """Test cases for JinaAIClient."""

    def test_init(self):
        """Test initialization."""
        client = JinaAIClient()
        assert client.concurrency == 3
        assert client._semaphore._value == 3

    def test_headers_include_required_params(self):
        """Test headers include X-Return-Format and X-Md-Link-Style."""
        client = JinaAIClient()
        assert client.headers["X-Return-Format"] == "markdown"
        assert client.headers["X-Md-Link-Style"] == "discarded"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Test successful fetch."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = (
                "Test content that is long enough to pass the minimum "
                "length check of 100 characters required by the "
                "JinaAIClient implementation."
            )
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is True
        assert "Test content" in result.content

    @pytest.mark.asyncio
    async def test_fetch_content_too_short(self):
        """Test fetch with content too short."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Short"
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "too short" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_429_rate_limit(self):
        """Test handling of rate limit (429)."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = ""
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "429" in result.error

    @pytest.mark.asyncio
    async def test_fetch_404(self):
        """Test handling of 404."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = ""
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_fetch_timeout(self):
        """Test handling of timeout."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "timeout" in result.error.lower()
