# RSS 采集错误修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Worker RSS 采集错误，实现重定向跟随、失败追踪和 RSS 自动发现功能。

**Architecture:** 新增 RSSDiscoveryService 模块处理 RSS 自动发现；修改 RSSConnector 启用重定向跟随和 User-Agent；增强 Source 模型添加失败追踪字段；修改 ingestion_tasks 实现失败计数和自动冻结。

**Tech Stack:** Python 3.11+, httpx, beautifulsoup4, SQLAlchemy, Alembic, pytest

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `src/cyberpulse/services/rss_discovery.py` | RSS 自动发现服务 |
| `tests/test_services/test_rss_discovery.py` | RSS 发现服务测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/cyberpulse/services/rss_connector.py` | 启用重定向、添加 UA、返回 FetchResult |
| `src/cyberpulse/models/source.py` | 新增 consecutive_failures, last_error_at 字段 |
| `src/cyberpulse/tasks/ingestion_tasks.py` | 失败追踪、自动冻结、RSS 发现集成 |
| `src/cyberpulse/cli/commands/source.py` | 添加源时支持 site_url 自动发现 |
| `pyproject.toml` | 添加 beautifulsoup4 依赖 |

### 数据库迁移

| 迁移 | 内容 |
|------|------|
| `alembic revision` | 添加 source.consecutive_failures, last_error_at 字段 |

---

## Task 1: 添加 beautifulsoup4 依赖

**Files:**
- Modify: `pyproject.toml`

- [x] **Step 1: 添加依赖**

```bash
uv add beautifulsoup4
```

- [x] **Step 2: 验证依赖添加成功**

```bash
grep "beautifulsoup4" pyproject.toml
```

Expected: 显示 beautifulsoup4 行

- [x] **Step 3: 提交**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add beautifulsoup4 dependency for RSS discovery"
```

---

## Task 2: 实现 RSSDiscoveryService

**Files:**
- Create: `src/cyberpulse/services/rss_discovery.py`
- Create: `tests/test_services/test_rss_discovery.py`

- [x] **Step 1: 编写 RSSDiscoveryService 测试**

```python
# tests/test_services/test_rss_discovery.py
"""Tests for RSS discovery service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


class TestRSSDiscovery:
    """Test RSS auto-discovery functionality."""

    @pytest.mark.asyncio
    async def test_discover_from_html_link(self):
        """Test discovering RSS from HTML link tags."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_excludes_comments_feed(self):
        """Test that comments feeds are excluded in favor of main feed."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="/comments/feed/">
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_returns_none_when_no_rss_found(self):
        """Test that None is returned when no RSS is found."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '<html><head></head></html>'
        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.head = AsyncMock(return_value=MagicMock(status_code=404))

            result = await service.discover("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_discover_handles_relative_urls(self):
        """Test that relative RSS URLs are converted to absolute."""
        from cyberpulse.services.rss_discovery import RSSDiscoveryService

        html = '''<html><head>
            <link rel="alternate" type="application/rss+xml" href="feed.xml">
        </head></html>'''

        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service.discover("https://example.com/blog/")
            assert result == "https://example.com/blog/feed.xml"
```

- [x] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_services/test_rss_discovery.py -v
```

Expected: 测试失败（模块不存在）

- [x] **Step 3: 实现 RSSDiscoveryService**

```python
# src/cyberpulse/services/rss_discovery.py
"""RSS 自动发现服务"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class RSSDiscoveryService:
    """RSS 自动发现服务

    通过两种方式发现 RSS 地址：
    1. 解析首页 HTML 中的 <link rel="alternate" type="application/rss+xml">
    2. 尝试常见 RSS 路径
    """

    COMMON_RSS_PATHS = [
        "/feed/",
        "/rss/",
        "/atom.xml",
        "/feed.xml",
        "/rss.xml",
        "/blog/feed/",
        "/blog/rss/",
    ]

    # 排除的 RSS URL 模式（如 comments feed）
    EXCLUDE_PATTERNS = [
        r"/comments?/feed",
        r"/comment-",
        r"comments\.rss",
    ]

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    TIMEOUT = 15.0

    async def discover(self, site_url: str) -> Optional[str]:
        """从网站发现 RSS 地址

        Args:
            site_url: 网站首页 URL

        Returns:
            发现的 RSS URL，或 None
        """
        # 方法 1：解析首页 RSS link
        rss_url = await self._discover_from_html(site_url)
        if rss_url:
            logger.info(f"Discovered RSS from HTML: {rss_url}")
            return rss_url

        # 方法 2：尝试常见路径
        rss_url = await self._discover_from_common_paths(site_url)
        if rss_url:
            logger.info(f"Discovered RSS from common path: {rss_url}")
            return rss_url

        logger.warning(f"No RSS found for site: {site_url}")
        return None

    async def _discover_from_html(self, site_url: str) -> Optional[str]:
        """从 HTML 解析 RSS link"""
        try:
            async with httpx.AsyncClient(
                timeout=self.TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    site_url,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
                )
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            rss_links = []

            for link in soup.find_all("link", rel="alternate"):
                link_type = link.get("type", "")
                if link_type in ("application/rss+xml", "application/atom+xml"):
                    href = link.get("href")
                    if href:
                        # 处理相对路径
                        if href.startswith("/"):
                            href = urljoin(site_url, href)
                        elif not href.startswith(("http://", "https://")):
                            href = urljoin(site_url, href)
                        rss_links.append(href)

            # 排除 comments feed
            for rss_url in rss_links:
                if not any(re.search(p, rss_url, re.I) for p in self.EXCLUDE_PATTERNS):
                    return rss_url

            # 如果只有 comments feed，返回第一个
            return rss_links[0] if rss_links else None

        except Exception as e:
            logger.debug(f"Failed to discover RSS from HTML: {e}")
            return None

    async def _discover_from_common_paths(self, site_url: str) -> Optional[str]:
        """尝试常见 RSS 路径"""
        parsed = urlparse(site_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        async with httpx.AsyncClient(
            timeout=self.TIMEOUT,
            follow_redirects=True,
        ) as client:
            for path in self.COMMON_RSS_PATHS:
                test_url = base_url + path
                try:
                    response = await client.head(
                        test_url,
                        headers={"User-Agent": self.DEFAULT_USER_AGENT},
                    )
                    if response.status_code == 200:
                        content_type = response.headers.get("content-type", "")
                        if "xml" in content_type or "rss" in content_type:
                            return test_url
                except Exception:
                    continue

        return None
```

- [x] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_services/test_rss_discovery.py -v
```

Expected: 所有测试通过

- [x] **Step 5: 提交**

```bash
git add src/cyberpulse/services/rss_discovery.py tests/test_services/test_rss_discovery.py
git commit -m "feat: add RSSDiscoveryService for automatic RSS feed discovery"
```

---

## Task 3: 增强 Source 模型

**Files:**
- Modify: `src/cyberpulse/models/source.py`

- [x] **Step 1: 编写模型字段测试**

```python
# tests/test_models/test_source_fields.py
"""Tests for Source model fields."""

import pytest
from cyberpulse.models import Source, SourceStatus


class TestSourceFailureTracking:
    """Test Source failure tracking fields."""

    def test_source_has_consecutive_failures_field(self, db_session):
        """Test that Source has consecutive_failures field with default 0."""
        source = Source(
            source_id="src_test01",
            name="Test Source",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        db_session.refresh(source)
        assert source.consecutive_failures == 0

    def test_source_has_last_error_at_field(self, db_session):
        """Test that Source has last_error_at field."""
        from datetime import datetime, timezone

        source = Source(
            source_id="src_test02",
            name="Test Source 2",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        # Set last_error_at
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source.last_error_at = now
        db_session.commit()

        db_session.refresh(source)
        assert source.last_error_at is not None
```

- [x] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models/test_source_fields.py -v
```

Expected: 测试失败（字段不存在）

- [x] **Step 3: 添加模型字段**

```python
# src/cyberpulse/models/source.py
# 在现有字段后添加:

    # Statistics
    last_fetched_at = Column(DateTime, nullable=True)
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)
    total_contents = Column(Integer, nullable=False, default=0)

    # Failure tracking
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error_at = Column(DateTime, nullable=True)
```

- [x] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models/test_source_fields.py -v
```

Expected: 测试通过

- [x] **Step 5: 创建数据库迁移**

```bash
uv run alembic revision --autogenerate -m "add source failure tracking fields"
```

- [x] **Step 6: 验证迁移文件**

```bash
ls -la alembic/versions/ | tail -1
```

Expected: 显示新创建的迁移文件

- [x] **Step 7: 提交**

```bash
git add src/cyberpulse/models/source.py tests/test_models/test_source_fields.py alembic/versions/
git commit -m "feat: add consecutive_failures and last_error_at fields to Source model"
```

---

## Task 4: 增强 RSSConnector

**Files:**
- Modify: `src/cyberpulse/services/rss_connector.py`
- Create: `tests/test_services/test_rss_connector_enhanced.py`

- [x] **Step 1: 编写 RSSConnector 增强测试**

```python
# tests/test_services/test_rss_connector_enhanced.py
"""Tests for enhanced RSS connector."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx


class TestRSSConnectorEnhanced:
    """Test RSS connector enhancements."""

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        """Test that fetch returns FetchResult with items and redirect_info."""
        from cyberpulse.services.rss_connector import RSSConnector, FetchResult

        connector = RSSConnector({"feed_url": "https://example.com/feed/"})

        # Mock successful response
        rss_content = b'''<?xml version="1.0"?>
        <rss><channel><title>Test</title>
        <item><title>Item 1</title><link>https://example.com/1</link><guid>1</guid></item>
        </channel></rss>'''

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = rss_content
            mock_response.url = "https://example.com/feed/"
            mock_response.history = []
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) == 1
        assert result.redirect_info is None

    @pytest.mark.asyncio
    async def test_fetch_detects_permanent_redirect(self):
        """Test that fetch detects 301 redirect and returns redirect_info."""
        from cyberpulse.services.rss_connector import RSSConnector, FetchResult

        connector = RSSConnector({"feed_url": "https://old.example.com/feed/"})

        rss_content = b'''<?xml version="1.0"?>
        <rss><channel><title>Test</title></channel></rss>'''

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            # Mock redirect history
            mock_hist = MagicMock()
            mock_hist.status_code = 301

            mock_response = MagicMock()
            mock_response.content = rss_content
            mock_response.url = "https://new.example.com/feed/"
            mock_response.history = [mock_hist]
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert result.redirect_info is not None
        assert result.redirect_info["status_code"] == 301
        assert result.redirect_info["original_url"] == "https://old.example.com/feed/"
        assert result.redirect_info["final_url"] == "https://new.example.com/feed/"

    @pytest.mark.asyncio
    async def test_fetch_includes_user_agent(self):
        """Test that fetch includes default User-Agent header."""
        from cyberpulse.services.rss_connector import RSSConnector

        connector = RSSConnector({"feed_url": "https://example.com/feed/"})

        with patch.object(httpx.AsyncClient, '__aenter__') as mock_enter:
            mock_client = MagicMock()
            mock_enter.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = b'<rss><channel></channel></rss>'
            mock_response.url = "https://example.com/feed/"
            mock_response.history = []
            mock_response.raise_for_status = MagicMock()

            mock_client.get = AsyncMock(return_value=mock_response)

            await connector.fetch()

            # Verify User-Agent was set
            call_args = mock_client.get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "User-Agent" in headers
            assert "Mozilla" in headers["User-Agent"]
```

- [x] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_services/test_rss_connector_enhanced.py -v
```

Expected: 测试失败（FetchResult 不存在）

- [x] **Step 3: 添加 FetchResult 数据类和增强 fetch 方法**

```python
# src/cyberpulse/services/rss_connector.py
# 在文件开头导入部分添加:

from dataclasses import dataclass
from typing import Optional

# 在 RSSConnector 类定义前添加:

@dataclass
class FetchResult:
    """RSS 采集结果"""
    items: list
    redirect_info: Optional[dict] = None  # {"original_url": "...", "final_url": "...", "status_code": 301}


class RSSConnector(BaseConnector):
    """Connector for RSS/Atom feeds."""

    MAX_ITEMS = 50
    REQUIRED_CONFIG_KEYS = ["feed_url"]

    # 默认浏览器 User-Agent
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # ... 保持 validate_config 不变 ...

    async def fetch(self) -> FetchResult:
        """Fetch items from the RSS feed.

        Returns:
            FetchResult with items and optional redirect_info

        Raises:
            ConnectorError: If feed cannot be fetched or parsed
        """
        self.validate_config()

        feed_url = self.config["feed_url"]

        try:
            # SSRF protection: fetch content via httpx with redirect following
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,  # 启用重定向跟随
            ) as client:
                response = await client.get(
                    feed_url,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
                )

                # Validate the final URL (in case of redirects)
                final_url = str(response.url)
                if final_url != feed_url:
                    try:
                        validate_url_for_ssrf(final_url)
                    except SSRFError as e:
                        raise ConnectorError(
                            f"RSS feed redirect to blocked URL: {e}"
                        ) from e

                response.raise_for_status()
                content = response.content

            # 检测永久重定向
            redirect_info = None
            if response.history:
                for hist in response.history:
                    if hist.status_code in (301, 308):
                        redirect_info = {
                            "original_url": feed_url,
                            "final_url": final_url,
                            "status_code": hist.status_code,
                        }
                        logger.info(
                            f"RSS feed permanently redirected: {feed_url} -> {final_url}"
                        )
                        break

            # Parse the fetched content with feedparser
            feed = feedparser.parse(content)

        except httpx.HTTPStatusError as e:
            raise ConnectorError(
                f"Failed to fetch RSS feed '{feed_url}': HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ConnectorError(
                f"Failed to fetch RSS feed '{feed_url}': {type(e).__name__}: {e}"
            ) from e
        except Exception as e:
            raise ConnectorError(
                f"Failed to fetch RSS feed '{feed_url}': {type(e).__name__}: {e}"
            ) from e

        # Check for fatal errors (not bozo errors, which we tolerate)
        if feed.get("bozo") and not isinstance(
            feed.get("bozo_exception"), feedparser.NonXMLContentType
        ):
            logger.warning(
                f"RSS feed '{feed_url}' has malformed content: {feed.get('bozo_exception')}"
            )

        # Get entries, limited to MAX_ITEMS
        entries = feed.get("entries", [])[: self.MAX_ITEMS]

        items = []
        for entry in entries:
            try:
                item = self._parse_entry(entry)
                if item:
                    items.append(item)
            except Exception as e:
                entry_id = (
                    entry.get("guid")
                    or entry.get("id")
                    or entry.get("link")
                    or "unknown"
                )
                logger.warning(
                    f"Skipping malformed RSS entry '{entry_id}' from '{feed_url}': {e}"
                )
                continue

        return FetchResult(items=items, redirect_info=redirect_info)
```

- [x] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_services/test_rss_connector_enhanced.py -v
```

Expected: 所有测试通过

- [x] **Step 5: 运行现有 RSS connector 测试确保无回归**

```bash
uv run pytest tests/test_services/test_rss_connector.py -v
```

Expected: 所有测试通过（可能需要更新部分测试以适配 FetchResult）

- [x] **Step 6: 提交**

```bash
git add src/cyberpulse/services/rss_connector.py tests/test_services/test_rss_connector_enhanced.py
git commit -m "feat: enhance RSSConnector with redirect following and User-Agent"
```

---

## Task 5: 增强采集任务

**Files:**
- Modify: `src/cyberpulse/tasks/ingestion_tasks.py`
- Create: `tests/test_tasks/test_ingestion_enhanced.py`

- [x] **Step 1: 编写采集任务增强测试**

```python
# tests/test_tasks/test_ingestion_enhanced.py
"""Tests for enhanced ingestion tasks."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from cyberpulse.models import Source, SourceStatus
from cyberpulse.services.connector_service import ConnectorError


class TestIngestionFailureTracking:
    """Test ingestion failure tracking."""

    # Note: db_session fixture is provided by tests/conftest.py

    def test_skips_frozen_source(self, db_session):
        """Test that frozen sources are skipped."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source

        source = Source(
            source_id="src_frozen01",
            name="Frozen Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.FROZEN,
            consecutive_failures=5,
        )
        db_session.add(source)
        db_session.commit()

        # Should not raise and should not try to fetch
        ingest_source("src_frozen01")

    def test_increments_consecutive_failures(self, db_session):
        """Test that consecutive_failures is incremented on error."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source

        source = Source(
            source_id="src_fail01",
            name="Fail Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=0,
        )
        db_session.add(source)
        db_session.commit()

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 404")

            with pytest.raises(ConnectorError):
                ingest_source("src_fail01")

        db_session.refresh(source)
        assert source.consecutive_failures == 1
        assert source.last_error_at is not None

    def test_freezes_after_max_failures(self, db_session):
        """Test that source is frozen after MAX_CONSECUTIVE_FAILURES."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source, MAX_CONSECUTIVE_FAILURES

        source = Source(
            source_id="src_freeze01",
            name="To Freeze Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=MAX_CONSECUTIVE_FAILURES - 1,
        )
        db_session.add(source)
        db_session.commit()

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 404")

            with pytest.raises(ConnectorError):
                ingest_source("src_freeze01")

        db_session.refresh(source)
        assert source.status == SourceStatus.FROZEN
        assert "连续采集失败" in source.review_reason

    def test_resets_failures_on_success(self, db_session):
        """Test that consecutive_failures is reset on successful fetch."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult

        source = Source(
            source_id="src_success01",
            name="Success Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=3,
        )
        db_session.add(source)
        db_session.commit()

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=None)

            ingest_source("src_success01")

        db_session.refresh(source)
        assert source.consecutive_failures == 0

    def test_updates_feed_url_on_redirect(self, db_session):
        """Test that feed_url is updated on permanent redirect."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult

        source = Source(
            source_id="src_redirect01",
            name="Redirect Source",
            connector_type="rss",
            config={"feed_url": "https://old.example.com/feed/"},
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        redirect_info = {
            "original_url": "https://old.example.com/feed/",
            "final_url": "https://new.example.com/feed/",
            "status_code": 301,
        }

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=redirect_info)

            ingest_source("src_redirect01")

        db_session.refresh(source)
        assert source.config["feed_url"] == "https://new.example.com/feed/"

    def test_temporary_redirect_does_not_update_url(self, db_session):
        """Test that 302/307 redirects are followed but URL is not updated."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source
        from cyberpulse.services.rss_connector import FetchResult

        source = Source(
            source_id="src_temp_redirect01",
            name="Temp Redirect Source",
            connector_type="rss",
            config={"feed_url": "https://old.example.com/feed/"},
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        # 302 temporary redirect
        redirect_info = {
            "original_url": "https://old.example.com/feed/",
            "final_url": "https://new.example.com/feed/",
            "status_code": 302,
        }

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=redirect_info)

            ingest_source("src_temp_redirect01")

        db_session.refresh(source)
        # URL should NOT be updated for temporary redirect
        assert source.config["feed_url"] == "https://old.example.com/feed/"

    def test_consecutive_failures_boundary(self, db_session):
        """Test consecutive_failures at boundary values (4 and 5)."""
        from cyberpulse.tasks.ingestion_tasks import ingest_source, MAX_CONSECUTIVE_FAILURES

        # Test at MAX - 1 (should not freeze)
        source = Source(
            source_id="src_boundary01",
            name="Boundary Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=MAX_CONSECUTIVE_FAILURES - 2,  # 3
        )
        db_session.add(source)
        db_session.commit()

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 500")

            with pytest.raises(ConnectorError):
                ingest_source("src_boundary01")

        db_session.refresh(source)
        # After 1 failure, should be at 4 (MAX - 1), not frozen
        assert source.consecutive_failures == MAX_CONSECUTIVE_FAILURES - 1
        assert source.status == SourceStatus.ACTIVE
```

- [x] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_tasks/test_ingestion_enhanced.py -v
```

Expected: 测试失败（功能未实现）

- [x] **Step 3: 增强 ingestion_tasks.py**

```python
# src/cyberpulse/tasks/ingestion_tasks.py
# 在文件开头添加导入:

from ..services.rss_connector import FetchResult
from ..services.rss_discovery import RSSDiscoveryService

# 在文件中添加常量:

MAX_CONSECUTIVE_FAILURES = 5

# 修改 ingest_source 函数:

@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str) -> None:
    """Ingest items from a source.

    This task:
    1. Gets source from database
    2. Skips if source is FROZEN
    3. Uses connector to fetch items
    4. Handles redirect and updates feed_url
    5. Creates Item records
    6. Tracks failures and freezes source if needed

    Args:
        source_id: The source ID to ingest from.
    """
    db = SessionLocal()
    try:
        # Get source from database
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            logger.error(f"Source not found: {source_id}")
            return

        # Skip frozen sources
        if source.status == SourceStatus.FROZEN:
            logger.debug(f"Skipping frozen source: {source.name}")
            return

        logger.info(f"Starting ingestion for source: {source.name} ({source_id})")

        # Create connector for this source
        connector = get_connector_for_source(source)

        # Fetch items using async connector
        result = asyncio.run(_fetch_items(connector, None))

        # Handle both FetchResult and legacy list return
        if isinstance(result, FetchResult):
            items_data = result.items
            redirect_info = result.redirect_info
        else:
            items_data = result
            redirect_info = None

        # Handle permanent redirect
        if redirect_info:
            logger.info(
                f"Updating source URL: {redirect_info['original_url']} -> {redirect_info['final_url']}"
            )
            source.config["feed_url"] = redirect_info["final_url"]

        # Reset failure count on success
        source.consecutive_failures = 0

        if not items_data:
            logger.info(f"No items fetched from source: {source.name}")
            source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            return

        logger.info(f"Fetched {len(items_data)} items from source: {source.name}")

        # Create ItemService and process items
        item_service = ItemService(db)
        new_items = []
        failed_count = 0

        for item_data in items_data:
            try:
                item = item_service.create_item(
                    source_id=source_id,
                    external_id=item_data["external_id"],
                    url=item_data["url"],
                    title=item_data["title"],
                    raw_content=item_data.get("content", ""),
                    published_at=item_data["published_at"],
                    content_hash=item_data["content_hash"],
                    raw_metadata={
                        "author": item_data.get("author", ""),
                        "tags": item_data.get("tags", []),
                    },
                )

                if item is not None and item.status.value == ItemStatus.NEW.value:
                    new_items.append(item)

            except IntegrityError as e:
                db.rollback()
                logger.warning(
                    f"Duplicate item detected from source {source_id}: {e}",
                    exc_info=True
                )
                continue
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(
                    f"Invalid item data from source {source_id}: {e}",
                    exc_info=True
                )
                failed_count += 1
                continue
            except SQLAlchemyError as e:
                logger.error(
                    f"Database error creating item from source {source_id}: {e}",
                    exc_info=True
                )
                raise

        # Update source statistics
        source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        source.total_items = (source.total_items or 0) + len(new_items)
        db.commit()

        duplicate_count = len(items_data) - len(new_items) - failed_count
        logger.info(
            f"Ingestion complete for {source.name}: "
            f"{len(new_items)} new items, {duplicate_count} duplicates, "
            f"{failed_count} failed"
        )

        # Queue normalization for each new item
        for item in new_items:
            normalize_actor = broker.get_actor("normalize_item")
            normalize_actor.send(item.item_id)
            logger.debug(f"Queued normalization for item: {item.item_id}")

    except Exception as e:
        logger.error(f"Ingestion failed for source {source_id}: {e}", exc_info=True)

        # Try RSS discovery for RSS sources
        if source and source.connector_type == "rss":
            try:
                new_feed_url = asyncio.run(_try_discover_rss(source))
                if new_feed_url:
                    logger.info(
                        f"Discovered new RSS URL for source {source_id}: {new_feed_url}"
                    )
                    source.config["feed_url"] = new_feed_url
                    source.consecutive_failures = 0
                    db.commit()
                    return
            except Exception as discover_error:
                logger.warning(f"RSS discovery failed: {discover_error}")

        # Update failure tracking
        if source:
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            source.last_error_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Check if should freeze
            if source.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                source.status = SourceStatus.FROZEN
                source.review_reason = f"连续采集失败: {str(e)[:100]}"
                logger.warning(
                    f"Source {source_id} frozen after {source.consecutive_failures} consecutive failures"
                )

        db.rollback()
        raise

    finally:
        db.close()


async def _try_discover_rss(source: Source) -> str | None:
    """Try to discover new RSS URL for a source.

    Args:
        source: Source object with config containing feed_url

    Returns:
        New RSS URL if found, None otherwise
    """
    feed_url = source.config.get("feed_url", "")
    if not feed_url:
        return None

    # Extract site URL from feed URL
    parsed = urlparse(feed_url)
    site_url = f"{parsed.scheme}://{parsed.netloc}"

    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)
```

- [x] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_tasks/test_ingestion_enhanced.py -v
```

Expected: 所有测试通过

- [x] **Step 5: 运行现有测试确保无回归**

```bash
uv run pytest tests/test_tasks/ -v
```

Expected: 所有测试通过

- [x] **Step 6: 提交**

```bash
git add src/cyberpulse/tasks/ingestion_tasks.py tests/test_tasks/test_ingestion_enhanced.py
git commit -m "feat: add failure tracking and auto-freeze to ingestion tasks"
```

---

## Task 6: CLI 添加源增强 (P1)

**Files:**
- Modify: `src/cyberpulse/cli/commands/source.py`

- [x] **Step 1: 添加 RSS 发现辅助函数**

```python
# src/cyberpulse/cli/commands/source.py
# 在文件中添加:

def _looks_like_feed_url(url: str) -> bool:
    """Check if URL looks like an RSS feed URL.

    Args:
        url: URL to check

    Returns:
        True if URL appears to be a feed URL
    """
    feed_patterns = ["/feed", "/rss", ".xml", ".rss", "/atom"]
    return any(p in url.lower() for p in feed_patterns)


async def _discover_rss_for_cli(site_url: str) -> Optional[str]:
    """Discover RSS URL for a site (CLI helper).

    Args:
        site_url: Site URL to discover RSS from

    Returns:
        Discovered RSS URL or None
    """
    from ...services.rss_discovery import RSSDiscoveryService
    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)
```

- [x] **Step 2: 修改 add_source 命令**

在 `add_source` 函数中，找到准备 config 的部分（约第 217-226 行），替换为：

```python
        # Prepare config based on connector type
        config: dict = {}
        if connector == "rss":
            # Check if URL looks like a feed URL or site URL
            if _looks_like_feed_url(url):
                config = {"feed_url": url}
            else:
                # Try to discover RSS from site URL
                console.print(f"[cyan]Discovering RSS feed from {url}...[/cyan]")
                feed_url = asyncio.run(_discover_rss_for_cli(url))
                if feed_url:
                    config = {"feed_url": feed_url}
                    console.print(f"[green]Found RSS: {feed_url}[/green]")
                else:
                    console.print(f"[yellow]Could not discover RSS, using URL as feed_url[/yellow]")
                    config = {"feed_url": url}
        elif connector == "api":
            config = {"url": url}
        elif connector == "web":
            config = {"url": url}
        elif connector == "media":
            config = {"url": url}
```

- [x] **Step 3: 手动测试 CLI**

```bash
# 测试自动发现（使用一个已知有 RSS 的网站）
uv run cyber-pulse source add "Test Discovery" rss "https://www.microsoft.com/en-us/security/blog" --no-test -y

# 验证
uv run cyber-pulse source list --format yaml | grep -A5 "Test Discovery"
```

Expected: 显示发现的 RSS URL

- [x] **Step 4: 提交**

```bash
git add src/cyberpulse/cli/commands/source.py
git commit -m "feat: add RSS auto-discovery when adding sources"
```

---

## Task 7: 集成测试和验证

- [x] **Step 1: 运行全部测试**

```bash
uv run pytest -v
```

Expected: 所有测试通过

- [x] **Step 2: 运行代码检查**

```bash
uv run ruff check src/ tests/
uv run mypy src/ --ignore-missing-imports
```

Expected: 无错误

- [x] **Step 3: 更新 CHANGELOG**

在 `CHANGELOG.md` 中添加：

```markdown
## [Unreleased]

### Added
- RSS auto-discovery service for finding RSS feeds from site URLs
- Source failure tracking with `consecutive_failures` and `last_error_at` fields
- Automatic source freezing after 5 consecutive failures
- RSS feed URL auto-update on permanent redirect (301/308)

### Fixed
- HTTP redirect handling in RSS connector (now follows redirects)
- Missing User-Agent header causing 403 errors
```

- [x] **Step 4: 最终提交**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for RSS ingestion error fix"
```

---

## 验收标准

- [ ] 所有测试通过 (`uv run pytest`)
- [ ] 代码检查通过 (`uv run ruff check`, `uv run mypy`)
- [ ] 数据库迁移已创建
- [ ] CHANGELOG 已更新
- [ ] Issue #42 可关闭

---

## 回滚计划

如果出现问题，可以：

1. **数据库回滚**：
   ```bash
   uv run alembic downgrade -1
   ```

2. **代码回滚**：
   ```bash
   git revert <commit-hash>
   ```

3. **手动解冻源**：
   ```bash
   uv run cyber-pulse source update <source_id> --status ACTIVE
   ```