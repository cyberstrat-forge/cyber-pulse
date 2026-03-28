from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

JINA_BASE_URL = "https://r.jina.ai/"
DEFAULT_TIMEOUT = 30.0
MIN_CONTENT_LENGTH = 100

# Global rate limiter singleton - 20 RPM = 3 seconds per request
_global_rate_limiter: _RateLimiter | None = None
_rate_limiter_lock = threading.Lock()


def _get_rate_limiter() -> _RateLimiter:
    """Get the global rate limiter singleton."""
    global _global_rate_limiter
    with _rate_limiter_lock:
        if _global_rate_limiter is None:
            _global_rate_limiter = _RateLimiter(rate_per_minute=20)
        return _global_rate_limiter


class _RateLimiter:
    """Rate limiter that enforces requests per minute.

    Uses threading.Lock instead of asyncio.Lock to avoid event loop binding issues.
    This is safe because the lock is only held briefly for time calculations,
    and the actual sleep is done with asyncio.sleep after releasing the lock.

    For 20 RPM: interval = 60/20 = 3 seconds per request.
    """

    def __init__(self, rate_per_minute: int):
        self._min_interval = 60.0 / rate_per_minute  # 3.0 seconds for 20 RPM
        self._last_request_time: float | None = None
        self._lock = threading.Lock()  # Thread-safe, no event loop binding

    async def acquire(self) -> None:
        """Wait until we can make a request within the rate limit.

        Uses threading.Lock for thread safety and calculates wait time
        before doing async sleep (outside the lock).
        """
        wait_time = 0.0

        with self._lock:
            now = time.time()

            if self._last_request_time is not None:
                elapsed = now - self._last_request_time
                if elapsed < self._min_interval:
                    wait_time = self._min_interval - elapsed
                    logger.debug(f"Rate limiter waiting {wait_time:.2f}s")

            self._last_request_time = time.time()

        # Sleep outside the lock to avoid blocking other threads
        if wait_time > 0:
            await asyncio.sleep(wait_time)


@dataclass
class JinaResult:
    """Result of Jina AI fetch operation."""

    content: str
    success: bool
    error: str | None = None


class JinaAIClient:
    """Jina AI Reader client.

    Rate limit: 20 RPM (no API key required)
    Uses global singleton RateLimiter to enforce rate limit across all instances.

    Request headers:
    - X-Return-Format: markdown
    - X-Md-Link-Style: discarded (removes links, keeps text)
    """

    def __init__(self):
        """Initialize Jina AI client.

        Note: Rate limiting is enforced by global singleton, not per-instance.
        """
        self._rate_limiter = _get_rate_limiter()
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
        await self._rate_limiter.acquire()
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
