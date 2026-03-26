# Design: RSS 采集错误修复

**Issue**: #42
**Date**: 2026-03-25
**Status**: Draft

## 问题概述

Worker 产生大量 RSS 采集错误，主要类型：

| 错误类型 | 次数 | 占比 |
|---------|------|------|
| HTTP 301/302/308 | 1353 | 81% |
| HTTP 403 | 225 | 14% |
| ConnectError | 84 | 5% |
| **总计** | **1662** | 100% |

## 根因分析

### 问题 1：HTTP 重定向错误（81%）

**当前代码**（`rss_connector.py:67`）：
```python
async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
    response = await client.get(feed_url)
    response.raise_for_status()
```

**根因**：`follow_redirects=False` 禁用了重定向跟随，遇到 301/302 直接报错。

**设计意图 vs 实现**：
- 设计意图：先验证重定向后的 URL 是否安全（SSRF 防护）
- 实际行为：从未跟随重定向，后续验证代码（第 72-77 行）永不执行

### 问题 2：HTTP 403 禁止访问（14%）

**根因**：缺少 User-Agent 请求头，被识别为爬虫。

### 问题 3：失败源无限重试（5%）

**根因**：无连续失败计数和自动冻结机制，持续重试无效源。

### 问题 4：RSS 地址废弃

**根因**：网站迁移后旧 RSS 地址失效（HTTP 404/000），无法自动恢复。

## 解决方案

### 方案架构

```
┌─────────────────────────────────────────────────────────────┐
│                     RSSConnector.fetch()                    │
├─────────────────────────────────────────────────────────────┤
│  1. 启用 follow_redirects=True + SSRF 校验                  │
│  2. 默认浏览器 User-Agent                                    │
│  3. 检测永久重定向 → 返回 redirect_info                      │
│  4. 错误时调用 RSS 发现模块                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   RSSDiscoveryService                        │
├─────────────────────────────────────────────────────────────┤
│  1. 从首页 HTML 解析 RSS link                                │
│  2. 尝试常见 RSS 路径                                        │
│  3. 返回发现的 RSS URL 或 None                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    ingestion_tasks.py                        │
├─────────────────────────────────────────────────────────────┤
│  1. 处理 redirect_info → 自动更新 feed_url                   │
│  2. 采集成功 → 重置 consecutive_failures = 0                 │
│  3. 采集失败 → consecutive_failures += 1                     │
│  4. 连续失败 >= 5 → 冻结源                                   │
└─────────────────────────────────────────────────────────────┘
```

### P0 实现

#### 1. RSSConnector 增强

**文件**：`src/cyberpulse/services/rss_connector.py`

**改动**：

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class FetchResult:
    """RSS 采集结果"""
    items: List[Dict[str, Any]]
    redirect_info: Optional[Dict[str, str]] = None  # {"original_url": "...", "final_url": "...", "status_code": 301}

class RSSConnector(BaseConnector):
    # 默认浏览器 User-Agent
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from the RSS feed.

        改动：
        1. 启用 follow_redirects=True
        2. 添加默认 User-Agent
        3. 检测永久重定向
        4. 返回 FetchResult 而非纯列表
        """
        self.validate_config()
        feed_url = self.config["feed_url"]

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,  # 启用重定向跟随
            ) as client:
                response = await client.get(
                    feed_url,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
                )

                # SSRF 校验：验证最终 URL 是否安全
                final_url = str(response.url)
                if final_url != feed_url:
                    try:
                        validate_url_for_ssrf(final_url)
                    except SSRFError as e:
                        raise ConnectorError(f"RSS feed redirect to blocked URL: {e}") from e

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
                        logger.info(f"RSS feed permanently redirected: {feed_url} -> {final_url}")
                        break

            # 解析 RSS
            feed = feedparser.parse(content)
            items = self._parse_feed(feed, feed_url)

            return FetchResult(items=items, redirect_info=redirect_info)

        except httpx.HTTPStatusError as e:
            raise ConnectorError(f"Failed to fetch RSS feed '{feed_url}': HTTP {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise ConnectorError(f"Failed to fetch RSS feed '{feed_url}': {type(e).__name__}") from e
```

#### 2. RSS 自动发现模块

**文件**：`src/cyberpulse/services/rss_discovery.py`

```python
"""RSS 自动发现服务"""

import logging
import re
from typing import Optional, List
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

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
            async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
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

    async def _validate_rss_url(self, url: str) -> bool:
        """验证 URL 是否为有效的 RSS/Atom feed

        Args:
            url: 待验证的 URL

        Returns:
            True 如果是有效的 RSS/Atom feed
        """
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": self.DEFAULT_USER_AGENT},
                )
                response.raise_for_status()

                # 检查 Content-Type
                content_type = response.headers.get("content-type", "").lower()
                if "xml" in content_type or "rss" in content_type or "atom" in content_type:
                    return True

                # 检查内容是否以 XML 声明或 RSS/Atom 标签开头
                content_start = response.content[:500].decode("utf-8", errors="ignore").strip()
                if content_start.startswith("<?xml") or "<rss" in content_start.lower() or "<feed" in content_start.lower():
                    return True

                return False

        except Exception as e:
            logger.debug(f"RSS validation failed for {url}: {e}")
            return False

    async def _discover_from_common_paths(self, site_url: str) -> Optional[str]:
        """尝试常见 RSS 路径"""
        parsed = urlparse(site_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
            for path in self.COMMON_RSS_PATHS:
                test_url = base_url + path
                try:
                    # 使用 GET 而非 HEAD，以便验证内容
                    response = await client.get(
                        test_url,
                        headers={"User-Agent": self.DEFAULT_USER_AGENT},
                    )
                    if response.status_code == 200:
                        # 验证是否为有效的 RSS
                        if await self._validate_rss_url(test_url):
                            return test_url
                except Exception:
                    continue

        return None
```

#### 3. Source 模型增强

**文件**：`src/cyberpulse/models/source.py`

**新增字段**：

```python
class Source(Base, TimestampMixin):
    # ... 现有字段 ...

    # 失败追踪
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error_at = Column(DateTime, nullable=True)
```

**数据库迁移**：

```bash
alembic revision --autogenerate -m "add source failure tracking fields"
```

#### 4. 采集任务增强

**文件**：`src/cyberpulse/tasks/ingestion_tasks.py`

```python
from ..services.rss_discovery import RSSDiscoveryService

# 冻结阈值
MAX_CONSECUTIVE_FAILURES = 5


@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str) -> None:
    """Ingest items from a source."""
    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            logger.error(f"Source not found: {source_id}")
            return

        # 跳过冻结源
        if source.status == SourceStatus.FROZEN:
            logger.debug(f"Skipping frozen source: {source.name}")
            return

        logger.info(f"Starting ingestion for source: {source.name} ({source_id})")

        connector = get_connector_for_source(source)
        result = asyncio.run(_fetch_items(connector, source))

        if isinstance(result, FetchResult):
            items_data = result.items
            redirect_info = result.redirect_info
        else:
            # 兼容旧版本 connector
            items_data = result
            redirect_info = None

        # 处理永久重定向
        if redirect_info:
            logger.info(f"Updating source URL: {redirect_info['original_url']} -> {redirect_info['final_url']}")
            source.config["feed_url"] = redirect_info["final_url"]

        # 采集成功，重置失败计数
        source.consecutive_failures = 0
        source.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # ... 创建 items 逻辑不变 ...

        db.commit()

    except ConnectorError as e:
        logger.error(f"Ingestion failed for source {source_id}: {e}")

        # 尝试 RSS 自动发现
        if source.connector_type == "rss":
            new_feed_url = asyncio.run(_try_discover_rss(source))
            if new_feed_url:
                logger.info(f"Discovered new RSS URL for source {source_id}: {new_feed_url}")
                source.config["feed_url"] = new_feed_url
                source.consecutive_failures = 0
                db.commit()
                return

        # 更新失败计数
        source.consecutive_failures += 1
        source.last_error_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 检查是否需要冻结
        if source.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            source.status = SourceStatus.FROZEN
            source.review_reason = f"连续采集失败: {str(e)[:100]}"
            logger.warning(f"Source {source_id} frozen after {source.consecutive_failures} consecutive failures")

        db.commit()
        raise

    finally:
        db.close()


async def _try_discover_rss(source: Source) -> Optional[str]:
    """尝试发现新的 RSS 地址"""
    feed_url = source.config.get("feed_url", "")
    if not feed_url:
        return None

    # 从当前 feed_url 提取网站首页
    parsed = urlparse(feed_url)
    site_url = f"{parsed.scheme}://{parsed.netloc}"

    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)
```

### P1 实现

#### 添加源时自动发现 RSS

**文件**：`src/cyberpulse/cli/commands/source.py`

```python
@app.command("add")
def add_source(
    name: str = typer.Argument(..., help="Source name"),
    connector: str = typer.Argument(..., help="Connector type (rss, api, web, media)"),
    url: str = typer.Argument(..., help="Source URL, feed URL, or site URL"),
    # ... 其他参数 ...
) -> None:
    """Add a new source with full onboarding flow."""

    # 准备配置
    config: dict = {}
    if connector == "rss":
        # 判断是 feed_url 还是 site_url
        if _looks_like_feed_url(url):
            config["feed_url"] = url
        else:
            # 自动发现 RSS
            console.print(f"[cyan]Discovering RSS feed from {url}...[/cyan]")
            feed_url = asyncio.run(_discover_rss(url))
            if feed_url:
                config["feed_url"] = feed_url
                console.print(f"[green]Found RSS: {feed_url}[/green]")
            else:
                console.print(f"[yellow]Could not discover RSS, using URL as feed_url[/yellow]")
                config["feed_url"] = url
    # ... 其他 connector 类型 ...


def _looks_like_feed_url(url: str) -> bool:
    """判断 URL 是否看起来像 RSS feed"""
    feed_patterns = ["/feed", "/rss", ".xml", ".rss", "/atom"]
    return any(p in url.lower() for p in feed_patterns)


async def _discover_rss(site_url: str) -> Optional[str]:
    """发现 RSS 地址"""
    from ...services.rss_discovery import RSSDiscoveryService
    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)
```

## 测试计划

### 单元测试

**文件**：`tests/test_services/test_rss_discovery.py`

```python
"""Tests for RSS discovery service."""

import pytest
from unittest.mock import AsyncMock, patch

from cyberpulse.services.rss_discovery import RSSDiscoveryService


class TestRSSDiscovery:
    """Test RSS auto-discovery functionality."""

    @pytest.mark.asyncio
    async def test_discover_from_html(self):
        """Test discovering RSS from HTML link tags."""
        html = '''
        <html>
        <head>
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head>
        </html>
        '''
        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.text = html
            mock_get.return_value.raise_for_status = lambda: None

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_excludes_comments_feed(self):
        """Test that comments feeds are excluded."""
        html = '''
        <html>
        <head>
            <link rel="alternate" type="application/rss+xml" href="/comments/feed/">
            <link rel="alternate" type="application/rss+xml" href="/feed/">
        </head>
        </html>
        '''
        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value.text = html
            mock_get.return_value.raise_for_status = lambda: None

            result = await service.discover("https://example.com")
            assert result == "https://example.com/feed/"

    @pytest.mark.asyncio
    async def test_discover_from_common_paths(self):
        """Test discovering RSS from common paths."""
        service = RSSDiscoveryService()

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock):
            with patch.object(httpx.AsyncClient, 'head', new_callable=AsyncMock) as mock_head:
                # Simulate /feed/ returning 200
                mock_head.return_value.status_code = 200
                mock_head.return_value.headers = {"content-type": "application/rss+xml"}

                result = await service.discover("https://example.com")
                # Should find /feed/ first
                assert "/feed/" in result
```

### 集成测试

**文件**：`tests/test_tasks/test_ingestion_with_discovery.py`

```python
"""Tests for ingestion with RSS discovery."""

import pytest
from unittest.mock import patch, MagicMock

from cyberpulse.tasks.ingestion_tasks import ingest_source, MAX_CONSECUTIVE_FAILURES
from cyberpulse.models import Source, SourceStatus


class TestIngestionWithDiscovery:
    """Test ingestion with automatic RSS discovery."""

    def test_consecutive_failures_increment(self, db_session):
        """Test that consecutive failures are tracked."""
        source = Source(
            source_id="src_test01",
            name="Test Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=0,
        )
        db_session.add(source)
        db_session.commit()

        # Simulate failure
        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.side_effect = ConnectorError("HTTP 404")

            with pytest.raises(ConnectorError):
                ingest_source("src_test01")

        db_session.refresh(source)
        assert source.consecutive_failures == 1

    def test_source_frozen_after_max_failures(self, db_session):
        """Test source is frozen after max consecutive failures."""
        source = Source(
            source_id="src_test02",
            name="Test Source",
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
                ingest_source("src_test02")

        db_session.refresh(source)
        assert source.status == SourceStatus.FROZEN
        assert "连续采集失败" in source.review_reason

    def test_failures_reset_on_success(self, db_session):
        """Test consecutive failures reset on successful fetch."""
        source = Source(
            source_id="src_test03",
            name="Test Source",
            connector_type="rss",
            config={"feed_url": "https://example.com/feed/"},
            status=SourceStatus.ACTIVE,
            consecutive_failures=3,
        )
        db_session.add(source)
        db_session.commit()

        with patch('cyberpulse.tasks.ingestion_tasks._fetch_items') as mock_fetch:
            mock_fetch.return_value = FetchResult(items=[], redirect_info=None)

            ingest_source("src_test03")

        db_session.refresh(source)
        assert source.consecutive_failures == 0
```

### 手动验证

```bash
# 1. 验证重定向跟随
docker compose -f deploy/docker-compose.yml exec api cyber-pulse source test src_70d4d89c  # VentureBeat (重定向)

# 2. 验证自动发现
docker compose -f deploy/docker-compose.yml exec api cyber-pulse source test src_9b52a098  # Microsoft Security (404)

# 3. 查看冻结源
docker compose -f deploy/docker-compose.yml exec api cyber-pulse source list --status FROZEN

# 4. 验证日志
docker compose -f deploy/docker-compose.yml exec api cyber-pulse log search "frozen"
```

## 影响评估

### 向后兼容性

| 项目 | 影响 |
|------|------|
| API 响应 | ✅ 兼容，无变化 |
| 数据库 | ⚠️ 新增字段，需要迁移 |
| CLI 命令 | ✅ 兼容，新增可选行为 |
| 配置文件 | ✅ 兼容，支持新增 site_url |

### 性能影响

| 项目 | 影响 |
|------|------|
| 正常采集 | 无影响 |
| 失败采集 | 新增 RSS 发现（约 2-3 秒），可接受 |
| 冻结源 | 跳过采集，减少无效请求 |

### 风险

| 风险 | 缓解措施 |
|------|---------|
| RSS 发现误判 | 验证发现的 URL 是否为有效 RSS |
| 冻结过于激进 | 阈值设为 5 次，不会误杀偶发失败 |
| SSRF 通过重定向绕过 | 已有 URL 校验逻辑，启用后生效 |

## 范围边界

### 纳入本次实现

- ✅ HTTP 重定向跟随 + 永久重定向自动更新 URL
- ✅ 默认浏览器 User-Agent
- ✅ 连续失败计数 + 自动冻结（5 次）
- ✅ RSS 自动发现模块
- ✅ 采集失败时自动发现新 RSS
- ✅ 添加源时支持 site_url 自动发现

### 不纳入本次实现

- ❌ 自定义 headers 支持（默认 UA 足够）
- ❌ CLI 增强（单独 issue）
- ❌ 源健康监控/告警（后续讨论）

## 完成标准

1. ✅ Issue #42 中的 HTTP 重定向错误全部解决
2. ✅ 连续失败源自动冻结，不再无限重试
3. ✅ 404 废弃地址可自动发现新 RSS
4. ✅ 所有测试通过
5. ✅ 代码审查通过