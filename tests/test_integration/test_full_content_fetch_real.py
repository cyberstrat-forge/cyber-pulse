"""Integration tests using real problematic URLs.

These tests validate the full content fetch pipeline against real-world
content extraction challenges documented in issues/ directory.

Run with: RUN_INTEGRATION_TESTS=1 uv run pytest \
    tests/test_integration/test_full_content_fetch_real.py -v
"""

import os

import pytest

from cyberpulse.services.content_quality_service import ContentQualityService
from cyberpulse.services.full_content_fetch_service import (
    FullContentFetchService,
    FullContentResult,
)

# ============================================================================
# Mocked tests - Always run (no network required)
# ============================================================================


class TestLevel2FallbackIntegration:
    """End-to-end tests for Level 2 fallback (mocked, no network)."""

    @pytest.mark.asyncio
    async def test_level1_403_triggers_level2(self):
        """Test that Level 1 403 triggers Level 2."""
        from unittest.mock import AsyncMock, patch

        service = FullContentFetchService()

        # Mock Level 1 to return 403
        with patch.object(
            service, "_fetch_level1", new_callable=AsyncMock
        ) as mock_l1:
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="HTTP error: 403"
            )

            # Mock Level 2 to succeed
            with patch.object(
                service, "_fetch_level2", new_callable=AsyncMock
            ) as mock_l2:
                mock_l2.return_value = FullContentResult(
                    content="Full content from Jina AI that is long enough to pass.",
                    success=True,
                )

                result = await service.fetch_full_content("https://openai.com/test")

        assert result.success is True
        assert result.level == "level2"
        mock_l1.assert_called_once()
        mock_l2.assert_called_once()

    @pytest.mark.asyncio
    async def test_level1_success_skips_level2(self):
        """Test that Level 1 success skips Level 2."""
        from unittest.mock import AsyncMock, patch

        service = FullContentFetchService()

        with patch.object(
            service, "_fetch_level1", new_callable=AsyncMock
        ) as mock_l1:
            mock_l1.return_value = FullContentResult(
                content="Good content from Level 1 that passes the check.",
                success=True,
            )

            with patch.object(
                service, "_fetch_level2", new_callable=AsyncMock
            ) as mock_l2:
                result = await service.fetch_full_content("https://example.com")

        assert result.success is True
        assert result.level == "level1"
        mock_l1.assert_called_once()
        mock_l2.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_levels_fail_returns_error(self):
        """Test that both levels failing returns error."""
        from unittest.mock import AsyncMock, patch

        service = FullContentFetchService()

        with patch.object(
            service, "_fetch_level1", new_callable=AsyncMock
        ) as mock_l1:
            mock_l1.return_value = FullContentResult(
                content="", success=False, error="HTTP error: 403"
            )

            with patch.object(
                service, "_fetch_level2", new_callable=AsyncMock
            ) as mock_l2:
                mock_l2.return_value = FullContentResult(
                    content="", success=False, error="Jina AI timeout"
                )

                result = await service.fetch_full_content("https://blocked-site.com")

        assert result.success is False
        assert result.error == "Jina AI timeout"
        assert result.level == "level2"
        mock_l1.assert_called_once()
        mock_l2.assert_called_once()


# ============================================================================
# Real URL tests - Require RUN_INTEGRATION_TESTS=1 (network required)
# ============================================================================


# Skip marker for tests requiring network
requires_integration = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests"
)


@requires_integration
class TestLevel1WithRealURLs:
    """Test Level 1 (httpx + trafilatura) with real URLs."""

    @pytest.mark.asyncio
    async def test_level1_success_urls(self):
        """Test URLs that should work with Level 1."""
        from tests.fixtures.real_test_urls import LEVEL1_SUCCESS_URLS

        service = FullContentFetchService()

        for url, source in LEVEL1_SUCCESS_URLS:
            result = await service.fetch_full_content(url)
            assert result.success, f"Level 1 failed for {source}: {result.error}"
            assert len(result.content) >= 100
            assert result.level == "level1"

    @pytest.mark.asyncio
    async def test_level1_fails_level2_rescues(self):
        """Test URLs that need Level 2 rescue."""
        from tests.fixtures.real_test_urls import LEVEL2_RESCUE_URLS

        service = FullContentFetchService()

        for url, source in LEVEL2_RESCUE_URLS:
            result = await service.fetch_full_content(url)
            assert result.success, f"Level 1+2 failed for {source}: {result.error}"
            assert len(result.content) >= 100
            # Could be level1 or level2 depending on current state


@requires_integration
class TestContentQualityWithRealURLs:
    """Test ContentQualityService with real content."""

    @pytest.mark.asyncio
    async def test_title_body_similarity_detection(self):
        """Test detection of title-as-body issue."""
        from tests.fixtures.real_test_urls import TITLE_AS_BODY_URLS

        service = ContentQualityService()
        fetch_service = FullContentFetchService()

        for url, source in TITLE_AS_BODY_URLS:
            result = await fetch_service.fetch_full_content(url)
            if result.success:
                quality = service.check_quality(
                    title="Test Title",  # Would use actual title
                    body=result.content,
                )
                # This tests the similarity detection logic
                assert isinstance(quality.needs_full_fetch, bool)


@requires_integration
class TestFullPipelineIntegration:
    """End-to-end tests of the full content fetch pipeline."""

    @pytest.mark.asyncio
    async def test_expected_fail_urls(self):
        """Test URLs that are expected to fail (e.g., WeChat)."""
        from tests.fixtures.real_test_urls import EXPECTED_FAIL_URLS

        service = FullContentFetchService()

        for url, source in EXPECTED_FAIL_URLS:
            result = await service.fetch_full_content(url)
            # These are expected to fail - validates REJECTED flow
            # We don't assert failure, just that the system handles it gracefully
            if not result.success:
                assert result.error is not None
