from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
import redis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

JINA_BASE_URL = "https://r.jina.ai/"
DEFAULT_TIMEOUT = 30.0
MIN_CONTENT_LENGTH = 100

# Error patterns that Jina AI may return in successful HTTP responses
JINA_ERROR_PATTERNS = [
    "Warning: Target URL returned error",
    "error 403: Forbidden",
    "403 Forbidden",
    "Access Denied",
]

# Redis key for distributed rate limiting
RATE_LIMIT_KEY = "jina:rate_limit"
RATE_LIMIT_PER_MINUTE = 20
RATE_LIMIT_WINDOW_SECONDS = 60


class _RedisRateLimiter:
    """Distributed rate limiter using Redis sliding window.

    This ensures rate limit coordination across multiple processes/containers.
    Uses Redis to track request timestamps within a sliding window.

    For 20 RPM: we track requests in the last 60 seconds and allow max 20.
    """

    def __init__(self, redis_url: str, rate_per_minute: int = 20):
        self._redis_url = redis_url
        self._rate_per_minute = rate_per_minute
        self._window_seconds = 60
        # 3s minimum interval for 20 RPM
        self._min_interval = self._window_seconds / self._rate_per_minute
        self._redis: redis.Redis | None = None

    def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def acquire(self) -> None:
        """Wait until we can make a request within the distributed rate limit.

        Uses Redis sliding window algorithm:
        1. Get count of requests in last 60 seconds
        2. If count >= 20, calculate wait time based on oldest request timestamp
        3. Add current request timestamp to Redis
        """
        while True:
            now = time.time()
            client = self._get_redis()

            # Use pipeline for atomic operations
            pipe = client.pipeline()

            # Remove expired timestamps (older than 60 seconds)
            pipe.zremrangebyscore(RATE_LIMIT_KEY, 0, now - self._window_seconds)

            # Count current requests in window
            pipe.zcard(RATE_LIMIT_KEY)

            # Get the oldest timestamp in window (to calculate wait time if needed)
            pipe.zrange(RATE_LIMIT_KEY, 0, 0, withscores=True)

            results = pipe.execute()
            current_count = results[1]
            oldest_entries = results[2]

            if current_count < self._rate_per_minute:
                # We can proceed - add our timestamp
                # Use a unique member name to allow multiple concurrent requests
                member = f"{now}:{time.monotonic_ns()}"
                client.zadd(RATE_LIMIT_KEY, {member: now})
                count_msg = f"{current_count + 1}/{self._rate_per_minute}"
                logger.debug(f"Rate limiter: request allowed ({count_msg})")
                return

            # Need to wait - calculate wait time from oldest request
            if oldest_entries:
                oldest_time = oldest_entries[0][1]
                # Calculate wait time with small buffer
                wait_time = oldest_time + self._window_seconds - now + 0.1
                logger.debug(
                    f"Rate limiter: at limit "
                    f"({current_count}/{self._rate_per_minute}), "
                    f"waiting {wait_time:.2f}s"
                )
                await asyncio.sleep(wait_time)
            else:
                # Edge case: window just cleared, wait minimum interval
                await asyncio.sleep(self._min_interval)


# Global rate limiter singleton - Redis-based for cross-process coordination
_global_rate_limiter: _RedisRateLimiter | None = None


def _get_rate_limiter(redis_url: str) -> _RedisRateLimiter:
    """Get the global rate limiter singleton.

    Args:
        redis_url: Redis URL for distributed coordination.

    Returns:
        Redis-based rate limiter instance.
    """
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = _RedisRateLimiter(
            redis_url=redis_url, rate_per_minute=RATE_LIMIT_PER_MINUTE
        )
    return _global_rate_limiter


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

    def __init__(self, redis_url: str | None = None):
        """Initialize Jina AI client.

        Args:
            redis_url: Redis URL for distributed rate limiting.
                       If not provided, uses settings.redis_url.
        """
        if redis_url is None:
            from ..config import settings

            redis_url = settings.redis_url

        self._rate_limiter = _get_rate_limiter(redis_url)
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

        # Check for error patterns that Jina AI may return in successful responses
        # (e.g., "Warning: Target URL returned error 403: Forbidden")
        content_lower = content.lower()
        for pattern in JINA_ERROR_PATTERNS:
            if pattern.lower() in content_lower:
                logger.warning(f"Jina AI returned error pattern: {pattern}")
                return JinaResult(
                    content="",
                    success=False,
                    error=f"Jina AI error: {pattern}",
                )

        if len(content) >= MIN_CONTENT_LENGTH:
            return JinaResult(content=content, success=True)
        else:
            return JinaResult(
                content=content,
                success=False,
                error=f"Content too short: {len(content)} chars",
            )
