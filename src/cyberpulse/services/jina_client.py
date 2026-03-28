"""Jina AI Reader client (20 RPM, no API key).

Request headers:
- X-Return-Format: markdown
- X-Md-Link-Style: discarded (removes links, keeps text)
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

JINA_BASE_URL = "https://r.jina.ai/"
DEFAULT_TIMEOUT = 30.0
MIN_CONTENT_LENGTH = 100


@dataclass
class JinaResult:
    """Result of Jina AI fetch operation."""

    content: str
    success: bool
    error: str | None = None


class JinaAIClient:
    """Jina AI Reader client.

    Rate limit: 20 RPM (no API key required)
    Concurrency: 3 (safe for 20 RPM)

    Request headers:
    - X-Return-Format: markdown
    - X-Md-Link-Style: discarded (removes links, keeps text)
    """

    def __init__(self):
        """Initialize Jina AI client."""
        self.concurrency = 3
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self.headers = {
            "X-Return-Format": "markdown",
            "X-Md-Link-Style": "discarded",
        }

    async def fetch(self, url: str) -> JinaResult:
        """Fetch content from URL using Jina AI Reader.

        Args:
            url: The URL to fetch content from.

        Returns:
            JinaResult with content or error.
        """
        async with self._semaphore:
            return await self._do_fetch(url)

    async def _do_fetch(self, url: str) -> JinaResult:
        """Perform the actual fetch.

        Args:
            url: Original URL to fetch.

        Returns:
            JinaResult.
        """
        jina_url = f"{JINA_BASE_URL}{url}"

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    jina_url,
                    headers=self.headers,
                    follow_redirects=True,
                )

            return self._process_response(response)

        except httpx.TimeoutException:
            logger.warning(f"Jina AI timeout for {url}")
            return JinaResult(content="", success=False, error="Timeout")
        except (httpx.RequestError, OSError, ConnectionError) as e:
            # Catch network-related exceptions only, not system exceptions
            logger.error(f"Jina AI network error for {url}: {type(e).__name__}: {e}")
            return JinaResult(
                content="", success=False, error=f"{type(e).__name__}: {e}"
            )

    def _process_response(self, response: httpx.Response) -> JinaResult:
        """Process Jina AI response.

        Args:
            response: HTTP response.

        Returns:
            JinaResult.
        """
        if response.status_code != 200:
            return JinaResult(
                content="",
                success=False,
                error=f"HTTP {response.status_code}",
            )

        content = response.text
        if len(content) >= MIN_CONTENT_LENGTH:
            return JinaResult(content=content, success=True)
        else:
            return JinaResult(
                content=content,
                success=False,
                error=f"Content too short: {len(content)} chars",
            )
