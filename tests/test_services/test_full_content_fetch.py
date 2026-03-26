"""Tests for FullContentFetchService."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services.full_content_fetch_service import (
    FullContentFetchService,
    FullContentResult,
)


class TestFullContentResult:
    """Test cases for FullContentResult dataclass."""

    def test_full_content_result_dataclass(self):
        """Test FullContentResult dataclass."""
        result = FullContentResult(
            content="Test content",
            success=True,
            error=None,
        )
        assert result.content == "Test content"
        assert result.success is True
        assert result.error is None

    def test_full_content_result_with_error(self):
        """Test FullContentResult with error."""
        result = FullContentResult(
            content="",
            success=False,
            error="Connection timeout",
        )
        assert result.content == ""
        assert result.success is False
        assert result.error == "Connection timeout"


class TestFullContentFetchService:
    """Test cases for FullContentFetchService."""

    @pytest.mark.asyncio
    async def test_fetch_full_content_success(self):
        """Test successful full content fetch."""
        service = FullContentFetchService()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "<html><body><p>Full article content here.</p></body></html>"
            mock_response.url = "https://example.com/article"  # Mock URL for redirect validation
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            with patch("trafilatura.extract", return_value="Full article content here."):
                result = await service.fetch_full_content("https://example.com/article")

        assert result.success is True
        assert "article content" in result.content

    @pytest.mark.asyncio
    async def test_fetch_full_content_failure(self):
        """Test failed full content fetch."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            # Make the get call raise an exception
            async def raise_error(*args, **kwargs):
                raise Exception("Connection error")

            mock_client.get = raise_error

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "Connection error" in result.error

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_on_first_try(self):
        """Test fetch_with_retry succeeds on first attempt."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="Content",
                success=True,
            )

            result = await service.fetch_with_retry("https://example.com", max_retries=3)

        assert result.success is True
        assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_on_second_try(self):
        """Test fetch_with_retry succeeds on second attempt."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.side_effect = [
                FullContentResult(content="", success=False, error="Timeout"),
                FullContentResult(content="Content", success=True),
            ]

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is True
        assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_with_retry_all_fail(self):
        """Test fetch_with_retry fails after all attempts."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="",
                success=False,
                error="Connection refused",
            )

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=2,
                retry_delay=0.1,
            )

        assert result.success is False
        assert mock_fetch.call_count == 2
        assert "2 attempts" in result.error

    @pytest.mark.asyncio
    async def test_fetch_full_content_ssrf_blocked(self):
        """Test SSRF protection blocks internal URLs."""
        service = FullContentFetchService()

        # Internal IP should be blocked by SSRF protection
        result = await service.fetch_full_content("http://169.254.169.254/metadata")

        assert result.success is False
        assert "SSRF protection" in result.error

    @pytest.mark.asyncio
    async def test_fetch_full_content_localhost_blocked(self):
        """Test SSRF protection blocks localhost."""
        service = FullContentFetchService()

        result = await service.fetch_full_content("http://localhost:8080/internal")

        assert result.success is False
        assert "SSRF protection" in result.error

    @pytest.mark.asyncio
    async def test_fetch_with_retry_early_exit_on_4xx(self):
        """Test fetch_with_retry exits early on 4xx client errors."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="",
                success=False,
                error="HTTP error: 404",
            )

            result = await service.fetch_with_retry(
                "https://example.com/notfound",
                max_retries=3,
                retry_delay=0.1,
            )

        # Should only call once (early exit on 4xx)
        assert result.success is False
        assert mock_fetch.call_count == 1
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_fetch_full_content_timeout(self):
        """Test timeout handling in full content fetch."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            async def raise_timeout(*args, **kwargs):
                raise httpx.TimeoutException("Connection timed out")

            mock_client.get = raise_timeout

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_full_content_http_error(self):
        """Test HTTP error handling in full content fetch."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.url = "https://example.com/article"

            async def raise_http_error(*args, **kwargs):
                raise httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=mock_response,
                )

            mock_client.get = raise_http_error

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "HTTP error" in result.error
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_fetch_full_content_extraction_failure(self):
        """Test handling when trafilatura fails to extract content."""
        service = FullContentFetchService()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "<html><body></body></html>"
            mock_response.url = "https://example.com/article"
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            # trafilatura returns None for failed extraction
            with patch("trafilatura.extract", return_value=None):
                result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "Failed to extract content" in result.error
