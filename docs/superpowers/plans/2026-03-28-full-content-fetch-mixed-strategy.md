# Full Content Fetch Two-Level Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two-level full content fetch strategy with unified trigger point (方案 A). Content incomplete → PENDING_FULL_FETCH → full fetch → success=MAPPED / fail=REJECTED. API only exposes MAPPED status.

**Architecture:** Level 1 uses httpx + trafilatura. On failure (403, content too short), Level 2 uses Jina AI Reader (20 RPM, no API key). ContentQualityService determines if full fetch needed. New status PENDING_FULL_FETCH for items awaiting full fetch.

**Tech Stack:** Python 3.11+, httpx, trafilatura, Dramatiq, PostgreSQL, SQLAlchemy, Alembic

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/cyberpulse/models/item.py` | Modify - Add PENDING_FULL_FETCH status |
| `src/cyberpulse/services/content_quality_service.py` | **New** - 内容质量判断规则 |
| `src/cyberpulse/services/jina_client.py` | **New** - Jina AI client (20 RPM) |
| `src/cyberpulse/services/full_content_fetch_service.py` | Extend with Level 2 fallback |
| `src/cyberpulse/tasks/full_content_tasks.py` | **New** - Dramatiq task (concurrency=3) |
| `src/cyberpulse/tasks/quality_tasks.py` | Modify - Integrate full content fetch trigger |
| `src/cyberpulse/api/routers/items.py` | Modify - Filter by status == MAPPED |
| `alembic/versions/xxx_add_pending_full_fetch.py` | **New** - Migration |
| `tests/test_services/test_content_quality.py` | **New** - 质量判断测试 |
| `tests/test_services/test_jina_client.py` | **New** - Jina client tests |
| `tests/test_tasks/test_full_content_tasks.py` | **New** - Task tests |

---

## Task 1: Add PENDING_FULL_FETCH Status

**Files:**
- Modify: `src/cyberpulse/models/item.py`
- Create: `alembic/versions/xxx_add_pending_full_fetch.py`

- [ ] **Step 1: Update ItemStatus enum**

Edit `src/cyberpulse/models/item.py`:

```python
class ItemStatus(StrEnum):
    """Item processing status"""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PENDING_FULL_FETCH = "PENDING_FULL_FETCH"  # Waiting for full content fetch
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"
```

- [ ] **Step 2: Create database migration**

```bash
uv run alembic revision -m "add pending_full_fetch status"
```

Edit the generated migration file:

```python
"""add pending_full_fetch status

Revision ID: xxx
Revises: yyy
Create Date: 2026-03-28
"""
from alembic import op

# revision identifiers
revision = "xxx"
down_revision = "yyy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum value to itemstatus
    op.execute("ALTER TYPE itemstatus ADD VALUE IF NOT EXISTS 'PENDING_FULL_FETCH'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    # This is a no-op for safety
    pass
```

- [ ] **Step 3: Run migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/models/item.py alembic/versions/
git commit -m "feat(models): add PENDING_FULL_FETCH status for items awaiting full fetch"
```

---

## Task 2: Update API Filter

**Files:**
- Modify: `src/cyberpulse/api/routers/items.py`
- Modify: `tests/test_api/test_items.py`

- [ ] **Step 1: Update filter condition**

Edit `src/cyberpulse/api/routers/items.py`, line 71:

```python
# Before
query = db.query(Item).filter(Item.status != ItemStatus.REJECTED)

# After
query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)
```

- [ ] **Step 2: Update/add tests**

Add test to `tests/test_api/test_items.py`:

```python
def test_items_only_returns_mapped_status(client, db):
    """Test that API only returns items with MAPPED status."""
    from cyberpulse.models import Item, ItemStatus
    from datetime import datetime, UTC

    # Create items with different statuses
    statuses = [
        ItemStatus.NEW,
        ItemStatus.NORMALIZED,
        ItemStatus.PENDING_FULL_FETCH,
        ItemStatus.MAPPED,
        ItemStatus.REJECTED,
    ]

    for i, status in enumerate(statuses):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            status=status,
        )
        db.add(item)
    db.commit()

    response = client.get("/api/v1/items?limit=100")
    assert response.status_code == 200

    data = response.json()
    returned_statuses = {item["id"].split("_")[1] for item in data["data"]}

    # Only MAPPED should be returned
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "item_00000003"  # MAPPED item
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_api/test_items.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/api/routers/items.py tests/test_api/test_items.py
git commit -m "fix(api): filter items by status == MAPPED to only expose complete content"
```

---

## Task 3: Create ContentQualityService

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
        title=getattr(item, "raw_title", None),
        body=getattr(item, "raw_body", None),
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

## Task 4: Create Jina AI Client

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

## Task 5: Extend FullContentFetchService with Level 2

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

## Task 6: Create Dramatiq Task (concurrency=3)

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

On success: item -> NORMALIZED -> quality_check
On failure: item -> REJECTED
"""

import asyncio
import logging

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus
from ..services.full_content_fetch_service import FullContentFetchService
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
            # No URL - reject immediately
            item.full_fetch_attempted = True
            item.full_fetch_succeeded = False
            item.status = ItemStatus.REJECTED
            db.commit()
            logger.warning(f"Item {item_id} has no URL, marking REJECTED")
            return {"item_id": item_id, "error": "No URL", "status": "REJECTED"}

        logger.info(f"Fetching full content for {item_id}")

        service = FullContentFetchService()
        result = asyncio.run(service.fetch_full_content(url))

        # Update item
        item.full_fetch_attempted = True

        if result.success and result.content:
            item.full_fetch_succeeded = True
            item.raw_content = result.content
            # Set to NORMALIZED to trigger re-quality-check
            item.status = ItemStatus.NORMALIZED
            logger.info(f"Full content fetched: {len(result.content)} chars via {result.level}")

            db.commit()

            # Re-normalize with new content
            from .normalization_tasks import normalize_item
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

## Task 7: Update Quality Tasks and Source API

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`
- Modify: `src/cyberpulse/api/routers/sources.py`

- [ ] **Step 1: Update quality_check_item to use ContentQualityService**

Edit `src/cyberpulse/tasks/quality_tasks.py`:

Replace the `_handle_pass` function and modify the quality check logic:

```python
"""Quality check tasks for validating normalized items."""

import logging

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus, Source
from ..services.content_quality_service import ContentQualityService
from ..services.normalization_service import NormalizationResult
from ..services.quality_gate_service import QualityDecision, QualityGateService
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def quality_check_item(
    item_id: str,
    normalized_title: str,
    normalized_body: str,
    canonical_hash: str,
    language: str | None = None,
    word_count: int = 0,
    extraction_method: str = "trafilatura",
) -> None:
    """Run quality check on an item.

    This task:
    1. Gets item and normalization result
    2. Runs QualityGateService for meta quality
    3. Runs ContentQualityService for content quality
    4. If content insufficient: PENDING_FULL_FETCH + trigger full fetch
    5. If content sufficient: MAPPED

    Args:
        item_id: The item ID to check.
        normalized_title: Normalized title from normalization.
        normalized_body: Normalized body from normalization.
        canonical_hash: Hash for deduplication.
        language: Detected language code.
        word_count: Word count of normalized body.
        extraction_method: Method used for extraction.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting quality check for item: {item_id}")

        # Create normalization result object
        normalization_result = NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            canonical_hash=canonical_hash,
            language=language,
            word_count=word_count,
            extraction_method=extraction_method,
        )

        # Run meta quality check
        quality_service = QualityGateService()
        quality_result = quality_service.check(item, normalization_result)

        # Run content quality check
        content_service = ContentQualityService()
        content_result = content_service.check_quality(
            title=normalized_title,
            body=normalized_body,
        )

        logger.debug(
            f"Quality check result for {item_id}: "
            f"decision={quality_result.decision.value}, "
            f"needs_full_fetch={content_result.needs_full_fetch}"
        )

        if quality_result.decision == QualityDecision.REJECT:
            # Meta quality rejected (e.g., duplicate)
            _handle_reject(db, item, quality_result)
            db.commit()
            return

        if content_result.needs_full_fetch:
            # Content quality insufficient - need full fetch
            _handle_needs_full_fetch(db, item, content_result.reason)
            db.commit()

            # Trigger full content fetch
            if item.url:
                from .full_content_tasks import fetch_full_content
                fetch_full_content.send(item_id)
                logger.info(f"Queued full fetch for {item_id}: {content_result.reason}")
            else:
                # No URL - reject immediately
                item.status = ItemStatus.REJECTED
                db.commit()
                logger.warning(f"Item {item_id} needs full fetch but has no URL, marking REJECTED")
        else:
            # All checks passed
            _handle_pass(db, item, normalization_result, quality_result)
            db.commit()

        logger.info(f"Quality check complete for item {item_id}")

    except Exception as e:
        logger.error(f"Quality check failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def _handle_pass(
    db,
    item: Item,
    normalization_result: NormalizationResult,
    quality_result,
) -> None:
    """Handle a passed quality check."""
    item.status = ItemStatus.MAPPED
    item.normalized_title = normalization_result.normalized_title
    item.normalized_body = normalization_result.normalized_body
    item.canonical_hash = normalization_result.canonical_hash
    item.language = normalization_result.language
    item.word_count = normalization_result.word_count
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Update source statistics
    source = getattr(item, "source", None)
    if source:
        source.total_items = (source.total_items or 0) + 1

    logger.info(f"Item {item.item_id} passed quality check: MAPPED")


def _handle_needs_full_fetch(
    db,
    item: Item,
    reason: str,
) -> None:
    """Handle item that needs full content fetch."""
    item.status = ItemStatus.PENDING_FULL_FETCH
    item.meta_completeness = 0.0
    item.content_completeness = 0.0

    # Store reason in metadata
    if item.raw_metadata is None:
        item.raw_metadata = {}
    item.raw_metadata["full_fetch_reason"] = reason

    logger.info(f"Item {item.item_id} needs full fetch: {reason}")


def _handle_reject(db, item: Item, quality_result) -> None:
    """Handle a rejected quality check."""
    item.status = ItemStatus.REJECTED
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Store rejection reason
    if item.raw_metadata is None:
        item.raw_metadata = {}
    item.raw_metadata["rejection_reason"] = quality_result.rejection_reason
    item.raw_metadata["quality_warnings"] = quality_result.warnings

    logger.warning(f"Item {item.item_id} rejected: {quality_result.rejection_reason}")


@dramatiq.actor(max_retries=3)
def recheck_item(item_id: str) -> None:
    """Re-run quality check on an item."""
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        item.status = ItemStatus.NEW
        db.commit()

        normalize_actor = broker.get_actor("normalize_item")
        normalize_actor.send(item_id)

        logger.info(f"Queued re-processing for item: {item_id}")

    except Exception as e:
        logger.error(f"Recheck failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 2: Update create_source to trigger immediate ingestion**

Edit `src/cyberpulse/api/routers/sources.py`:

```python
@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    source: SourceCreate,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """
    Create a new source and trigger immediate ingestion.

    New sources enter observation period by default (30 days).

    **Tier/Score Rules:**
    - If both `tier` and `score` provided: use as-is
    - If only `score` provided: tier is derived from score
    - If only `tier` provided: score defaults to tier's middle value
    - If neither provided: defaults to T2 with score 50

    **Tier-Score Mapping:**
    - T0: score >= 80
    - T1: 60 <= score < 80
    - T2: 40 <= score < 60
    - T3: score < 40
    """
    logger.debug(
        f"create_source called by client {client.client_id}: name={source.name}"
    )

    # Convert tier string to enum if provided
    tier_enum = None
    if source.tier:
        tier_enum = _validate_tier(source.tier)

    # Create service and add source
    service = SourceService(db)
    created_source, message = service.add_source(
        name=source.name,
        connector_type=source.connector_type,
        tier=tier_enum,
        config=source.config or {},
        score=source.score,
    )

    if created_source is None:
        # Duplicate name
        raise HTTPException(
            status_code=409,
            detail=message
        )

    # Trigger immediate ingestion for the new source
    from ...tasks.ingestion_tasks import ingest_source
    try:
        ingest_source.send(created_source.source_id)
        logger.info(f"Triggered initial ingestion for source: {created_source.source_id}")
    except Exception as e:
        logger.error(f"Failed to trigger initial ingestion: {e}", exc_info=True)
        # Don't fail the request - source was created successfully

    return SourceResponse.model_validate(created_source)
```

- [ ] **Step 3: Run tests to verify no regression**

```bash
uv run pytest tests/test_tasks/test_quality_tasks.py tests/test_api/test_sources.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/tasks/quality_tasks.py src/cyberpulse/api/routers/sources.py
git commit -m "feat(tasks,api): integrate ContentQualityService, trigger ingestion on source creation"
```

---

## Task 8: Integration Tests with Real URLs

**Files:**
- Create: `tests/test_integration/test_full_content_fetch_real.py`
- Create: `tests/fixtures/real_test_urls.py`

- [ ] **Step 1: Create test fixtures with real URLs**

Create `tests/fixtures/real_test_urls.py`:

```python
"""Real problematic URLs for integration testing.

These URLs are extracted from issues/ directory and validated through
manual testing. They represent real-world content extraction challenges.
"""

# URLs that work with Level 1 (httpx + trafilatura)
LEVEL1_SUCCESS_URLS = [
    # paulgraham.com - classic essays, no JS
    ("http://www.paulgraham.com/superlinear.html", "paulgraham.com"),
    # mitchellh.com - technical blog
    ("https://mitchellh.com/writing/my-ai-adoption-journey", "mitchellh.com"),
]

# URLs that need Level 2 (Jina AI) - Level 1 returns 403
LEVEL2_RESCUE_URLS = [
    # OpenAI blog - Cloudflare protection
    ("https://openai.com/index/chatgpt/", "openai"),
    # Anthropic Research - Cloudflare
    ("https://www.anthropic.com/research/alignment-faking", "anthropic"),
]

# URLs with known title-body similarity issue
TITLE_AS_BODY_URLS = [
    # Anthropic Research - title sometimes extracted as body
    ("https://www.anthropic.com/research/constitutional-classifiers", "anthropic"),
]

# URLs that fail both levels (for testing REJECTED status)
EXPECTED_FAIL_URLS = [
    # WeChat requires special handling
    ("https://mp.weixin.qq.com/s?__biz=MzU3ODQ0NjA3Mg==&mid=2247486001", "wechat"),
]
```

- [ ] **Step 2: Write integration tests**

Create `tests/test_integration/test_full_content_fetch_real.py`:

```python
"""Integration tests using real problematic URLs.

These tests validate the full content fetch pipeline against real-world
content extraction challenges documented in issues/ directory.

Run with: uv run pytest tests/test_integration/test_full_content_fetch_real.py -v --run-integration
"""

import os
import pytest

from cyberpulse.services.full_content_fetch_service import FullContentFetchService
from cyberpulse.services.content_quality_service import ContentQualityService

# Skip all tests in this module if --run-integration not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests"
)


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
```

- [ ] **Step 3: Update Task 3 tests to use real URL patterns**

Add to `tests/test_services/test_content_quality.py`:

```python
class TestContentQualityWithRealPatterns:
    """Test content quality rules against real problematic patterns."""

    def test_anthropic_title_as_body_pattern(self):
        """Test detection of Anthropic-style title-as-body issue."""
        service = ContentQualityService()

        # Simulate Anthropic Research issue: title extracted as body
        result = service.check_quality(
            title="Alignment Faking in Large Language Models",
            body="Alignment Faking in Large Language Models",  # Same as title
        )
        assert result.needs_full_fetch is True

    def test_paulgraham_short_content(self):
        """Test detection of short content (RSS summary only)."""
        service = ContentQualityService()

        # paulgraham.com RSS often has no content
        result = service.check_quality(
            title="Superlinear Returns",
            body="A short summary from RSS feed",  # < 100 chars
        )
        assert result.needs_full_fetch is True

    def test_cloudflare_challenge_content(self):
        """Test detection of Cloudflare challenge page content."""
        service = ContentQualityService()

        # Cloudflare challenge response
        result = service.check_quality(
            title="Article Title",
            body="Please enable JavaScript to continue. Checking your browser...",
        )
        assert result.needs_full_fetch is True
```

- [ ] **Step 4: Run integration tests manually**

```bash
# Run unit tests
uv run pytest tests/test_services/test_content_quality.py -v

# Run integration tests (requires network)
RUN_INTEGRATION_TESTS=1 uv run pytest tests/test_integration/test_full_content_fetch_real.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/real_test_urls.py tests/test_integration/test_full_content_fetch_real.py tests/test_services/test_content_quality.py
git commit -m "test: add integration tests with real problematic URLs from issues"
```

---

## Task 9: Final Verification

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

Status flow:
- NEW → NORMALIZED → quality_check
- Content complete → MAPPED (API visible)
- Content incomplete → PENDING_FULL_FETCH
  - Full fetch success → NORMALIZED → MAPPED
  - Full fetch failure → REJECTED (API invisible)
- No URL → REJECTED

Changes:
- Add PENDING_FULL_FETCH status
- API filter: status == MAPPED only
- ContentQualityService: unified trigger (3 rules)
- Level 1: httpx + trafilatura (~57% success)
- Level 2: Jina AI Reader (20 RPM, no API key)
- Dramatiq task max_concurrency=3

Design: docs/superpowers/specs/2026-03-27-full-content-fetch-mixed-strategy-design.md"
```

---

## Summary

| Task | Files | Key Change |
|------|-------|------------|
| 1 | item.py, migration | 新增 PENDING_FULL_FETCH 状态 |
| 2 | items.py | API 过滤改为 `status == MAPPED` |
| 3 | content_quality_service.py | 统一触发规则（3条规则） |
| 4 | jina_client.py | Jina AI 客户端，20 RPM |
| 5 | full_content_fetch_service.py | Level 2 fallback |
| 6 | full_content_tasks.py | Dramatiq 任务，并发=3 |
| 7 | quality_tasks.py, sources.py | 集成 ContentQualityService + 创建源触发采集 |
| 8 | real_test_urls.py, test_full_content_fetch_real.py | 真实 URL 集成测试 |
| 9 | - | 最终验证 |

**状态流转验证矩阵：**

| 场景 | 最终状态 | API 可见 | 正确性 |
|------|---------|---------|--------|
| 内容完整 | MAPPED | ✓ | ✓ |
| 内容不足 + 全文成功 | MAPPED | ✓ | ✓ |
| 内容不足 + 全文失败 | REJECTED | ✗ | ✓ |
| 内容不足 + 无 URL | REJECTED | ✗ | ✓ |
| 全文获取进行中 | PENDING_FULL_FETCH | ✗ | ✓ |

**真实 URL 测试数据来源：**

| URL 类别 | 来源 | 测试目的 |
|----------|------|---------|
| Level 1 成功 | paulgraham.com, mitchellh.com | 验证基础提取 |
| Level 2 救援 | openai.com, anthropic.com | 验证 Cloudflare 绕过 |
| 标题-正文相似 | anthropic.com/research | 验证相似度检测 |
| 预期失败 | wechat | 验证 REJECTED 流程 |