"""BrowserFetcher - Playwright headless browser HTML rendering."""

import logging
import tempfile

logger = logging.getLogger(__name__)


class BrowserFetcher:
    """无头浏览器渲染 HTML，为 SPA 站点提供兜底。按源启用（render_js: true）。"""

    def __init__(self, headless: bool = True, timeout: float = 30.0):
        """Initialize browser fetcher.

        Args:
            headless: Run browser in headless mode (no window)
            timeout: Page load timeout in seconds
        """
        self.headless = headless
        self.timeout = timeout

    async def render(self, url: str) -> str | None:
        """渲染页面返回完整 HTML；失败返回 None（调用方走 httpx 原始结果）。"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=tempfile.mkdtemp(prefix="cyberpulse-bf-"),
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--mute-audio",
                    ],
                )
                try:
                    page = (
                        browser.pages[0]
                        if browser.pages
                        else await browser.new_page()
                    )
                    await page.goto(
                        url, wait_until="networkidle", timeout=self.timeout * 1000
                    )
                    return await page.content()
                finally:
                    await browser.close()
        except Exception as e:
            logger.warning(
                f"BrowserFetcher render failed for '{url}': {type(e).__name__}: {e}"
            )
            return None
