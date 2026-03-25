# RSS 内容质量问题修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Issue #41 和 #46，实现 RSS 内容质量全面修复，包括全文获取、源准入验证、质量门禁增强、源添加体验优化。

**Architecture:** 采用服务层扩展 + Dramatiq 异步任务的方式。新增 FullContentFetchService 获取全文，SourceQualityValidator 验证源质量，TitleParserService 解析复合标题，在 quality_check_item 任务中触发全文获取流程。

**Tech Stack:** Python 3.11+, SQLAlchemy, Dramatiq, httpx, trafilatura, Typer

---

## File Structure

```
src/cyberpulse/
├── models/
│   ├── source.py          # [修改] 新增全文获取相关字段
│   └── item.py            # [修改] 新增全文获取状态字段
├── services/
│   ├── full_content_fetch_service.py   # [新增] 全文获取服务
│   ├── source_quality_validator.py     # [新增] 源质量验证器
│   ├── title_parser_service.py         # [新增] 标题解析服务
│   ├── source_detector_service.py      # [新增] 源信息自动检测
│   ├── quality_gate_service.py         # [修改] 增强内容质量检测
│   └── source_service.py               # [修改] 增强 URL 去重
├── tasks/
│   ├── full_content_tasks.py           # [新增] 全文获取任务
│   └── quality_tasks.py                # [修改] 集成全文获取触发
└── cli/commands/
    └── source.py                       # [修改] 交互式添加流程

alembic/versions/
└── xxx_add_full_fetch_fields.py       # [新增] 数据库迁移

tests/
├── test_services/
│   ├── test_full_content_fetch.py     # [新增]
│   ├── test_source_quality_validator.py # [新增]
│   └── test_title_parser.py           # [新增]
├── test_integration/
│   └── test_full_content_flow.py      # [新增]
└── fixtures/
    └── rss_samples.py                  # [新增] 测试样本数据
```

---

## Phase 1: 数据模型 (Day 1)

### Task 1.1: 扩展 Source 模型

**Files:**
- Modify: `src/cyberpulse/models/source.py`

- [ ] **Step 1: 添加新字段到 Source 模型**

在 `src/cyberpulse/models/source.py` 的 `Source` 类中添加以下字段：

```python
# 在现有字段后添加（约第44行后）

    # Full content fetch configuration
    needs_full_fetch = Column(Boolean, nullable=False, default=False)
    full_fetch_threshold = Column(Float, nullable=True, default=0.7)

    # Source quality markers
    content_type = Column(String(20), nullable=True)  # 'full' | 'summary' | 'mixed'
    avg_content_length = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True, default=50.0)

    # Full fetch statistics
    full_fetch_success_count = Column(Integer, nullable=False, default=0)
    full_fetch_failure_count = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 2: 验证模型导入**

```bash
uv run python -c "from cyberpulse.models import Source; print('Source model OK')"
```
Expected: "Source model OK"

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/source.py
git commit -m "feat(models): add full fetch fields to Source model"
```

---

### Task 1.2: 扩展 Item 模型

**Files:**
- Modify: `src/cyberpulse/models/item.py`

- [ ] **Step 1: 添加新字段到 Item 模型**

在 `src/cyberpulse/models/item.py` 的 `Item` 类中添加以下字段：

```python
# 在现有字段后添加（约第36行后）

    # Full content fetch status
    full_fetch_attempted = Column(Boolean, nullable=False, default=False)
    full_fetch_succeeded = Column(Boolean, nullable=True)
```

- [ ] **Step 2: 验证模型导入**

```bash
uv run python -c "from cyberpulse.models import Item; print('Item model OK')"
```
Expected: "Item model OK"

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/item.py
git commit -m "feat(models): add full fetch status fields to Item model"
```

---

### Task 1.3: 创建数据库迁移

**Files:**
- Create: `alembic/versions/<timestamp>_add_full_fetch_fields.py`

- [ ] **Step 1: 生成迁移文件**

```bash
uv run alembic revision -m "add_full_fetch_fields"
```

- [ ] **Step 2: 编写迁移脚本**

在生成的迁移文件中添加：

```python
"""add full fetch fields

Revision ID: <generated>
Revises: <previous>
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '<generated>'
down_revision = '<previous>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Source table new fields
    op.add_column('sources', sa.Column('needs_full_fetch', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('sources', sa.Column('full_fetch_threshold', sa.Float(), nullable=True))
    op.add_column('sources', sa.Column('content_type', sa.String(20), nullable=True))
    op.add_column('sources', sa.Column('avg_content_length', sa.Integer(), nullable=True))
    op.add_column('sources', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column('sources', sa.Column('full_fetch_success_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sources', sa.Column('full_fetch_failure_count', sa.Integer(), nullable=False, server_default='0'))

    # Item table new fields
    op.add_column('items', sa.Column('full_fetch_attempted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('items', sa.Column('full_fetch_succeeded', sa.Boolean(), nullable=True))


def downgrade() -> None:
    # Item table - drop in reverse order
    op.drop_column('items', 'full_fetch_succeeded')
    op.drop_column('items', 'full_fetch_attempted')

    # Source table - drop in reverse order
    op.drop_column('sources', 'full_fetch_failure_count')
    op.drop_column('sources', 'full_fetch_success_count')
    op.drop_column('sources', 'quality_score')
    op.drop_column('sources', 'avg_content_length')
    op.drop_column('sources', 'content_type')
    op.drop_column('sources', 'full_fetch_threshold')
    op.drop_column('sources', 'needs_full_fetch')
```

- [ ] **Step 3: 验证迁移（不执行）**

```bash
uv run alembic check
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/*_add_full_fetch_fields.py
git commit -m "feat(db): add migration for full fetch fields"
```

---

## Phase 2: 服务层 (Day 2-3)

### Task 2.1: 创建 FullContentFetchService

**Files:**
- Create: `src/cyberpulse/services/full_content_fetch_service.py`
- Create: `tests/test_services/test_full_content_fetch.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_services/test_full_content_fetch.py`：

```python
"""Tests for FullContentFetchService."""

import pytest
from unittest.mock import AsyncMock, patch
from cyberpulse.services.full_content_fetch_service import (
    FullContentFetchService,
    FullContentResult,
)


class TestFullContentFetchService:
    """Test cases for FullContentFetchService."""

    def test_full_content_result_dataclass(self):
        """Test FullContentResult dataclass."""
        result = FullContentResult(
            content="Test content",
            success=True,
            error=None,
        )
        assert result.content == "Test content"
        assert result.success is True
        assert result.error is None

    def test_full_content_result_with_error(self):
        """Test FullContentResult with error."""
        result = FullContentResult(
            content="",
            success=False,
            error="Connection timeout",
        )
        assert result.content == ""
        assert result.success is False
        assert result.error == "Connection timeout"

    @pytest.mark.asyncio
    async def test_fetch_full_content_success(self):
        """Test successful full content fetch."""
        service = FullContentFetchService()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                text="<html><body><p>Full article content here.</p></body></html>"
            )

            with patch("trafilatura.extract") as mock_extract:
                mock_extract.return_value = "Full article content here."

                result = await service.fetch_full_content("https://example.com/article")

        assert result.success is True
        assert "article content" in result.content

    @pytest.mark.asyncio
    async def test_fetch_full_content_failure(self):
        """Test failed full content fetch."""
        service = FullContentFetchService()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = Exception("Connection error")

            result = await service.fetch_full_content("https://example.com/article")

        assert result.success is False
        assert "Connection error" in result.error

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_on_first_try(self):
        """Test fetch_with_retry succeeds on first attempt."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="Content",
                success=True,
            )

            result = await service.fetch_with_retry("https://example.com", max_retries=3)

        assert result.success is True
        assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success_on_second_try(self):
        """Test fetch_with_retry succeeds on second attempt."""
        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.side_effect = [
                FullContentResult(content="", success=False, error="Timeout"),
                FullContentResult(content="Content", success=True),
            ]

            result = await service.fetch_with_retry(
                "https://example.com",
                max_retries=3,
                retry_delay=0.1,
            )

        assert result.success is True
        assert mock_fetch.call_count == 2
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_services/test_full_content_fetch.py -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 FullContentFetchService**

创建 `src/cyberpulse/services/full_content_fetch_service.py`：

```python
"""Full content fetch service for retrieving article content from URLs."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
import trafilatura

logger = logging.getLogger(__name__)


@dataclass
class FullContentResult:
    """Result of full content fetch operation."""

    content: str
    success: bool
    error: Optional[str] = None


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
        try:
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
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
            logger.error(f"Error fetching content from {url}: {e}")
            return FullContentResult(
                content="",
                success=False,
                error=str(e),
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_services/test_full_content_fetch.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/full_content_fetch_service.py tests/test_services/test_full_content_fetch.py
git commit -m "feat(services): add FullContentFetchService for fetching article content"
```

---

### Task 2.2: 创建 TitleParserService

**Files:**
- Create: `src/cyberpulse/services/title_parser_service.py`
- Create: `tests/test_services/test_title_parser.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_services/test_title_parser.py`：

```python
"""Tests for TitleParserService."""

import pytest
from cyberpulse.services.title_parser_service import (
    TitleParserService,
    ParsedTitle,
)


class TestTitleParserService:
    """Test cases for TitleParserService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TitleParserService()

    def test_parsed_title_dataclass(self):
        """Test ParsedTitle dataclass."""
        result = ParsedTitle(
            category="AI",
            date="Dec 18, 2024",
            title="Test Title",
            summary=None,
        )
        assert result.category == "AI"
        assert result.date == "Dec 18, 2024"
        assert result.title == "Test Title"

    def test_parse_anthropic_research_title(self):
        """Test parsing Anthropic Research compound title."""
        title = "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides..."
        result = self.service.parse_compound_title(title, source_name="Anthropic Research")

        assert result.category == "Alignment"
        assert result.date == "Dec 18, 2024"
        assert "Alignment faking" in result.title

    def test_parse_title_with_date_no_source(self):
        """Test parsing title with date when no source pattern matches."""
        title = "Some Article Jan 15, 2024 More Text Here"
        result = self.service.parse_compound_title(title)

        assert result.date == "Jan 15, 2024"
        assert result.category is None
        assert "Jan 15, 2024" not in result.title

    def test_parse_simple_title(self):
        """Test parsing simple title without compound structure."""
        title = "Simple Article Title"
        result = self.service.parse_compound_title(title)

        assert result.title == title
        assert result.category is None
        assert result.date is None
        assert result.summary is None

    def test_parse_empty_title(self):
        """Test parsing empty title."""
        result = self.service.parse_compound_title("")

        assert result.title == ""
        assert result.category is None
        assert result.date is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_services/test_title_parser.py -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 TitleParserService**

创建 `src/cyberpulse/services/title_parser_service.py`：

```python
"""Title parser service for parsing compound RSS titles."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedTitle:
    """Result of parsing a compound title."""

    category: Optional[str]
    date: Optional[str]
    title: str
    summary: Optional[str]


class TitleParserService:
    """Service for parsing compound RSS titles.

    Some RSS feeds (e.g., Anthropic Research) have titles that combine
    multiple fields: category, date, actual title, and summary.

    Example: "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides..."
    """

    # Known source-specific patterns
    SOURCE_PATTERNS = {
        "anthropic_research": re.compile(
            r"^(?P<category>[A-Z][a-z]+)"
            r"(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})?"
            r"(?P<title>.+?)"
            r"(?P<summary>This paper provides.*)?$",
            re.DOTALL,
        ),
    }

    # Generic date pattern for fallback
    DATE_PATTERN = re.compile(
        r"\b(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})\b"
    )

    def parse_compound_title(
        self,
        title: str,
        source_name: Optional[str] = None,
    ) -> ParsedTitle:
        """Parse a compound title into its components.

        Args:
            title: The title string to parse.
            source_name: Optional source name for source-specific parsing.

        Returns:
            ParsedTitle with extracted components.
        """
        if not title:
            return ParsedTitle(
                category=None,
                date=None,
                title=title,
                summary=None,
            )

        # Try source-specific pattern
        if source_name:
            source_key = source_name.lower().replace(" ", "_")
            if source_key in self.SOURCE_PATTERNS:
                pattern = self.SOURCE_PATTERNS[source_key]
                match = pattern.match(title)
                if match:
                    return ParsedTitle(
                        category=match.group("category"),
                        date=match.group("date"),
                        title=match.group("title").strip(),
                        summary=match.group("summary"),
                    )

        # Fallback: extract date from title
        date_match = self.DATE_PATTERN.search(title)
        if date_match:
            # Remove date from title
            clean_title = self.DATE_PATTERN.sub("", title).strip()
            return ParsedTitle(
                category=None,
                date=date_match.group("date"),
                title=clean_title,
                summary=None,
            )

        # No parsing possible, return original
        return ParsedTitle(
            category=None,
            date=None,
            title=title,
            summary=None,
        )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_services/test_title_parser.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/title_parser_service.py tests/test_services/test_title_parser.py
git commit -m "feat(services): add TitleParserService for compound RSS titles"
```

---

### Task 2.3: 创建 SourceQualityValidator

**Files:**
- Create: `src/cyberpulse/services/source_quality_validator.py`
- Create: `tests/test_services/test_source_quality_validator.py`

- [ ] **Step 1: 编写测试**

创建 `tests/test_services/test_source_quality_validator.py`：

```python
"""Tests for SourceQualityValidator."""

import pytest
from unittest.mock import AsyncMock, patch
from cyberpulse.services.source_quality_validator import (
    SourceQualityValidator,
    SourceValidationResult,
)


class TestSourceQualityValidator:
    """Test cases for SourceQualityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SourceQualityValidator()

    def test_source_validation_result_dataclass(self):
        """Test SourceValidationResult dataclass."""
        result = SourceValidationResult(
            is_valid=True,
            content_type="article",
            sample_completeness=0.8,
            avg_content_length=500,
        )
        assert result.is_valid is True
        assert result.content_type == "article"

    def test_quality_constants(self):
        """Test quality threshold constants."""
        assert self.validator.MIN_SAMPLE_ITEMS == 3
        assert self.validator.MIN_AVG_COMPLETENESS == 0.4
        assert self.validator.MIN_AVG_CONTENT_LENGTH == 50

    @pytest.mark.asyncio
    async def test_validate_source_high_quality(self):
        """Test validation of high-quality source."""
        config = {"feed_url": "https://example.com/feed.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": "x" * 600} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is True
        assert result.sample_completeness >= 0.4

    @pytest.mark.asyncio
    async def test_validate_source_low_quality(self):
        """Test validation of low-quality source (empty content)."""
        config = {"feed_url": "https://example.com/empty.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": ""} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is False
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_validate_source_with_force(self):
        """Test validation with force option."""
        config = {"feed_url": "https://example.com/bad.xml"}

        result = await self.validator.validate_source_with_force(
            config,
            force=True,
        )

        assert result.is_valid is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_services/test_source_quality_validator.py -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 SourceQualityValidator**

创建 `src/cyberpulse/services/source_quality_validator.py`：

```python
"""Source quality validator for validating RSS sources."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)


@dataclass
class SourceValidationResult:
    """Result of source quality validation."""

    is_valid: bool
    content_type: str  # 'article' | 'summary_only' | 'empty'
    sample_completeness: float
    avg_content_length: int
    rejection_reason: Optional[str] = None
    samples_analyzed: int = 0


class SourceQualityValidator:
    """Validator for RSS source quality.

    Validates that sources meet minimum quality standards before being added.
    """

    # Quality thresholds
    MIN_SAMPLE_ITEMS = 3
    MAX_SAMPLE_ITEMS = 10
    MIN_AVG_COMPLETENESS = 0.4
    MIN_AVG_CONTENT_LENGTH = 50

    # HTTP settings
    REQUEST_TIMEOUT = 30.0

    async def validate_source(
        self,
        source_config: Dict[str, Any],
    ) -> SourceValidationResult:
        """Validate a source's quality.

        Args:
            source_config: Source configuration with 'feed_url'.

        Returns:
            SourceValidationResult with validation outcome.
        """
        feed_url = source_config.get("feed_url")
        if not feed_url:
            return SourceValidationResult(
                is_valid=False,
                content_type="unknown",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Missing feed_url in configuration",
            )

        # Fetch samples
        samples = await self._fetch_samples(feed_url)

        if not samples:
            return SourceValidationResult(
                is_valid=False,
                content_type="empty",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Could not fetch any items from feed",
            )

        # Analyze samples
        analysis = self._analyze_samples(samples)

        # Determine content type
        if analysis["avg_content_length"] == 0:
            content_type = "empty"
            rejection_reason = "RSS feed has no content"
        elif analysis["avg_content_length"] < self.MIN_AVG_CONTENT_LENGTH:
            content_type = "summary_only"
            rejection_reason = "RSS content quality below threshold"
        else:
            content_type = "article"
            rejection_reason = None

        # Check if meets quality standards
        is_valid = (
            len(samples) >= self.MIN_SAMPLE_ITEMS
            and analysis["avg_completeness"] >= self.MIN_AVG_COMPLETENESS
            and analysis["avg_content_length"] >= self.MIN_AVG_CONTENT_LENGTH
        )

        return SourceValidationResult(
            is_valid=is_valid,
            content_type=content_type,
            sample_completeness=analysis["avg_completeness"],
            avg_content_length=analysis["avg_content_length"],
            rejection_reason=rejection_reason if not is_valid else None,
            samples_analyzed=len(samples),
        )

    async def validate_source_with_force(
        self,
        source_config: Dict[str, Any],
        force: bool = False,
    ) -> SourceValidationResult:
        """Validate source with option to force acceptance.

        Args:
            source_config: Source configuration.
            force: If True, skip quality validation.

        Returns:
            SourceValidationResult.
        """
        if force:
            return SourceValidationResult(
                is_valid=True,
                content_type="unknown",
                sample_completeness=0.0,
                avg_content_length=0,
            )
        return await self.validate_source(source_config)

    async def _fetch_samples(self, feed_url: str) -> List[Dict[str, Any]]:
        """Fetch sample items from RSS feed.

        Args:
            feed_url: URL of the RSS feed.

        Returns:
            List of sample items with content.
        """
        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                response = await client.get(feed_url, follow_redirects=True)
                response.raise_for_status()
                content = response.content

            feed = feedparser.parse(content)
            entries = feed.get("entries", [])[:self.MAX_SAMPLE_ITEMS]

            samples = []
            for entry in entries:
                # Extract content
                entry_content = ""
                if hasattr(entry, "content") and entry.content:
                    for content_obj in entry.content:
                        if hasattr(content_obj, "value"):
                            entry_content = content_obj.value
                            break
                if not entry_content:
                    entry_content = entry.get("summary") or entry.get("description") or ""

                samples.append({
                    "title": entry.get("title", ""),
                    "content": entry_content,
                    "url": entry.get("link", ""),
                })

            return samples

        except Exception as e:
            logger.error(f"Failed to fetch samples from {feed_url}: {e}")
            return []

    def _analyze_samples(self, samples: List[Dict[str, Any]]) -> Dict[str, float]:
        """Analyze sample content quality.

        Args:
            samples: List of sample items.

        Returns:
            Dictionary with analysis metrics.
        """
        if not samples:
            return {"avg_content_length": 0, "avg_completeness": 0.0}

        total_length = 0
        completeness_scores = []

        for sample in samples:
            content = sample.get("content", "")
            length = len(content)
            total_length += length

            # Calculate completeness score
            if length >= 500:
                completeness_scores.append(1.0)
            elif length >= 200:
                completeness_scores.append(0.7)
            elif length >= 50:
                completeness_scores.append(0.4)
            else:
                completeness_scores.append(0.2)

        return {
            "avg_content_length": int(total_length / len(samples)),
            "avg_completeness": sum(completeness_scores) / len(completeness_scores),
        }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_services/test_source_quality_validator.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/source_quality_validator.py tests/test_services/test_source_quality_validator.py
git commit -m "feat(services): add SourceQualityValidator for source admission"
```

---

### Task 2.4: 增强 QualityGateService

**Files:**
- Modify: `src/cyberpulse/services/quality_gate_service.py`

- [ ] **Step 1: 阅读现有代码**

```bash
uv run pytest tests/test_services/test_quality_gate.py -v 2>/dev/null || echo "No existing tests"
```

- [ ] **Step 2: 添加内容质量检测方法**

在 `QualityGateService` 类中添加以下方法和常量：

**注意**：需要确保文件开头有以下导入：
```python
import re
from difflib import SequenceMatcher
from typing import List
```

```python
# 在类定义中添加常量（约第62行后）

    # Content quality detection constants
    TITLE_BODY_SIMILARITY_THRESHOLD = 0.95
    MIN_BODY_LENGTH = 50
    TITLE_DATE_PATTERN = r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b'
```

```python
# 添加新方法

    def _validate_content_quality(self, norm: "NormalizationResult") -> List[str]:
        """Validate content quality and return warnings.

        Checks for:
        1. Title equals body
        2. Body too short
        3. Title contains date pattern

        Args:
            norm: NormalizationResult to validate.

        Returns:
            List of warning messages.
        """
        warnings = []

        # Check title = body
        if self._is_title_body_same(norm.normalized_title, norm.normalized_body):
            warnings.append("标题与正文相同，可能需要全文获取")

        # Check body too short
        body_length = len(norm.normalized_body or "")
        if body_length < self.MIN_BODY_LENGTH:
            warnings.append(f"正文过短（{body_length} 字符），建议获取全文")

        # Check title format anomaly
        if re.search(self.TITLE_DATE_PATTERN, norm.normalized_title or ""):
            warnings.append("标题包含日期，可能存在解析问题")

        return warnings

    def _is_title_body_same(self, title: str, body: str) -> bool:
        """Check if title and body are essentially the same.

        Args:
            title: Normalized title.
            body: Normalized body.

        Returns:
            True if title and body are the same.
        """
        if not title or not body:
            return False

        # Normalize for comparison
        title_normalized = " ".join(title.lower().split())
        body_normalized = " ".join(body.lower().split())

        # Check for exact match
        if title_normalized == body_normalized:
            return True

        # Check for high similarity
        similarity = SequenceMatcher(None, title_normalized, body_normalized).ratio()
        return similarity >= self.TITLE_BODY_SIMILARITY_THRESHOLD
```

- [ ] **Step 3: 在 check 方法中调用内容质量检测**

在 `check` 方法中添加调用：

```python
# 在 _calculate_metrics 调用后添加

        # Validate content quality (new)
        quality_warnings = self._validate_content_quality(normalization_result)

        # Combine warnings
        all_warnings = warnings + quality_warnings
```

- [ ] **Step 4: 验证语法正确**

```bash
uv run python -c "from cyberpulse.services.quality_gate_service import QualityGateService; print('OK')"
```
Expected: "OK"

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/quality_gate_service.py
git commit -m "feat(services): enhance QualityGateService with content quality detection"
```

---

### Task 2.5: 增强 SourceService URL 去重

**Files:**
- Modify: `src/cyberpulse/services/source_service.py`

- [ ] **Step 1: 在 add_source 方法中添加 URL 去重**

在 `add_source` 方法中，在名称去重检查后添加 URL 去重：

```python
# 在第96-98行的名称去重检查后添加

        # Check for duplicate URL (new)
        feed_url = config.get("feed_url") if config else None
        if feed_url:
            existing_by_url = self.db.query(Source).filter(
                Source.config["feed_url"].astext == feed_url
            ).first()
            if existing_by_url:
                return None, f"RSS URL '{feed_url}' 已存在于源 '{existing_by_url.name}'"
```

- [ ] **Step 2: 验证语法正确**

```bash
uv run python -c "from cyberpulse.services.source_service import SourceService; print('OK')"
```
Expected: "OK"

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/services/source_service.py
git commit -m "feat(services): add URL deduplication to SourceService"
```

---

## Phase 3: 任务层 (Day 4)

### Task 3.1: 创建 fetch_full_content Dramatiq 任务

**Files:**
- Create: `src/cyberpulse/tasks/full_content_tasks.py`

- [ ] **Step 1: 创建任务文件**

创建 `src/cyberpulse/tasks/full_content_tasks.py`：

```python
"""Full content fetch tasks."""

import asyncio
import logging
from typing import TYPE_CHECKING

import dramatiq

from ..database import SessionLocal
from ..models import Item, Source

if TYPE_CHECKING:
    from ..services.full_content_fetch_service import FullContentResult

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def fetch_full_content(item_id: str) -> None:
    """Fetch full content for an item.

    This task is triggered when quality_check_item finds
    content_completeness < threshold.

    Args:
        item_id: The item ID to fetch full content for.
    """
    db = SessionLocal()
    try:
        # Get item
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        # Check if already attempted
        if item.full_fetch_attempted:
            logger.info(f"Full fetch already attempted for item: {item_id}")
            return

        # Get source
        source = db.query(Source).filter(Source.source_id == item.source_id).first()

        # Import service here to avoid circular imports
        from ..services.full_content_fetch_service import FullContentFetchService

        fetch_service = FullContentFetchService()

        # Fetch full content (async)
        result = asyncio.run(fetch_service.fetch_full_content(item.url))

        item.full_fetch_attempted = True

        # Update source statistics
        if source:
            if result.success:
                source.full_fetch_success_count += 1
            else:
                source.full_fetch_failure_count += 1

            # Check if source needs review
            total_attempts = source.full_fetch_success_count + source.full_fetch_failure_count
            if total_attempts >= 10:
                failure_rate = source.full_fetch_failure_count / total_attempts
                if failure_rate > 0.5:
                    source.pending_review = True
                    source.review_reason = "全文获取失败率过高"

        if result.success:
            # Update item content
            item.raw_content = result.content
            item.full_fetch_succeeded = True
            db.commit()

            logger.info(f"Full content fetched for item {item_id}")

            # Trigger re-normalization
            from .worker import broker
            normalize_actor = broker.get_actor("normalize_item")
            normalize_actor.send(item_id)

        else:
            # Mark as failed but keep original content
            item.full_fetch_succeeded = False
            db.commit()
            logger.warning(f"Full fetch failed for item {item_id}: {result.error}")

    except Exception as e:
        logger.error(f"Full fetch task failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 2: 在 tasks/__init__.py 中导出**

在 `src/cyberpulse/tasks/__init__.py` 中添加：

```python
from .full_content_tasks import fetch_full_content

__all__ = [
    # ... existing exports
    "fetch_full_content",
]
```

- [ ] **Step 3: 验证任务注册**

```bash
uv run python -c "from cyberpulse.tasks import fetch_full_content; print('Task registered')"
```
Expected: "Task registered"

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/tasks/full_content_tasks.py src/cyberpulse/tasks/__init__.py
git commit -m "feat(tasks): add fetch_full_content Dramatiq task"
```

---

### Task 3.2: 修改 quality_check_item 任务

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`

- [ ] **Step 1: 在 quality_check_item 中添加全文获取触发**

在 `quality_check_item` 函数中，在创建 Content 之前添加：

```python
# 在质量检查后、创建 Content 前添加

        # Get source configuration for full fetch decision
        source = db.query(Source).filter(Source.source_id == item.source_id).first()

        needs_full_fetch = source.needs_full_fetch if source else False
        threshold = source.full_fetch_threshold if source and source.full_fetch_threshold else 0.7

        # Check if we need to fetch full content
        completeness = quality_result.metrics.get("content_completeness", 1.0)
        if (needs_full_fetch and
            completeness < threshold and
            not item.full_fetch_attempted):

            logger.info(f"Triggering full content fetch for item: {item_id}")
            from .worker import broker
            fetch_actor = broker.get_actor("fetch_full_content")
            fetch_actor.send(item_id)
            return  # Wait for full fetch before processing further
```

- [ ] **Step 2: 添加必要的导入**

在文件顶部添加：

```python
from ..models import Source
```

- [ ] **Step 3: 验证语法正确**

```bash
uv run python -c "from cyberpulse.tasks.quality_tasks import quality_check_item; print('OK')"
```
Expected: "OK"

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/tasks/quality_tasks.py
git commit -m "feat(tasks): integrate full content fetch trigger in quality_check_item"
```

---

## Phase 4: CLI 增强 (Day 5)

### Task 4.1: 增强源添加命令

**Files:**
- Modify: `src/cyberpulse/cli/commands/source.py`

- [ ] **Step 1: 添加交互式添加流程**

在 `add_source` 命令中添加交互式检测和确认流程：

```python
# 在 add_source 函数中，test 分支内添加质量验证

            # Step 4: Quality Assessment (enhanced)
            console.print("\n[bold]Step 4: Quality Assessment...[/bold]")

            # Use SourceQualityValidator
            from ...services.source_quality_validator import SourceQualityValidator
            validator = SourceQualityValidator()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Validating source quality...", total=None)
                validation_result = asyncio.run(validator.validate_source(config))

            if validation_result.is_valid:
                console.print(f"[green]Quality check passed[/green]")
                console.print(f"  Content completeness: {validation_result.sample_completeness:.2f}")
                console.print(f"  Average content length: {validation_result.avg_content_length} chars")

                # Auto-enable full fetch if needed
                if validation_result.sample_completeness < 0.7:
                    config["needs_full_fetch"] = True
                    console.print("[yellow]Auto-enabled full content fetch (low completeness)[/yellow]")
            else:
                console.print(f"[red]Quality check failed: {validation_result.rejection_reason}[/red]")
                if not (yes or typer.confirm("Add source anyway?")):
                    raise typer.Exit(0)
                config["needs_full_fetch"] = True
```

- [ ] **Step 2: 更新源创建调用**

在创建源时传递新字段：

```python
# 修改 add_source 调用，添加新字段
        source, message = service.add_source(
            name=name,
            connector_type=connector,
            tier=source_tier,
            config=config,
            # New fields
            needs_full_fetch=config.pop("needs_full_fetch", False),
        )
```

- [ ] **Step 3: 更新 SourceService.add_source 签名**

在 `SourceService.add_source` 中添加新参数处理：

```python
# 在 add_source 方法参数中添加
    needs_full_fetch: bool = False,
    full_fetch_threshold: Optional[float] = None,
```

```python
# 在创建 Source 对象时添加
        source = Source(
            # ... existing fields
            needs_full_fetch=needs_full_fetch,
            full_fetch_threshold=full_fetch_threshold,
        )
```

- [ ] **Step 4: 验证 CLI 正常**

```bash
uv run cyber-pulse source --help
```
Expected: Shows help with add command

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/cli/commands/source.py src/cyberpulse/services/source_service.py
git commit -m "feat(cli): enhance source add with quality validation and auto full fetch"
```

---

## Phase 5: 测试 (Day 6)

### Task 5.1: 创建测试样本数据

**Files:**
- Create: `tests/fixtures/rss_samples.py`

- [ ] **Step 1: 创建测试样本**

```python
"""RSS sample data for testing."""

RSS_SAMPLES = {
    "anthropic_research": {
        "url": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
        "expected_issues": ["title_eq_body", "compound_title"],
        "expected_action": "fetch_full_content",
        "expected_completeness": 0.4,
    },
    "krebsonsecurity": {
        "url": "https://krebsonsecurity.com/feed/",
        "expected_issues": [],
        "expected_action": "pass",
        "expected_completeness": 1.0,
    },
    "paulgraham": {
        "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss",
        "expected_issues": ["empty_content"],
        "expected_action": "reject_source",
        "expected_completeness": 0.2,
    },
}

# Mock RSS content for unit tests
MOCK_RSS_FEEDS = {
    "high_quality": """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>High Quality Feed</title>
    <item>
      <title>Article Title</title>
      <description>This is a full article content that is quite long and detailed.</description>
      <link>https://example.com/article1</link>
    </item>
  </channel>
</rss>""",

    "low_quality": """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Low Quality Feed</title>
    <item>
      <title>Short</title>
      <description>Brief</description>
      <link>https://example.com/article1</link>
    </item>
  </channel>
</rss>""",

    "empty": """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <item>
      <title>Title Only</title>
      <description></description>
      <link>https://example.com/article1</link>
    </item>
  </channel>
</rss>""",
}
```

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/rss_samples.py
git commit -m "test: add RSS sample data for testing"
```

---

### Task 5.2: 创建集成测试

**Files:**
- Create: `tests/test_integration/test_full_content_flow.py`

- [ ] **Step 1: 创建集成测试**

```python
"""Integration tests for full content fetch flow."""

import pytest
from unittest.mock import patch, AsyncMock


class TestFullContentFlow:
    """Integration tests for the full content fetch workflow."""

    @pytest.mark.asyncio
    async def test_low_quality_content_triggers_fetch(self, db_session):
        """Test that low quality content triggers full fetch."""
        from cyberpulse.services.source_quality_validator import SourceQualityValidator
        from cyberpulse.services.full_content_fetch_service import FullContentFetchService

        # Create a mock source config with low quality content
        config = {"feed_url": "https://example.com/low-quality.xml"}

        validator = SourceQualityValidator()

        with patch.object(validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": "Short"} for _ in range(5)
            ]

            result = await validator.validate_source(config)

        assert result.is_valid is False
        assert result.sample_completeness < 0.4

    @pytest.mark.asyncio
    async def test_full_fetch_success_flow(self, db_session):
        """Test successful full content fetch flow."""
        from cyberpulse.services.full_content_fetch_service import (
            FullContentFetchService,
            FullContentResult,
        )

        service = FullContentFetchService()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                text="<html><body><p>Full content</p></body></html>",
            )

            with patch("trafilatura.extract") as mock_extract:
                mock_extract.return_value = "Full content"

                result = await service.fetch_full_content("https://example.com/article")

        assert result.success is True
        assert "content" in result.content.lower()

    def test_title_parser_with_anthropic_format(self):
        """Test title parser with Anthropic Research format."""
        from cyberpulse.services.title_parser_service import TitleParserService

        parser = TitleParserService()

        title = "AlignmentDec 18, 2024Alignment faking in large language models"
        result = parser.parse_compound_title(title, source_name="Anthropic Research")

        assert result.category == "Alignment"
        assert result.date == "Dec 18, 2024"
        assert "Alignment faking" in result.title

    @pytest.mark.asyncio
    async def test_full_fetch_timeout(self):
        """Test that timeout is handled gracefully."""
        from cyberpulse.services.full_content_fetch_service import FullContentFetchService
        import httpx

        service = FullContentFetchService()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Connection timeout")

            result = await service.fetch_full_content("https://example.com/slow")

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_full_fetch_4xx_no_retry(self):
        """Test that 4xx errors do not trigger retry."""
        from cyberpulse.services.full_content_fetch_service import FullContentFetchService

        service = FullContentFetchService()

        with patch.object(service, "fetch_full_content") as mock_fetch:
            mock_fetch.return_value = FullContentResult(
                content="",
                success=False,
                error="HTTP error: 404",
            )

            result = await service.fetch_with_retry(
                "https://example.com/notfound",
                max_retries=3,
            )

        # Should only be called once (no retry for 4xx)
        assert mock_fetch.call_count == 1
        assert result.success is False

    def test_title_parser_edge_cases(self):
        """Test title parser with edge cases."""
        from cyberpulse.services.title_parser_service import TitleParserService

        parser = TitleParserService()

        # Empty title
        result = parser.parse_compound_title("")
        assert result.title == ""
        assert result.category is None

        # No matching pattern
        result = parser.parse_compound_title("Simple Title Without Date")
        assert result.title == "Simple Title Without Date"
        assert result.category is None
        assert result.date is None

        # Date in middle of title
        result = parser.parse_compound_title("Some Text Jan 15, 2024 More Text")
        assert result.date == "Jan 15, 2024"
        assert "Jan 15, 2024" not in result.title

    def test_source_governance_triggers_review(self, db_session):
        """Test that high failure rate triggers pending_review."""
        from cyberpulse.models import Source, SourceStatus

        source = Source(
            source_id="src_governance01",
            name="Governance Test",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            full_fetch_success_count=3,
            full_fetch_failure_count=8,  # 8/11 = 72% failure rate
        )
        db_session.add(source)
        db_session.commit()

        # Simulate another failure
        source.full_fetch_failure_count += 1  # 9/12 = 75% failure rate
        total = source.full_fetch_success_count + source.full_fetch_failure_count
        if total >= 10 and source.full_fetch_failure_count / total > 0.5:
            source.pending_review = True
            source.review_reason = "全文获取失败率过高"
        db_session.commit()

        db_session.refresh(source)
        assert source.pending_review is True
        assert "全文获取失败率过高" in source.review_reason
```

- [ ] **Step 2: 运行集成测试**

```bash
uv run pytest tests/test_integration/test_full_content_flow.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration/test_full_content_flow.py
git commit -m "test: add integration tests for full content flow"
```

---

### Task 5.3: 运行完整测试套件

- [ ] **Step 1: 运行所有测试**

```bash
uv run pytest tests/ -v --cov=src/cyberpulse --cov-report=term-missing
```

Expected: All tests pass, coverage >= 80%

- [ ] **Step 2: 运行代码检查**

```bash
uv run ruff check src/ tests/
uv run mypy src/ --ignore-missing-imports
```
Expected: No errors

---

## Summary

本计划实现了以下功能：

| Phase | 内容 | 文件数 |
|-------|------|-------|
| 1 | 数据模型扩展 | 3 |
| 2 | 服务层实现 | 6 |
| 3 | Dramatiq 任务 | 2 |
| 4 | CLI 增强 | 1 |
| 5 | 测试 | 3 |

**总计:** 15 个文件变更

**关键实现点:**
1. Source/Item 模型新增全文获取相关字段
2. FullContentFetchService 负责从 URL 获取全文
3. SourceQualityValidator 验证源质量，拒绝低质量源
4. TitleParserService 解析复合标题（如 Anthropic Research）
5. fetch_full_content 任务异步获取全文
6. quality_check_item 任务集成全文获取触发
7. CLI 支持交互式添加和质量预检测