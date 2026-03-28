# Full Content Fetch Two-Level Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two-level full content fetch strategy with unified trigger point (方案 A). Content incomplete → full fetch → success=MAPPED / fail=REJECTED.

**Architecture:** Level 1 uses httpx + trafilatura. On failure (403, content too short), Level 2 uses Jina AI Reader (20 RPM, no API key). ContentQualityService determines if full fetch needed. Dramatiq task with max_concurrency=3.

**Tech Stack:** Python 3.11+, httpx, trafilatura, Dramatiq, PostgreSQL

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/cyberpulse/services/content_quality_service.py` | **New** - 内容质量判断规则 |
| `src/cyberpulse/services/jina_client.py` | **New** - Jina AI client (20 RPM) |
| `src/cyberpulse/services/full_content_fetch_service.py` | Extend with Level 2 fallback |
| `src/cyberpulse/tasks/full_content_tasks.py` | **New** - Dramatiq task (concurrency=3) |
| `src/cyberpulse/tasks/quality_tasks.py` | Integrate full content fetch trigger |
| `tests/test_services/test_content_quality.py` | **New** - 质量判断测试 |
| `tests/test_services/test_jina_client.py` | **New** - Jina client tests |
| `tests/test_services/test_full_content_fetch.py` | Extend existing tests |
| `tests/test_tasks/test_full_content_tasks.py` | **New** - Task tests |

---

## Task 1: Create ContentQualityService

**Files:**
- Create: `src/cyberpulse/services/content_quality_service.py`
- Create: `tests/test_services/test_content_quality.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_content_quality.py`:

```python
"""Tests for ContentQualityService."""

import pytest

from cyberpulse.services.content_quality_service import (
    ContentQualityService,
    needs_full_fetch,
    MIN_CONTENT_LENGTH,
)


class TestContentQualityService:
    """Test cases for content quality judgment."""

    def test_min_content_length_constant(self):
        """Test MIN_CONTENT_LENGTH is 100."""
        assert MIN_CONTENT_LENGTH == 100

    def test_short_content_needs_fetch(self):
        """Test content < 100 chars needs full fetch."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Test Title",
            body="Short content here",
        )
        assert result.needs_full_fetch is True
        assert "too short" in result.reason.lower()

    def test_long_content_passes(self):
        """Test content >= 100 chars passes."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Test Title",
            body="This is a long enough content that should pass the minimum length check of one hundred characters.",
        )
        assert result.needs_full_fetch is False

    def test_title_as_body_detection(self):
        """Test title-body similarity detection."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Alignment Faking",
            body="Alignment Faking",  # 100% similar
        )
        assert result.needs_full_fetch is True
        assert "title" in result.reason.lower()

    def test_invalid_content_pattern(self):
        """Test invalid content patterns."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Test",
            body="Please enable JavaScript to continue viewing this page.",
        )
        assert result.needs_full_fetch is True
        assert "invalid" in result.reason.lower()

    def test_multiple_patterns_covered(self):
        """Test multiple invalid patterns."""
        patterns = [
            "Checking your browser before accessing",
            "404 Not Found",
            "Access Denied",
        ]
        service = ContentQualityService()
        for pattern in patterns:
            result = service.check_quality(
                title="Test",
                body=pattern,
            )
            assert result.needs_full_fetch is True


class TestNeedsFullFetchFunction:
    """Test cases for needs_full_fetch convenience function."""

    def test_with_item_mock(self):
        """Test with Item-like object."""
        from unittest.mock import MagicMock

        item = MagicMock()
        item.raw_title = "Test Title"
        item.raw_body = "Short"

        assert needs_full_fetch(item) is True

    def test_with_none_values(self):
        """Test with None title/body."""
        from unittest.mock import MagicMock

        item = MagicMock()
        item.raw_title = None
        item.raw_body = None

        assert needs_full_fetch(item) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_content_quality.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ContentQualityService**

Create `src/cyberpulse/services/content_quality_service.py`:

```python
"""Content quality judgment service.

Determines if item content needs full fetch based on:
1. Content length threshold (< 100 chars)
2. Title-body similarity (Anthropic Research issue)
3. Invalid content patterns (JS challenge, 404, etc.)
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

MIN_CONTENT_LENGTH = 100
TITLE_SIMILARITY_THRESHOLD = 0.8

INVALID_CONTENT_PATTERNS = [
    "Please enable JavaScript",
    "Checking your browser",
    "404 Not Found",
    "Access Denied",
]


@dataclass
class QualityCheckResult:
    """Result of content quality check."""

    needs_full_fetch: bool
    reason: str


class ContentQualityService:
    """Service for checking content quality.

    Used in quality_check stage to determine if full fetch is needed.
    """

    def check_quality(
        self,
        title: str | None,
        body: str | None,
    ) -> QualityCheckResult:
        """Check if content needs full fetch.

        Args:
            title: Item title.
            body: Item body content.

        Returns:
            QualityCheckResult with needs_full_fetch flag and reason.
        """
        # Rule 1: Content length
        body_len = len(body or "")
        if body_len < MIN_CONTENT_LENGTH:
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=f"Content too short: {body_len} chars (min: {MIN_CONTENT_LENGTH})",
            )

        # Rule 2: Title-body similarity
        if self._is_title_as_body(title, body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason="Title-body similarity exceeds threshold (possible extraction error)",
            )

        # Rule 3: Invalid content patterns
        if self._has_invalid_pattern(body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason="Content contains invalid pattern (JS challenge/error page)",
            )

        return QualityCheckResult(
            needs_full_fetch=False,
            reason="Content quality check passed",
        )

    def _is_title_as_body(self, title: str | None, body: str | None) -> bool:
        """Check if title was incorrectly extracted as body."""
        if not title or not body:
            return False

        similarity = SequenceMatcher(
            None,
            title.strip().lower(),
            body.strip().lower(),
        ).ratio()

        return similarity > TITLE_SIMILARITY_THRESHOLD

    def _has_invalid_pattern(self, body: str | None) -> bool:
        """Check if body contains invalid content pattern."""
        if not body:
            return False

        return any(pattern.lower() in body.lower() for pattern in INVALID_CONTENT_PATTERNS)


def needs_full_fetch(item) -> bool:
    """Convenience function to check if item needs full fetch.

    Args:
        item: Item object with raw_title and raw_body attributes.

    Returns:
        True if item needs full fetch.
    """
    service = ContentQualityService()
    result = service.check_quality(
        title=item.raw_title,
        body=item.raw_body,
    )
    return result.needs_full_fetch
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_content_quality.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/content_quality_service.py tests/test_services/test_content_quality.py
git commit -m "feat(services): add ContentQualityService for unified full fetch trigger"
```

---

## Task 2: Create Jina AI Client

**Files:**
- Create: `src/cyberpulse/services/jina_client.py`
- Create: `tests/test_services/test_jina_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_services/test_jina_client.py`:

```python
"""Tests for JinaAIClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services.jina_client import JinaAIClient, JinaResult


class TestJinaAIClient:
    """Test cases for JinaAIClient."""

    def test_init(self):
        """Test initialization."""
        client = JinaAIClient()
        assert client.concurrency == 3
        assert client._semaphore._value == 3

    def test_headers_include_required_params(self):
        """Test headers include X-Return-Format and X-Md-Link-Style."""
        client = JinaAIClient()
        assert client.headers["X-Return-Format"] == "markdown"
        assert client.headers["X-Md-Link-Style"] == "discarded"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Test successful fetch."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Test content that is long enough to pass the minimum length check."
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is True
        assert "Test content" in result.content
        # Verify correct headers were passed
        call_args = mock_client.get.call_args
        assert call_args[1]["headers"]["X-Return-Format"] == "markdown"
        assert call_args[1]["headers"]["X-Md-Link-Style"] == "discarded"

    @pytest.mark.asyncio
    async def test_fetch_content_too_short(self):
        """Test fetch with content too short."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Short"
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "too short" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_429_rate_limit(self):
        """Test handling of rate limit (429)."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = ""
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "429" in result.error

    @pytest.mark.asyncio
    async def test_fetch_404(self):
        """Test handling of 404."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = ""
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "404" in result.error

    @pytest.mark.asyncio
    async def test_fetch_timeout(self):
        """Test handling of timeout."""
        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            result = await client.fetch("https://example.com")

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Test semaphore limits concurrent requests to 3."""
        import asyncio

        client = JinaAIClient()

        with patch.object(httpx.AsyncClient, "__aenter__") as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Content that is long enough to pass minimum length."
            mock_client.get = AsyncMock(return_value=mock_response)

            # Launch 5 concurrent requests
            tasks = [client.fetch(f"https://example{i}.com") for i in range(5)]
            results = await asyncio.gather(*tasks)

        assert all(r.success for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_jina_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement JinaAIClient**

Create `src/cyberpulse/services/jina_client.py`:

```python
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
        except Exception as e:
            logger.error(f"Jina AI error for {url}: {type(e).__name__}: {e}")
            return JinaResult(content="", success=False, error=f"{type(e).__name__}: {e}")

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_jina_client.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/jina_client.py tests/test_services/test_jina_client.py
git commit -m "feat(services): add JinaAIClient with X-Return-Format and X-Md-Link-Style headers"
```

---

## Task 3: Extend FullContentFetchService with Level 2

**Files:**
- Modify: `src/cyberpulse/services/full_content_fetch_service.py`
- Modify: `tests/test_services/test_full_content_fetch.py`

- [ ] **Step 1: Add failing tests for Level 2 fallback**

Add to `tests/test_services/test_full_content_fetch.py`:

```python
# Add at top if not present
from unittest.mock import patch, MagicMock, AsyncMock

# Add new test class
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_services/test_full_content_fetch.py::TestFullContentFetchServiceLevel2 -v
```

Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement Level 2 in FullContentFetchService**

Replace `src/cyberpulse/services/full_content_fetch_service.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_services/test_full_content_fetch.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/full_content_fetch_service.py tests/test_services/test_full_content_fetch.py
git commit -m "feat(services): add Level 2 (Jina AI) fallback to FullContentFetchService"
```

---

## Task 4: Create Dramatiq Task (concurrency=3)

**Files:**
- Create: `src/cyberpulse/tasks/full_content_tasks.py`
- Create: `tests/test_tasks/test_full_content_tasks.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tasks/test_full_content_tasks.py`:

```python
"""Tests for full content fetch tasks."""

import pytest


class TestFetchFullContentTask:
    """Test cases for fetch_full_content task."""

    def test_task_exists(self):
        """Test that the task is registered."""
        from cyberpulse.tasks.full_content_tasks import fetch_full_content
        assert fetch_full_content is not None

    def test_task_has_max_concurrency_3(self):
        """Test that task has max_concurrency=3 for 20 RPM limit."""
        from cyberpulse.tasks.full_content_tasks import fetch_full_content
        # Check actor options
        assert fetch_full_content.options.get("max_concurrency") == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_tasks/test_full_content_tasks.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the task**

Create `src/cyberpulse/tasks/full_content_tasks.py`:

```python
"""Full content fetch tasks.

Task fetches full content using two-level strategy:
- Level 1: httpx + trafilatura
- Level 2: Jina AI Reader (20 RPM)

On failure, item is marked as REJECTED.
"""

import asyncio
import logging

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus
from ..services.full_content_fetch_service import FullContentFetchService
from .normalization_tasks import normalize_item
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=2, max_concurrency=3)
def fetch_full_content(item_id: str) -> dict:
    """Fetch full content for an item.

    Max concurrency is 3 to respect Jina AI 20 RPM limit.

    Args:
        item_id: The item ID to fetch content for.

    Returns:
        Dictionary with fetch result.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return {"error": "Item not found", "item_id": item_id}

        # Skip if already attempted
        if item.full_fetch_attempted:
            logger.debug(f"Full fetch already attempted for {item_id}")
            return {"item_id": item_id, "skipped": True}

        url = item.url
        if not url:
            return {"error": "No URL", "item_id": item_id}

        logger.info(f"Fetching full content for {item_id}")

        service = FullContentFetchService()
        result = asyncio.run(service.fetch_full_content(url))

        # Update item
        item.full_fetch_attempted = True

        if result.success and result.content:
            item.full_fetch_succeeded = True
            item.raw_body = result.content
            logger.info(f"Full content fetched: {len(result.content)} chars via {result.level}")

            # Re-normalize with new content
            db.commit()
            normalize_item.send(item_id)

            return {
                "item_id": item_id,
                "success": True,
                "content_length": len(result.content),
                "level": result.level,
            }
        else:
            # Full fetch failed - REJECT the item
            item.full_fetch_succeeded = False
            item.status = ItemStatus.REJECTED
            logger.warning(f"Full fetch failed for {item_id}: {result.error}, marking REJECTED")

            db.commit()

            return {
                "item_id": item_id,
                "success": False,
                "error": result.error,
                "status": "REJECTED",
            }

    except Exception as e:
        logger.error(f"Full fetch failed for {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tasks/test_full_content_tasks.py -v
```

Expected: Tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/tasks/full_content_tasks.py tests/test_tasks/test_full_content_tasks.py
git commit -m "feat(tasks): add fetch_full_content task with max_concurrency=3, REJECT on failure"
```

---

## Task 5: Integrate into Quality Tasks

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`

- [ ] **Step 1: Add full content fetch trigger in quality_check**

Read current `src/cyberpulse/tasks/quality_tasks.py` and locate where quality check happens. Add trigger for full fetch when content is insufficient.

Find the quality check logic and add after quality validation:

```python
# After quality check, if content insufficient, queue full fetch
from ..services.content_quality_service import needs_full_fetch

# In quality_check_item function, after existing checks:
if needs_full_fetch(item) and not item.full_fetch_attempted:
    from .full_content_tasks import fetch_full_content
    fetch_full_content.send(item.item_id)
    logger.info(f"Content quality check failed for {item_id}, queued full fetch")
    # Keep item in pending state until full fetch completes
    return {"item_id": item_id, "status": "pending_full_fetch"}
```

- [ ] **Step 2: Run tests to verify no regression**

```bash
uv run pytest tests/test_tasks/test_quality_tasks.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/tasks/quality_tasks.py
git commit -m "feat(tasks): integrate ContentQualityService into quality_check, trigger full fetch"
```

---

## Task 6: Final Verification

- [ ] **Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests PASS

- [ ] **Step 2: Run linting**

```bash
uv run ruff check src/ tests/
uv run mypy src/ --ignore-missing-imports
```

Expected: No errors

- [ ] **Step 3: Create final commit**

```bash
git add -A
git commit -m "feat: implement two-level full content fetch (方案 A)

- ContentQualityService: unified trigger point
  - Rule 1: content < 100 chars
  - Rule 2: title-body similarity > 80%
  - Rule 3: invalid content patterns
- Level 1: httpx + trafilatura (~57% success)
- Level 2: Jina AI Reader (20 RPM, no API key)
  - X-Return-Format: markdown
  - X-Md-Link-Style: discarded
- Dramatiq task with max_concurrency=3
- Failure → REJECTED (no summary retained)

Design: docs/superpowers/specs/2026-03-27-full-content-fetch-mixed-strategy-design.md"
```

---

## Summary

| Task | Files | Key Change |
|------|-------|------------|
| 1 | content_quality_service.py | 统一触发规则（3条规则） |
| 2 | jina_client.py | Jina AI 客户端，20 RPM |
| 3 | full_content_fetch_service.py | Level 2 fallback |
| 4 | full_content_tasks.py | Dramatiq 任务，并发=3，失败→REJECTED |
| 5 | quality_tasks.py | 集成 ContentQualityService |
| 6 | - | 最终验证 |

**业务流程（方案 A）：**
```
quality_check → 内容不足 → fetch_full_content → 成功→MAPPED / 失败→REJECTED
```

**Rate Limiting:**
- Jina AI: 20 RPM (no API key)
- Task concurrency: 3 (safe for 20 RPM)
- Headers: `X-Return-Format: markdown`, `X-Md-Link-Style: discarded`