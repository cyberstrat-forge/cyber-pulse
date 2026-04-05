# YouTube 频道字幕采集连接器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 YouTube 频道连接器，通过 RSS Feed 获取视频列表，使用 youtube-transcript-api 提取字幕作为正文内容。

**Architecture:** 分层设计 - URL 解析层（channel_url → channel_id → RSS URL）+ 数据获取层（RSS 解析 + 字幕提取）+ 输出层（标准化 FetchResult）。严格遵循 RSSConnector 模式确保与现有 ingest_source 任务完全兼容。

**Tech Stack:** Python 3.11+, httpx, feedparser, youtube-transcript-api, asyncio

---

## 文件结构

```
src/cyberpulse/services/
├── youtube_connector.py      # 新增：YouTube 频道连接器（核心实现）
├── connector_factory.py      # 修改：注册 youtube 类型
└── __init__.py               # 修改：导出 YouTubeConnector

tests/test_services/
└── test_youtube_connector.py # 新增：单元测试

docs/
└── source-config-examples.md # 修改：添加 YouTube 源配置示例
```

---

### Task 1: 实现 YouTubeConnector 核心类

**Files:**
- Create: `src/cyberpulse/services/youtube_connector.py`

- [ ] **Step 1: 创建 youtube_connector.py 文件骨架**

```python
"""YouTube Channel Connector implementation for video transcript collection."""

import asyncio
import email.utils
import logging
import re
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

    REQUIRED_CONFIG_KEYS = ["channel_url"]
    MAX_ITEMS = 15
    TRANSCRIPT_LANGUAGE_PRIORITY = ["en", "en-US", "en-GB"]
    ALLOWED_DOMAINS = frozenset(["www.youtube.com", "youtube.com", "m.youtube.com"])

    def validate_config(self) -> bool:
        """Validate that channel_url is present and valid."""
        if "channel_url" not in self.config:
            raise ValueError("YouTube connector requires 'channel_url' in config")

        channel_url = self.config["channel_url"]
        if not channel_url or not isinstance(channel_url, str):
            raise ValueError("YouTube connector 'channel_url' must be a non-empty string")

        try:
            validate_url_for_ssrf(channel_url)
        except SSRFError as e:
            raise ValueError(f"Invalid channel_url: {e}") from e

        parsed = urlparse(channel_url)
        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            raise ValueError(
                f"Invalid YouTube URL: domain must be youtube.com, got '{parsed.netloc}'"
            )

        return True

    async def fetch(self) -> FetchResult:
        """Fetch videos with transcripts from the YouTube channel."""
        raise NotImplementedError("To be implemented")

    # 后续步骤添加其他方法...
```

- [ ] **Step 2: 运行语法检查**

Run: `uv run python -c "from cyberpulse.services.youtube_connector import YouTubeConnector; print('Import OK')"`
Expected: "Import OK"

- [ ] **Step 3: 实现 _resolve_channel_url 方法**

在 `YouTubeConnector` 类中添加：

```python
async def _resolve_channel_url(self, channel_url: str) -> str:
    """Resolve channel URL to RSS Feed URL."""
    parsed = urlparse(channel_url)
    path = parsed.path.strip("/")

    # Format: /channel/UCxxxxxx
    if path.startswith("channel/"):
        channel_id = path.split("/")[1]
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # Format: /@Handle or /user/Username
    try:
        channel_id = await self._fetch_channel_id(channel_url)
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    except Exception as e:
        raise ConnectorError(
            f"Failed to resolve YouTube channel: {type(e).__name__}: {e}"
        ) from e
```

- [ ] **Step 4: 实现 _fetch_channel_id 方法**

在 `YouTubeConnector` 类中添加：

```python
async def _fetch_channel_id(self, channel_url: str) -> str:
    """Fetch channel_id from channel page HTML."""
    cached_id = self.config.get("resolved_channel_id")
    if cached_id:
        return cached_id

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(channel_url, headers=get_browser_headers())
        response.raise_for_status()
        html = response.text

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
```

- [ ] **Step 5: 实现 _fetch_video_list 方法**

在 `YouTubeConnector` 类中添加：

```python
async def _fetch_video_list(self, rss_url: str) -> FetchResult:
    """Fetch video list from RSS Feed."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(rss_url, headers=get_browser_headers())

            final_url = str(response.url)
            if final_url != rss_url:
                try:
                    validate_url_for_ssrf(final_url)
                except SSRFError as e:
                    raise ConnectorError(f"RSS redirect to blocked URL: {e}") from e

            response.raise_for_status()
            content = response.content

        redirect_info = None
        if response.history:
            for hist in response.history:
                if hist.status_code in (301, 308):
                    redirect_info = {
                        "original_url": rss_url,
                        "final_url": final_url,
                        "status_code": hist.status_code,
                    }
                    logger.info(f"YouTube RSS permanently redirected: {rss_url} -> {final_url}")
                    break

        feed = feedparser.parse(content)

        if feed.get("bozo"):
            logger.warning(f"YouTube RSS feed has malformed content: {feed.get('bozo_exception')}")

        entries = feed.get("entries", [])[:self.MAX_ITEMS]

        items = []
        for entry in entries:
            try:
                item = self._parse_video_entry(entry)
                if item:
                    items.append(item)
            except Exception as e:
                video_id = entry.get("yt_videoid") or entry.get("id") or "unknown"
                logger.warning(f"Skipping malformed YouTube entry '{video_id}': {e}")
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
```

- [ ] **Step 6: 实现 _parse_video_entry 方法**

在 `YouTubeConnector` 类中添加：

```python
def _parse_video_entry(self, entry: Any) -> dict[str, Any] | None:
    """Parse a YouTube RSS entry into standardized format."""
    video_id = entry.get("yt_videoid") or entry.get("id")
    if not video_id:
        return None

    url = entry.get("link")
    if not url:
        url = f"https://www.youtube.com/watch?v={video_id}"

    title = entry.get("title", "")
    description = entry.get("summary") or entry.get("description") or ""
    published_at = self._parse_date(entry)
    author = entry.get("author", "")

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
```

- [ ] **Step 7: 实现 _parse_date 方法**

在 `YouTubeConnector` 类中添加：

```python
def _parse_date(self, entry: Any) -> datetime:
    """Parse publication date from YouTube RSS entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            return dt
        except (TypeError, ValueError):
            pass

    published = entry.get("published") or entry.get("pubDate")
    if published:
        try:
            parsed = email.utils.parsedate_to_datetime(published)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except (TypeError, ValueError):
            pass

    logger.debug("No valid publication date found, using current UTC time")
    return self.get_current_utc_time()
```

- [ ] **Step 8: 实现 _process_videos 方法**

在 `YouTubeConnector` 类中添加：

```python
async def _process_videos(self, video_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Process video entries: fetch transcripts and build items."""
    items = []

    for entry in video_entries:
        video_id = entry["video_id"]
        transcript = await self._fetch_transcript(video_id)
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
```

- [ ] **Step 9: 实现 _fetch_transcript 方法**

在 `YouTubeConnector` 类中添加：

```python
async def _fetch_transcript(self, video_id: str) -> str | None:
    """Fetch transcript for a YouTube video."""
    try:
        api = YouTubeTranscriptApi()

        for lang in self.TRANSCRIPT_LANGUAGE_PRIORITY:
            try:
                transcript_list = api.fetch(video_id, [lang])
                return self._format_transcript(transcript_list)
            except NoTranscriptFound:
                continue

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
```

- [ ] **Step 10: 实现 _format_transcript 方法**

在 `YouTubeConnector` 类中添加：

```python
def _format_transcript(self, transcript_list: list) -> str:
    """Format transcript list into text."""
    transcripts = list(transcript_list) if not isinstance(transcript_list, list) else transcript_list

    texts = []
    for snippet in transcripts:
        text = getattr(snippet, "text", None) or snippet.get("text", "")
        if text:
            texts.append(text)

    return " ".join(texts)
```

- [ ] **Step 11: 实现 fetch 主方法**

在 `YouTubeConnector` 类中添加：

```python
async def fetch(self) -> FetchResult:
    """Fetch videos with transcripts from the YouTube channel."""
    self.validate_config()

    channel_url = self.config["channel_url"]

    rss_url = await self._resolve_channel_url(channel_url)
    rss_result = await self._fetch_video_list(rss_url)
    items = await self._process_videos(rss_result.items)

    return FetchResult(items=items, redirect_info=rss_result.redirect_info)
```

- [ ] **Step 12: 运行类型检查**

Run: `uv run mypy src/cyberpulse/services/youtube_connector.py --ignore-missing-imports`
Expected: 无错误

- [ ] **Step 13: 提交 Task 1**

```bash
git add src/cyberpulse/services/youtube_connector.py
git commit -m "feat: add YouTubeConnector for video transcript collection

- RSS Feed for video list (no API Key required)
- youtube-transcript-api for transcript extraction
- Language priority: en -> en-US -> en-GB
- Fallback to video description when no transcript

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: 注册 YouTube 连接器类型

**Files:**
- Modify: `src/cyberpulse/services/connector_factory.py`
- Modify: `src/cyberpulse/services/__init__.py`

- [ ] **Step 1: 更新 connector_factory.py 导入**

在 `connector_factory.py` 文件顶部的导入部分添加：

```python
from .youtube_connector import YouTubeConnector
```

- [ ] **Step 2: 更新 CONNECTOR_REGISTRY**

将 `connector_factory.py` 中的注册表更新为：

```python
CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    "rss": RSSConnector,
    "api": APIConnector,
    "web": WebScraperConnector,
    "media": MediaAPIConnector,
    "youtube": YouTubeConnector,
}
```

- [ ] **Step 3: 更新 __init__.py 导入**

在 `__init__.py` 中添加导入：

```python
from .youtube_connector import YouTubeConnector
```

- [ ] **Step 4: 更新 __init__.py 导出列表**

将 `__all__` 列表更新为：

```python
__all__ = [
    "BaseService",
    "SourceService",
    "SourceScoreService",
    "ScoreComponents",
    "ItemService",
    "BaseConnector",
    "ConnectorError",
    "RSSConnector",
    "APIConnector",
    "WebScraperConnector",
    "MediaAPIConnector",
    "YouTubeConnector",  # 新增
    "NormalizationService",
    "NormalizationResult",
    "QualityGateService",
    "QualityDecision",
    "QualityResult",
    "CONNECTOR_REGISTRY",
    "get_connector",
    "get_connector_for_source",
]
```

- [ ] **Step 5: 验证导入**

Run: `uv run python -c "from cyberpulse.services import YouTubeConnector; print('YouTubeConnector imported successfully')"`
Expected: "YouTubeConnector imported successfully"

- [ ] **Step 6: 提交 Task 2**

```bash
git add src/cyberpulse/services/connector_factory.py src/cyberpulse/services/__init__.py
git commit -m "feat: register YouTubeConnector in factory and exports

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: 编写单元测试

**Files:**
- Create: `tests/test_services/test_youtube_connector.py`

- [ ] **Step 1: 创建测试文件骨架**

```python
"""Tests for YouTube Connector."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services import ConnectorError, YouTubeConnector
from cyberpulse.services.rss_connector import FetchResult


class MockFeedEntry(dict):
    """Mock feed entry that supports both dict and attribute access."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class TestYouTubeConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid_handle_url(self):
        """Test validation passes with @Handle format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })
        assert connector.validate_config() is True

    def test_validate_config_valid_channel_id_url(self):
        """Test validation passes with /channel/ID format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })
        assert connector.validate_config() is True

    def test_validate_config_missing_channel_url(self):
        """Test validation fails when channel_url is missing."""
        connector = YouTubeConnector({})
        with pytest.raises(ValueError, match="requires 'channel_url'"):
            connector.validate_config()

    def test_validate_config_empty_channel_url(self):
        """Test validation fails when channel_url is empty."""
        connector = YouTubeConnector({"channel_url": ""})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_non_youtube_domain(self):
        """Test validation fails for non-YouTube domain."""
        connector = YouTubeConnector({
            "channel_url": "https://vimeo.com/somechannel"
        })
        with pytest.raises(ValueError, match="must be youtube.com"):
            connector.validate_config()

    def test_validate_config_mobile_youtube_domain(self):
        """Test validation passes for m.youtube.com domain."""
        connector = YouTubeConnector({
            "channel_url": "https://m.youtube.com/@SomeChannel"
        })
        assert connector.validate_config() is True


class TestYouTubeConnectorResolveChannelUrl:
    """Tests for _resolve_channel_url method."""

    @pytest.mark.asyncio
    async def test_resolve_channel_id_format(self):
        """Test /channel/ID format resolves directly."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        rss_url = await connector._resolve_channel_url(
            "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        )

        assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCJ6q9Ie29ajGqKApbLqfBOg"


class TestYouTubeConnectorParseVideoEntry:
    """Tests for _parse_video_entry method."""

    def test_parse_video_entry_basic(self):
        """Test basic video entry parsing."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            yt_videoid="video123",
            link="https://www.youtube.com/watch?v=video123",
            title="Test Video",
            summary="Video description",
            published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
            author="Test Channel",
        )

        result = connector._parse_video_entry(entry)

        assert result is not None
        assert result["video_id"] == "video123"
        assert result["url"] == "https://www.youtube.com/watch?v=video123"
        assert result["title"] == "Test Video"
        assert result["description"] == "Video description"
        assert result["author"] == "Test Channel"

    def test_parse_video_entry_without_link(self):
        """Test entry without link generates URL from video_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            yt_videoid="video456",
            link=None,
            title="Video Without Link",
            summary="Description",
            published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
        )

        result = connector._parse_video_entry(entry)

        assert result is not None
        assert result["url"] == "https://www.youtube.com/watch?v=video456"

    def test_parse_video_entry_without_video_id(self):
        """Test entry without video_id returns None."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            title="No Video ID",
            summary="Description",
        )

        result = connector._parse_video_entry(entry)

        assert result is None


class TestYouTubeConnectorParseDate:
    """Tests for _parse_date method."""

    def test_parse_date_from_published_parsed(self):
        """Test parsing date from published_parsed field."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            published_parsed=time.struct_time((2024, 3, 15, 14, 30, 0, 0, 75, 0))
        )

        result = connector._parse_date(entry)

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.tzinfo == UTC

    def test_parse_date_fallback_to_current_time(self):
        """Test missing date falls back to current UTC time."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry()

        before = datetime.now(UTC)
        result = connector._parse_date(entry)
        after = datetime.now(UTC)

        assert before <= result <= after
        assert result.tzinfo == UTC


class TestYouTubeConnectorFetchVideoList:
    """Tests for _fetch_video_list method."""

    def _create_mock_response(self, content: bytes = b"", url: str = "https://www.youtube.com/feeds/videos.xml?channel_id=test"):
        """Create a mock httpx response."""
        mock_response = MagicMock()
        mock_response.content = content
        mock_response.url = url
        mock_response.history = []
        mock_response.raise_for_status = MagicMock()
        return mock_response

    @pytest.mark.asyncio
    async def test_fetch_video_list_success(self):
        """Test successful video list fetch."""
        mock_response = self._create_mock_response(b"<rss></rss>")

        mock_feed_result = {
            "entries": [
                MockFeedEntry(
                    yt_videoid="vid1",
                    link="https://www.youtube.com/watch?v=vid1",
                    title="Video 1",
                    summary="Description 1",
                    published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
                )
            ],
            "bozo": False,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                connector = YouTubeConnector({
                    "channel_url": "https://www.youtube.com/@TestChannel"
                })
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

        assert isinstance(result, FetchResult)
        assert len(result.items) == 1
        assert result.items[0]["video_id"] == "vid1"

    @pytest.mark.asyncio
    async def test_fetch_video_list_http_error(self):
        """Test fetch raises ConnectorError on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=http_error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            connector = YouTubeConnector({
                "channel_url": "https://www.youtube.com/@TestChannel"
            })

            with pytest.raises(ConnectorError, match="Failed to fetch YouTube RSS"):
                await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )


class TestYouTubeConnectorFetch:
    """Tests for main fetch method."""

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        """Test that fetch returns FetchResult."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        # Mock all internal methods
        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            with patch.object(connector, "_fetch_video_list", new_callable=AsyncMock) as mock_fetch_list:
                with patch.object(connector, "_process_videos", new_callable=AsyncMock) as mock_process:
                    mock_resolve.return_value = "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                    mock_fetch_list.return_value = FetchResult(items=[], redirect_info=None)
                    mock_process.return_value = []

                    result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert result.items == []
        assert result.redirect_info is None
```

- [ ] **Step 2: 运行测试确认通过**

Run: `uv run pytest tests/test_services/test_youtube_connector.py -v`
Expected: 所有测试通过

- [ ] **Step 3: 提交 Task 3**

```bash
git add tests/test_services/test_youtube_connector.py
git commit -m "test: add unit tests for YouTubeConnector

- Config validation tests
- URL resolution tests
- Video entry parsing tests
- Date parsing tests
- RSS fetch tests

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: 更新连接器工厂测试

**Files:**
- Modify: `tests/test_services/test_connector_factory.py`

- [ ] **Step 1: 添加 YouTube 连接器导入**

在 `test_connector_factory.py` 顶部导入部分添加：

```python
from cyberpulse.services import (
    CONNECTOR_REGISTRY,
    APIConnector,
    MediaAPIConnector,
    RSSConnector,
    WebScraperConnector,
    YouTubeConnector,  # 新增
    get_connector,
    get_connector_for_source,
)
```

- [ ] **Step 2: 添加 test_get_connector_youtube 测试**

在 `TestGetConnector` 类中添加：

```python
def test_get_connector_youtube(self):
    """Test get_connector returns YouTubeConnector for 'youtube' type."""
    config = {"channel_url": "https://www.youtube.com/@TestChannel"}
    connector = get_connector("youtube", config)
    assert isinstance(connector, YouTubeConnector)
    assert connector.config == config
```

- [ ] **Step 3: 添加 test_get_connector_for_source_youtube 测试**

在 `TestGetConnectorForSource` 类中添加：

```python
def test_get_connector_for_source_youtube(self):
    """Test get_connector_for_source with YouTube source."""
    mock_source = MagicMock()
    mock_source.connector_type = "youtube"
    mock_source.config = {"channel_url": "https://www.youtube.com/@TestChannel"}

    connector = get_connector_for_source(mock_source)
    assert isinstance(connector, YouTubeConnector)
    assert connector.config == mock_source.config
```

- [ ] **Step 4: 更新 test_registry_contains_all_types 测试**

将 `TestConnectorRegistry` 类中的测试更新为：

```python
def test_registry_contains_all_types(self):
    """Test registry contains all expected connector types."""
    expected_types = {"rss", "api", "web", "media", "youtube"}
    assert set(CONNECTOR_REGISTRY.keys()) == expected_types
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_services/test_connector_factory.py -v`
Expected: 所有测试通过

- [ ] **Step 6: 提交 Task 4**

```bash
git add tests/test_services/test_connector_factory.py
git commit -m "test: update connector_factory tests for YouTube

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: 更新文档

**Files:**
- Modify: `docs/source-config-examples.md`

- [ ] **Step 1: 更新目录**

在目录部分添加 YouTube 源配置链接：

```markdown
## 目录

- [RSS 源配置](#rss-源配置)
- [API 源配置](#api-源配置)
- [Web 抓取源配置](#web-抓取源配置)
- [YouTube 源配置](#youtube-源配置)
- [配置模板](#配置模板)
- [常见问题](#常见问题)
```

- [ ] **Step 2: 添加 YouTube 源配置章节**

在 Web 抓取源配置章节后添加：

```markdown
---

## YouTube 源配置

### 基础 YouTube 源

```bash
cyber-pulse source add "Black Hat Official" youtube "https://www.youtube.com/@BlackHatOfficialYT" \
  --tier T1 --yes
```

### YouTube 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `channel_url` | string | YouTube 频道 URL（必需） |

### 支持的 URL 格式

| 格式 | 示例 |
|------|------|
| @Handle | `https://www.youtube.com/@BlackHatOfficialYT` |
| Channel ID | `https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg` |

### 内容说明

- **视频列表**：通过 RSS Feed 获取最近 15 条视频
- **正文内容**：优先提取视频字幕，无字幕时使用视频描述
- **字幕语言**：优先英文（en, en-US, en-GB），支持自动生成字幕

### 常见 YouTube 源示例

| 源名称 | 类型 | URL | 建议分级 |
|--------|------|-----|----------|
| Black Hat Official | youtube | https://www.youtube.com/@BlackHatOfficialYT | T1 |
| OWASP Global | youtube | https://www.youtube.com/@OWASPGLOBAL | T1 |
| DEF CON | youtube | https://www.youtube.com/@DEFCONConference | T1 |
```

- [ ] **Step 3: 更新配置模板章节**

在配置模板章节添加 YouTube 源模板：

```markdown
### YouTube 源模板

```json
{
  "channel_url": "https://www.youtube.com/@ChannelHandle"
}
```
```

- [ ] **Step 4: 提交 Task 5**

```bash
git add docs/source-config-examples.md
git commit -m "docs: add YouTube source configuration examples

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: 运行完整测试套件

**Files:**
- 无文件变更

- [ ] **Step 1: 运行所有相关测试**

Run: `uv run pytest tests/test_services/test_youtube_connector.py tests/test_services/test_connector_factory.py -v`
Expected: 所有测试通过

- [ ] **Step 2: 运行类型检查**

Run: `uv run mypy src/cyberpulse/services/youtube_connector.py --ignore-missing-imports`
Expected: 无错误

- [ ] **Step 3: 运行代码风格检查**

Run: `uv run ruff check src/cyberpulse/services/youtube_connector.py`
Expected: 无错误

---

## 自检清单

### 1. Spec 覆盖检查

| Spec 要求 | 对应任务 |
|-----------|----------|
| YouTubeConnector 类实现 | Task 1 |
| 配置验证 (validate_config) | Task 1 Step 1 |
| URL 解析 (_resolve_channel_url) | Task 1 Step 3-4 |
| RSS 获取 (_fetch_video_list) | Task 1 Step 5 |
| 视频解析 (_parse_video_entry) | Task 1 Step 6 |
| 日期解析 (_parse_date) | Task 1 Step 7 |
| 字幕提取 (_fetch_transcript) | Task 1 Step 9-10 |
| 主方法 (fetch) | Task 1 Step 11 |
| 连接器注册 | Task 2 |
| 单元测试 | Task 3 |
| 工厂测试更新 | Task 4 |
| 文档更新 | Task 5 |

### 2. Placeholder 扫描

- [ ] 无 TBD/TODO
- [ ] 无 "implement later"
- [ ] 无 "fill in details"
- [ ] 所有代码步骤包含完整代码

### 3. 类型一致性检查

- [ ] `FetchResult` 在所有方法中返回类型一致
- [ ] `_parse_video_entry` 返回 `dict[str, Any] | None`
- [ ] `_fetch_transcript` 返回 `str | None`
- [ ] `validate_config` 返回 `bool`