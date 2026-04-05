---
name: YouTube 频道字幕采集连接器设计
description: YouTube 频道字幕采集连接器（无 API Key 方案）
type: project
---

# YouTube 频道字幕采集连接器设计

## 概述

**目标**：实现 YouTube 频道视频采集，以字幕作为正文内容。

**方案**：RSS Feed（获取视频列表）+ youtube-transcript-api（提取字幕），无需 API Key。

**测试验证**：Black Hat 官方频道 5/5 视频字幕提取成功率 100%。

---

## 架构设计

### 整体架构

```
YouTubeConnector (新连接器)
├── 配置层
│   └── channel_url → 解析 → channel_id → RSS Feed URL
│
├── 数据获取层
│   ├── _fetch_video_list()  → RSS Feed 解析（视频元数据）
│   └── _fetch_transcript()  → youtube-transcript-api（字幕提取）
│
└── 输出层
    └── FetchResult(items, redirect_info)
        └── 标准化 Item 格式
```

### 文件结构

```
src/cyberpulse/services/
├── youtube_connector.py      # 新增：YouTube 频道连接器
├── connector_factory.py      # 修改：注册 youtube 类型
└── __init__.py               # 修改：导出 YouTubeConnector

tests/
├── services/test_youtube_connector.py      # 新增：单元测试
└── integration/test_youtube_connector.py   # 新增：集成测试

docs/source-config-examples.md  # 修改：添加 YouTube 源配置示例
```

---

## 详细设计

### 1. YouTubeConnector 类

```python
"""YouTube Channel Connector implementation for video transcript collection."""

import asyncio
import email.utils
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError
from .http_headers import get_browser_headers
from .rss_connector import FetchResult

logger = logging.getLogger(__name__)


class YouTubeConnector(BaseConnector):
    """Connector for YouTube channels.

    Fetches video transcripts using RSS Feed + youtube-transcript-api.
    No API Key required.
    """

    # Configuration
    REQUIRED_CONFIG_KEYS = ["channel_url"]
    MAX_ITEMS = 15  # RSS Feed 默认返回 15 条

    # Transcript language priority
    TRANSCRIPT_LANGUAGE_PRIORITY = ["en", "en-US", "en-GB"]

    # Allowed domains
    ALLOWED_DOMAINS = frozenset(["www.youtube.com", "youtube.com", "m.youtube.com"])

    def validate_config(self) -> bool:
        """Validate that channel_url is present and valid.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If channel_url is missing or invalid
        """
        if "channel_url" not in self.config:
            raise ValueError("YouTube connector requires 'channel_url' in config")

        channel_url = self.config["channel_url"]
        if not channel_url or not isinstance(channel_url, str):
            raise ValueError("YouTube connector 'channel_url' must be a non-empty string")

        # SSRF protection: validate URL scheme and destination
        try:
            validate_url_for_ssrf(channel_url)
        except SSRFError as e:
            raise ValueError(f"Invalid channel_url: {e}") from e

        # Validate YouTube domain
        parsed = urlparse(channel_url)
        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            raise ValueError(
                f"Invalid YouTube URL: domain must be youtube.com, got '{parsed.netloc}'"
            )

        return True

    async def fetch(self) -> FetchResult:
        """Fetch videos with transcripts from the YouTube channel.

        Returns:
            FetchResult with items and optional redirect_info

        Raises:
            ConnectorError: If fetch fails
        """
        self.validate_config()

        channel_url = self.config["channel_url"]

        # Step 1: Resolve channel URL to RSS Feed URL
        rss_url = await self._resolve_channel_url(channel_url)

        # Step 2: Fetch video list from RSS Feed
        rss_result = await self._fetch_video_list(rss_url)

        # Step 3: Extract transcripts for each video
        items = await self._process_videos(rss_result.items)

        return FetchResult(items=items, redirect_info=rss_result.redirect_info)

    async def _resolve_channel_url(self, channel_url: str) -> str:
        """Resolve channel URL to RSS Feed URL.

        Handles formats:
        - https://youtube.com/@Handle
        - https://youtube.com/channel/UCxxxxxx
        - https://youtube.com/user/Username

        Args:
            channel_url: YouTube channel URL

        Returns:
            RSS Feed URL

        Raises:
            ConnectorError: If URL cannot be resolved
        """
        parsed = urlparse(channel_url)
        path = parsed.path.strip("/")

        # Format: /channel/UCxxxxxx
        if path.startswith("channel/"):
            channel_id = path.split("/")[1]
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        # Format: /@Handle or /user/Username
        # Need to fetch channel page to get channel_id
        try:
            channel_id = await self._fetch_channel_id(channel_url)
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        except Exception as e:
            raise ConnectorError(
                f"Failed to resolve YouTube channel: {type(e).__name__}: {e}"
            ) from e

    async def _fetch_channel_id(self, channel_url: str) -> str:
        """Fetch channel_id from channel page HTML.

        Args:
            channel_url: YouTube channel URL

        Returns:
            Channel ID

        Raises:
            ConnectorError: If channel_id cannot be extracted
        """
        # Check cache
        cached_id = self.config.get("resolved_channel_id")
        if cached_id:
            return cached_id

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                channel_url,
                headers=get_browser_headers(),
            )
            response.raise_for_status()
            html = response.text

        # Extract channel_id from HTML
        # Pattern: "channelId":"UCxxxxxx" or meta tag og:url
        patterns = [
            r'"channelId"\s*:\s*"([^"]+)"',
            r'<meta\s+property="og:url"\s+content="[^"]*channel/([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                channel_id = match.group(1)
                logger.info(f"Resolved channel_id: {channel_id} from {channel_url}")
                return channel_id

        raise ConnectorError(f"Could not extract channel_id from {channel_url}")

    async def _fetch_video_list(self, rss_url: str) -> FetchResult:
        """Fetch video list from RSS Feed.

        Args:
            rss_url: YouTube RSS Feed URL

        Returns:
            FetchResult with video entries

        Raises:
            ConnectorError: If fetch fails
        """
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    rss_url,
                    headers=get_browser_headers(),
                )

                # SSRF validation on final URL
                final_url = str(response.url)
                if final_url != rss_url:
                    try:
                        validate_url_for_ssrf(final_url)
                    except SSRFError as e:
                        raise ConnectorError(
                            f"RSS redirect to blocked URL: {e}"
                        ) from e

                response.raise_for_status()
                content = response.content

            # Detect permanent redirect
            redirect_info = None
            if response.history:
                for hist in response.history:
                    if hist.status_code in (301, 308):
                        redirect_info = {
                            "original_url": rss_url,
                            "final_url": final_url,
                            "status_code": hist.status_code,
                        }
                        logger.info(
                            f"YouTube RSS permanently redirected: {rss_url} -> {final_url}"
                        )
                        break

            # Parse RSS with feedparser
            feed = feedparser.parse(content)

            # Handle bozo (malformed) feeds
            if feed.get("bozo"):
                logger.warning(
                    f"YouTube RSS feed has malformed content: {feed.get('bozo_exception')}"
                )

            entries = feed.get("entries", [])[:self.MAX_ITEMS]

            # Parse video entries
            items = []
            for entry in entries:
                try:
                    item = self._parse_video_entry(entry)
                    if item:
                        items.append(item)
                except Exception as e:
                    video_id = (
                        entry.get("yt_videoid")
                        or entry.get("id")
                        or "unknown"
                    )
                    logger.warning(
                        f"Skipping malformed YouTube entry '{video_id}': {e}"
                    )
                    continue

            return FetchResult(items=items, redirect_info=redirect_info)

        except httpx.HTTPStatusError as e:
            raise ConnectorError(
                f"Failed to fetch YouTube RSS '{rss_url}': HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ConnectorError(
                f"Failed to fetch YouTube RSS '{rss_url}': {type(e).__name__}: {e}"
            ) from e
        except Exception as e:
            raise ConnectorError(
                f"Failed to fetch YouTube RSS '{rss_url}': {type(e).__name__}: {e}"
            ) from e

    def _parse_video_entry(self, entry: Any) -> dict[str, Any] | None:
        """Parse a YouTube RSS entry into standardized format.

        Args:
            entry: feedparser entry object

        Returns:
            Standardized item dictionary or None if invalid
        """
        # Get video_id
        video_id = entry.get("yt_videoid") or entry.get("id")
        if not video_id:
            return None

        # Get URL
        url = entry.get("link")
        if not url:
            url = f"https://www.youtube.com/watch?v={video_id}"

        # Get title
        title = entry.get("title", "")

        # Get description (fallback content)
        description = entry.get("summary") or entry.get("description") or ""

        # Parse published date
        published_at = self._parse_date(entry)

        # Get author (channel name)
        author = entry.get("author", "")

        # Get tags
        tags = []
        if hasattr(entry, "tags") and entry.tags:
            tags = [t.term for t in entry.tags if hasattr(t, "term")]

        return {
            "video_id": video_id,
            "url": url,
            "title": title,
            "description": description,
            "published_at": published_at,
            "author": author,
            "tags": tags,
        }

    async def _process_videos(
        self, video_entries: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process video entries: fetch transcripts and build items.

        Args:
            video_entries: List of parsed video entries

        Returns:
            List of standardized items with content (transcript or description)
        """
        items = []

        for entry in video_entries:
            video_id = entry["video_id"]

            # Try to fetch transcript
            transcript = await self._fetch_transcript(video_id)

            # Use transcript if available, otherwise use description
            content = transcript or entry["description"]

            if not content or not content.strip():
                logger.warning(f"No content for video {video_id}, skipping")
                continue

            items.append({
                "external_id": video_id,
                "url": entry["url"],
                "title": entry["title"],
                "published_at": entry["published_at"],
                "content": content,
                "author": entry["author"],
                "tags": entry["tags"],
                "raw_metadata": {
                    "has_transcript": transcript is not None,
                    "video_id": video_id,
                },
            })

        return items

    async def _fetch_transcript(self, video_id: str) -> str | None:
        """Fetch transcript for a YouTube video.

        Language priority: en -> en-US -> en-GB -> auto-generated English

        Args:
            video_id: YouTube video ID

        Returns:
            Transcript text or None if unavailable
        """
        try:
            api = YouTubeTranscriptApi()

            # Try preferred languages
            for lang in self.TRANSCRIPT_LANGUAGE_PRIORITY:
                try:
                    transcript_list = api.fetch(video_id, [lang])
                    return self._format_transcript(transcript_list)
                except NoTranscriptFound:
                    continue

            # Try auto-generated English
            try:
                transcript_list = api.fetch(video_id, ["en"], preserve_formatting=True)
                return self._format_transcript(transcript_list)
            except (TranscriptsDisabled, NoTranscriptFound):
                return None

        except TranscriptsDisabled:
            logger.debug(f"Transcripts disabled for video {video_id}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch transcript for {video_id}: {e}")
            return None

    def _format_transcript(self, transcript_list: list) -> str:
        """Format transcript list into text.

        Args:
            transcript_list: List of transcript snippets

        Returns:
            Formatted transcript text
        """
        # Convert to list if needed
        transcripts = list(transcript_list) if not isinstance(transcript_list, list) else transcript_list

        # Extract text from snippets
        texts = []
        for snippet in transcripts:
            # Use attribute access (FetchedTranscriptSnippet)
            text = getattr(snippet, "text", None) or snippet.get("text", "")
            if text:
                texts.append(text)

        return " ".join(texts)

    def _parse_date(self, entry: Any) -> datetime:
        """Parse publication date from YouTube RSS entry.

        Args:
            entry: feedparser entry object

        Returns:
            Timezone-aware datetime (defaults to current UTC time if parsing fails)
        """
        # Try published_parsed first (struct_time)
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6], tzinfo=UTC)
                return dt
            except (TypeError, ValueError):
                pass

        # Try published string
        published = entry.get("published") or entry.get("pubDate")
        if published:
            try:
                parsed = email.utils.parsedate_to_datetime(published)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            except (TypeError, ValueError):
                pass

        # Fallback to current time
        logger.debug(f"No valid publication date found, using current UTC time")
        return self.get_current_utc_time()
```

---

### 2. connector_factory.py 修改

```python
# 添加导入
from .youtube_connector import YouTubeConnector

# 更新注册表
CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "rss": RSSConnector,
    "api": APIConnector,
    "web": WebScraperConnector,
    "media": MediaAPIConnector,
    "youtube": YouTubeConnector,  # 新增
}
```

---

### 3. 采集流程兼容性

**ingest_source 任务无需修改**，原因：

1. **连接器选择**：`get_connector_for_source(source)` 自动根据 `connector_type` 选择连接器
2. **输出格式**：`FetchResult` 与 `RSSConnector` 一致
3. **重定向处理**：RSS URL 重定向信息记录到日志，不影响源配置
4. **失败追踪**：`ConnectorError` 抛出后，任务层自动追踪 `consecutive_failures` 并冻结源

**重定向处理差异**：

| 场景 | RSS 源 | YouTube 源 |
|------|--------|------------|
| 301/308 检测 | ✅ | ✅ |
| 更新源配置 | `source.config["feed_url"] = new_url` | 不更新（无 feed_url 字段） |
| 处理方式 | 自动更新 | 记录日志，可能更新 `resolved_channel_id` |

---

### 4. 错误处理策略

| 错误类型 | 场景 | 连接器行为 | 任务层处理 |
|----------|------|------------|------------|
| **配置验证失败** | 无效 URL、非 YouTube 域名 | `ValueError`（阻止源创建） | 源创建失败 |
| **channel_id 解析失败** | 频道不存在、页面结构变更 | `ConnectorError` | `consecutive_failures += 1` |
| **RSS 获取失败** | 网络错误、HTTP 错误 | `ConnectorError` | `consecutive_failures += 1` |
| **字幕提取失败** | 无字幕、语言不匹配 | 返回 `None`，降级用描述 | 正常完成，不计失败 |
| **连续失败 ≥ N** | N = `max_consecutive_failures` | 无需处理 | 自动冻结源 |

---

### 5. 测试策略

#### 单元测试

```python
# tests/services/test_youtube_connector.py

class TestYouTubeConnectorValidate:
    """配置验证测试"""

    def test_valid_channel_url_handle(self):
        """测试 @Handle 格式 URL"""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })
        assert connector.validate_config() is True

    def test_valid_channel_url_id(self):
        """测试 /channel/ID 格式 URL"""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })
        assert connector.validate_config() is True

    def test_invalid_url_missing_channel_url(self):
        """测试缺少 channel_url"""
        with pytest.raises(ValueError, match="requires 'channel_url'"):
            YouTubeConnector({}).validate_config()

    def test_invalid_url_non_youtube(self):
        """测试非 YouTube 域名"""
        with pytest.raises(ValueError, match="must be youtube.com"):
            YouTubeConnector({
                "channel_url": "https://vimeo.com/somechannel"
            }).validate_config()


class TestYouTubeConnectorTranscript:
    """字幕提取测试"""

    @pytest.mark.asyncio
    async def test_fetch_transcript_success(self):
        """测试成功获取字幕"""

    @pytest.mark.asyncio
    async def test_fetch_transcript_disabled(self):
        """测试字幕禁用"""

    @pytest.mark.asyncio
    async def test_fetch_transcript_fallback_description(self):
        """测试降级使用描述"""


class TestYouTubeConnectorIntegration:
    """完整流程测试"""

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        """测试返回 FetchResult"""

    @pytest.mark.asyncio
    async def test_fetch_items_format(self):
        """测试输出格式符合标准"""
```

#### 集成测试

```python
# tests/integration/test_youtube_connector.py

class TestYouTubeConnectorReal:
    """真实频道测试"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_blackhat_channel(self):
        """测试 Black Hat 官方频道"""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })
        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0
        assert all(item["external_id"] for item in result.items)
        assert all(item["url"].startswith("https://") for item in result.items)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_owasp_channel(self):
        """测试 OWASP 频道"""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@OWASPGLOBAL"
        })
        result = await connector.fetch()

        assert len(result.items) > 0
```

---

### 6. 配置示例

#### API 请求

```bash
curl -X POST http://localhost:8000/api/v1/admin/sources \
  -H "Authorization: Bearer <admin_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Black Hat Official",
    "connector_type": "youtube",
    "tier": "T1",
    "config": {
      "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
    }
  }'
```

#### sources.yaml 格式

```yaml
sources:
  - name: Black Hat Official
    connector_type: youtube
    tier: T1
    config:
      channel_url: https://www.youtube.com/@BlackHatOfficialYT

  - name: OWASP Global
    connector_type: youtube
    tier: T1
    config:
      channel_url: https://www.youtube.com/@OWASPGLOBAL
```

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/cyberpulse/services/youtube_connector.py` | **新增** | YouTube 频道连接器 |
| `src/cyberpulse/services/connector_factory.py` | **修改** | 注册 `youtube` 类型 |
| `src/cyberpulse/services/__init__.py` | **修改** | 导出 `YouTubeConnector` |
| `tests/services/test_youtube_connector.py` | **新增** | 单元测试 |
| `tests/integration/test_youtube_connector.py` | **新增** | 集成测试 |
| `docs/source-config-examples.md` | **修改** | 添加 YouTube 源配置示例 |

---

## 与 RSS 源对照检查表

| 检查项 | RSSConnector | YouTubeConnector | 状态 |
|--------|--------------|------------------|------|
| 必填字段验证 | `feed_url` | `channel_url` | ✅ |
| 字段类型验证 | ✅ | ✅ | ✅ |
| 非空验证 | ✅ | ✅ | ✅ |
| SSRF 防护 | ✅ | ✅ | ✅ |
| YouTube 域名验证 | N/A | ✅ | ✅ |
| httpx 客户端配置 | ✅ | ✅ | ✅ |
| 浏览器 Headers | ✅ | ✅ | ✅ |
| 重定向跟随 | ✅ | ✅ | ✅ |
| 最终 URL SSRF 验证 | ✅ | ✅ | ✅ |
| 301/308 永久重定向检测 | ✅ | ✅ | ✅ |
| feedparser 解析 | ✅ | ✅ | ✅ |
| bozo 容错 | ✅ | ✅ | ✅ |
| 条目解析失败处理 | ✅ | ✅ | ✅ |
| 日期解析（多格式） | ✅ | ✅ | ✅ |
| 时区处理 | ✅ | ✅ | ✅ |
| 返回 FetchResult | ✅ | ✅ | ✅ |
| 错误处理 | ✅ | ✅ | ✅ |
| 标准化输出格式 | ✅ | ✅ | ✅ |

---

## Why

用户需要跟踪 YouTube 频道最新视频，以字幕作为正文内容。无 API Key 方案避免了配额限制和第三方依赖。

## How to apply

1. 实现 `YouTubeConnector` 类
2. 在 `connector_factory.py` 注册 `youtube` 类型
3. 更新 `__init__.py` 导出
4. 编写单元测试和集成测试
5. 更新配置文档

实现时严格遵循 `RSSConnector` 的模式，确保与现有采集流程完全兼容。