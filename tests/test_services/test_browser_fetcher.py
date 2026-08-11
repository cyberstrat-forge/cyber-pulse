"""Tests for BrowserFetcher (Playwright HTML rendering fallback)."""

from unittest.mock import AsyncMock, patch

import pytest

from cyberpulse.services.browser_fetcher import BrowserFetcher


class TestBrowserFetcher:
    """Test cases for BrowserFetcher.render."""

    @pytest.mark.asyncio
    async def test_render_success(self):
        """渲染成功返回完整 HTML。"""
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_ctx = AsyncMock()
            mock_page = AsyncMock()
            mock_page.content.return_value = "<html>rendered</html>"
            mock_browser = AsyncMock()
            mock_browser.pages = [mock_page]
            mock_ctx.chromium.launch_persistent_context.return_value = mock_browser
            mock_pw.return_value.__aenter__.return_value = mock_ctx
            fetcher = BrowserFetcher()
            html = await fetcher.render("https://example.com/")
        assert html == "<html>rendered</html>"
        mock_page.goto.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_render_failure_returns_none(self):
        """渲染失败返回 None（调用方用 httpx 原始结果）。"""
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_ctx = AsyncMock()
            mock_ctx.chromium.launch_persistent_context.side_effect = Exception(
                "browser failed"
            )
            mock_pw.return_value.__aenter__.return_value = mock_ctx
            fetcher = BrowserFetcher()
            html = await fetcher.render("https://example.com/")
        assert html is None
