"""Tests for FullContentFetchService."""

from unittest.mock import MagicMock, patch

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
        """Test successful full content fetch via Level 1."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1:
            # Level 1 succeeds with sufficient content
            mock_l1.return_value = FullContentResult(
                content=(
                    "Full article content here. This is a longer piece of text "
                    "that meets the minimum content length requirement of 100 "
                    "characters for successful extraction."
                ),
                success=True,
            )

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is True
        assert "article content" in result.content
        assert result.level == "level1"

    @pytest.mark.asyncio
    async def test_fetch_full_content_failure(self):
        """Test failed full content fetch."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            # Make the get call raise a network error
            async def raise_error(*args, **kwargs):
                raise httpx.ConnectError("Connection error")

            mock_client.get = raise_error

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "ConnectError" in result.error or "Connection" in result.error

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_on_first_try(self):
        """Test fetch_with_retry succeeds on first attempt."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="Content",
                success=True,
            )

            result = await service.fetch_with_retry(
                "https://example.com", max_retries=3
            )

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
        """Test HTTP error handling in full content fetch (Level 1)."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            # Level 1 fails with HTTP 500 error
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="HTTP error: 500"
            )
            # Level 2 also fails (to test error propagation)
            mock_l2.return_value = FullContentResult(
                content="", success=False, error="HTTP 500"
            )

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert result.level == "level2"
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_fetch_full_content_extraction_failure(self):
        """Test handling when Level 1 content extraction fails."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            # Level 1 fails due to content too short
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="Content too short: 0 chars"
            )
            # Level 2 also fails
            mock_l2.return_value = FullContentResult(
                content="", success=False, error="Content too short: 0 chars"
            )

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert result.level == "level2"
        assert "too short" in result.error


class TestFullContentFetchServiceLevel2:
    """Test cases for Level 2 (Jina AI) fallback."""

    @pytest.mark.asyncio
    async def test_level2_fallback_on_403(self):
        """Test Level 2 is used when Level 1 gets 403."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="HTTP 403"
            )
            mock_l2.return_value = FullContentResult(
                content="Full content from Jina", success=True
            )

            result = await service.fetch_full_content("https://example.com")

        assert result.success is True
        assert result.level == "level2"
        mock_l2.assert_called_once()

    @pytest.mark.asyncio
    async def test_level2_fallback_on_content_short(self):
        """Test Level 2 when Level 1 content is short."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            mock_l1.return_value = FullContentResult(
                content="Hi", success=False, error="Content too short: 2 chars"
            )
            mock_l2.return_value = FullContentResult(
                content="Full content from Jina", success=True
            )

            result = await service.fetch_full_content("https://example.com")

        assert result.success is True
        assert result.level == "level2"

    @pytest.mark.asyncio
    async def test_level1_success_skips_level2(self):
        """Test Level 2 not called when Level 1 succeeds."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            mock_l1.return_value = FullContentResult(
                content="Good content from Level 1", success=True
            )

            result = await service.fetch_full_content("https://example.com")

        assert result.success is True
        assert result.level == "level1"
        mock_l2.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_levels_fail(self):
        """Test result when both levels fail."""
        service = FullContentFetchService()

        with patch.object(service, "_fetch_level1") as mock_l1, \
             patch.object(service, "_fetch_level2") as mock_l2:
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="HTTP 403"
            )
            mock_l2.return_value = FullContentResult(
                content="", success=False, error="HTTP 404"
            )

            result = await service.fetch_full_content("https://example.com")

        assert result.success is False
        assert result.level == "level2"


class TestSSRFRedirectProtection:
    """Test cases for SSRF protection on redirects."""

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_blocked(self):
        """Test that redirect to private IP address is blocked."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            # Create a mock response that appears to redirect to private IP
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "http://192.168.1.1/internal"  # Redirect target
            mock_response.text = "<html><body>Internal content</body></html>"

            async def return_response(*args, **kwargs):
                return mock_response

            mock_client.get = return_response

            # Level 1 should block redirect to private IP
            result = await service._fetch_level1("https://example.com/article")

        assert result.success is False
        assert "Redirect to blocked URL" in result.error or "SSRF" in result.error

    @pytest.mark.asyncio
    async def test_redirect_to_localhost_blocked(self):
        """Test that redirect to localhost is blocked."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "http://localhost/admin"  # Redirect target
            mock_response.text = "<html><body>Admin page</body></html>"

            async def return_response(*args, **kwargs):
                return mock_response

            mock_client.get = return_response

            result = await service._fetch_level1("https://example.com/article")

        assert result.success is False
        assert "Redirect to blocked URL" in result.error or "SSRF" in result.error

    @pytest.mark.asyncio
    async def test_redirect_to_metadata_endpoint_blocked(self):
        """Test that redirect to AWS metadata endpoint is blocked."""
        service = FullContentFetchService()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "http://169.254.169.254/latest/meta-data/"
            mock_response.text = "<html><body>Metadata</body></html>"

            async def return_response(*args, **kwargs):
                return mock_response

            mock_client.get = return_response

            result = await service._fetch_level1("https://example.com/article")

        assert result.success is False
        assert "Redirect to blocked URL" in result.error or "SSRF" in result.error


class Test429RetryBehavior:
    """Test cases for 429 rate limit retry behavior."""

    @pytest.mark.asyncio
    async def test_429_triggers_retry(self):
        """Test that 429 response triggers retry."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            # First call returns 429, second succeeds
            mock_fetch.side_effect = [
                FullContentResult(content="", success=False, error="HTTP error: 429"),
                FullContentResult(content="Success content", success=True),
            ]

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is True
        assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_429_retries_all_attempts(self):
        """Test that 429 exhausts all retry attempts before failing."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="", success=False, error="HTTP error: 429"
            )

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is False
        assert mock_fetch.call_count == 3
        assert "429" in result.error

    @pytest.mark.asyncio
    async def test_other_4xx_no_retry(self):
        """Test that other 4xx errors (non-429) do not retry."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="", success=False, error="HTTP error: 400"
            )

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is False
        assert mock_fetch.call_count == 1  # No retry for non-429 4xx
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_429_vs_404_different_behavior(self):
        """Test that 429 retries while 404 does not."""
        service = FullContentFetchService()

        # Test 429 - should retry
        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.side_effect = [
                FullContentResult(content="", success=False, error="HTTP error: 429"),
                FullContentResult(content="", success=False, error="HTTP error: 404"),
            ]

            result = await service.fetch_with_retry(
                "https://example.com/429-then-404",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is False
        assert mock_fetch.call_count == 2  # 429 retried, 404 did not
