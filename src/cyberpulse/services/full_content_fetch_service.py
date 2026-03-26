"""Full content fetch service for retrieving article content from URLs."""

import asyncio
import logging
from dataclasses import dataclass

import httpx
import trafilatura

from .base import SSRFError, validate_url_for_ssrf

logger = logging.getLogger(__name__)


@dataclass
class FullContentResult:
    """Result of full content fetch operation."""

    content: str
    success: bool
    error: str | None = None


class FullContentFetchService:
    """Service for fetching full article content from URLs.

    This service retrieves the full content of articles when RSS feeds
    only provide summaries or incomplete content.
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; CyberPulse/1.0)"

    async def fetch_full_content(self, url: str) -> FullContentResult:
        """Fetch full content from a URL.

        Args:
            url: The URL to fetch content from.

        Returns:
            FullContentResult with the extracted content or error.
        """
        # SSRF validation before fetching
        try:
            validate_url_for_ssrf(url)
        except SSRFError as e:
            logger.warning(f"SSRF protection blocked URL: {url}")
            return FullContentResult(
                content="",
                success=False,
                error=f"URL blocked by SSRF protection: {e}",
            )

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
                        logger.warning(f"Redirect to blocked URL: {final_url}")
                        return FullContentResult(
                            content="",
                            success=False,
                            error=f"Redirect to blocked URL: {e}",
                        )

                response.raise_for_status()

                # Extract content using trafilatura
                content = trafilatura.extract(
                    response.text,
                    output_format="markdown",
                    include_comments=False,
                    include_tables=True,
                    favor_precision=True,
                )

                if content:
                    return FullContentResult(
                        content=content,
                        success=True,
                    )
                else:
                    return FullContentResult(
                        content="",
                        success=False,
                        error="Failed to extract content from page",
                    )

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching content from {url}")
            return FullContentResult(
                content="",
                success=False,
                error="Request timeout",
            )
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error fetching content from {url}: {e}")
            return FullContentResult(
                content="",
                success=False,
                error=f"HTTP error: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {type(e).__name__}: {e}")
            return FullContentResult(
                content="",
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def fetch_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> FullContentResult:
        """Fetch content with retry logic.

        Args:
            url: The URL to fetch content from.
            max_retries: Maximum number of retry attempts.
            retry_delay: Delay between retries in seconds.

        Returns:
            FullContentResult with the extracted content or error.
        """
        last_error = None

        for attempt in range(max_retries):
            result = await self.fetch_full_content(url)

            if result.success:
                return result

            last_error = result.error

            # Don't retry on certain errors
            if result.error and "HTTP error: 4" in result.error:
                # Client errors (4xx) don't benefit from retry
                break

            if attempt < max_retries - 1:
                logger.debug(f"Retry {attempt + 1}/{max_retries} for {url}")
                await asyncio.sleep(retry_delay * (attempt + 1))

        return FullContentResult(
            content="",
            success=False,
            error=f"Failed after {max_retries} attempts: {last_error}",
        )
