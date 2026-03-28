"""Full content fetch service with two-level strategy."""

import asyncio
import logging
from dataclasses import dataclass

import httpx
import trafilatura

from .base import SSRFError, validate_url_for_ssrf
from .jina_client import JinaAIClient

logger = logging.getLogger(__name__)


@dataclass
class FullContentResult:
    """Result of full content fetch operation."""

    content: str
    success: bool
    error: str | None = None
    level: str | None = None  # "level1" or "level2"


class FullContentFetchService:
    """Service for fetching full article content from URLs.

    Two-level strategy:
    - Level 1: httpx + trafilatura (fast, ~57% success)
    - Level 2: Jina AI Reader (20 RPM, ~100% rescue)
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    MIN_CONTENT_LENGTH = 100

    def __init__(self):
        """Initialize service."""
        self._jina_client = JinaAIClient()

    async def fetch_full_content(self, url: str) -> FullContentResult:
        """Fetch full content using two-level strategy.

        Args:
            url: The URL to fetch content from.

        Returns:
            FullContentResult with content or error.
        """
        # SSRF validation
        try:
            validate_url_for_ssrf(url)
        except SSRFError as e:
            logger.warning(f"SSRF protection blocked URL: {url}")
            return FullContentResult(
                content="", success=False,
                error=f"URL blocked by SSRF protection: {e}",
            )

        # Level 1: httpx + trafilatura
        result = await self._fetch_level1(url)
        if result.success:
            result.level = "level1"
            return result

        logger.debug(f"Level 1 failed for {url}: {result.error}, trying Level 2")

        # Level 2: Jina AI
        result = await self._fetch_level2(url)
        result.level = "level2"
        return result

    async def _fetch_level1(self, url: str) -> FullContentResult:
        """Fetch using Level 1 (httpx + trafilatura)."""
        try:
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
                )

                # Validate final URL after redirects
                final_url = str(response.url)
                if final_url != url:
                    try:
                        validate_url_for_ssrf(final_url)
                    except SSRFError as e:
                        return FullContentResult(
                            content="", success=False,
                            error=f"Redirect to blocked URL: {e}",
                        )

                response.raise_for_status()

                content = trafilatura.extract(
                    response.text,
                    output_format="markdown",
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                )

                if content and len(content) >= self.MIN_CONTENT_LENGTH:
                    return FullContentResult(content=content, success=True)
                else:
                    content_len = len(content) if content else 0
                    return FullContentResult(
                        content=content or "",
                        success=False,
                        error=f"Content too short: {content_len} chars",
                    )

        except httpx.TimeoutException:
            return FullContentResult(content="", success=False, error="Timeout")
        except httpx.HTTPStatusError as e:
            return FullContentResult(
                content="", success=False,
                error=f"HTTP error: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Level 1 error for {url}: {type(e).__name__}: {e}")
            return FullContentResult(
                content="", success=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def _fetch_level2(self, url: str) -> FullContentResult:
        """Fetch using Level 2 (Jina AI)."""
        jina_result = await self._jina_client.fetch(url)
        return FullContentResult(
            content=jina_result.content,
            success=jina_result.success,
            error=jina_result.error,
        )

    async def fetch_with_retry(
        self, url: str, max_retries: int = 3, retry_delay: float = 1.0
    ) -> FullContentResult:
        """Fetch with retry logic."""
        last_error = None

        for attempt in range(max_retries):
            result = await self.fetch_full_content(url)
            if result.success:
                return result

            last_error = result.error

            # Don't retry on 4xx (except 429)
            if result.error and "HTTP error: 4" in result.error:
                if "429" not in result.error:
                    break

            if attempt < max_retries - 1:
                logger.debug(f"Retry {attempt + 1}/{max_retries} for {url}")
                await asyncio.sleep(retry_delay * (attempt + 1))

        return FullContentResult(
            content="", success=False,
            error=f"Failed after {max_retries} attempts: {last_error}",
        )
