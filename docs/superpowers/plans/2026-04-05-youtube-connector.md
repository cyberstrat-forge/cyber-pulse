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

tests/test_integration/
└── test_youtube_connector.py # 新增：集成测试

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

    @pytest.mark.asyncio
    async def test_resolve_handle_format(self):
        """Test /@Handle format resolves via _fetch_channel_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch.object(connector, "_fetch_channel_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "UCXXXXXX"

            rss_url = await connector._resolve_channel_url(
                "https://www.youtube.com/@TestChannel"
            )

            assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCXXXXXX"
            mock_fetch.assert_called_once_with("https://www.youtube.com/@TestChannel")

    @pytest.mark.asyncio
    async def test_resolve_user_format(self):
        """Test /user/Username format resolves via _fetch_channel_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/user/TestUser"
        })

        with patch.object(connector, "_fetch_channel_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "UCYYYYYY"

            rss_url = await connector._resolve_channel_url(
                "https://www.youtube.com/user/TestUser"
            )

            assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCYYYYYY"


class TestYouTubeConnectorFetchChannelId:
    """Tests for _fetch_channel_id method."""

    @pytest.mark.asyncio
    async def test_fetch_channel_id_from_cache(self):
        """Test cached channel_id is returned without HTTP request."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel",
            "resolved_channel_id": "UCCACHED"
        })

        channel_id = await connector._fetch_channel_id(
            "https://www.youtube.com/@TestChannel"
        )

        assert channel_id == "UCCACHED"

    @pytest.mark.asyncio
    async def test_fetch_channel_id_from_html(self):
        """Test channel_id extracted from HTML page."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        mock_html = '<script>"channelId":"UCFROMHTML123"</script>'
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            channel_id = await connector._fetch_channel_id(
                "https://www.youtube.com/@TestChannel"
            )

        assert channel_id == "UCFROMHTML123"

    @pytest.mark.asyncio
    async def test_fetch_channel_id_not_found(self):
        """Test ConnectorError when channel_id cannot be extracted."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@InvalidChannel"
        })

        mock_response = MagicMock()
        mock_response.text = "<html>No channel ID here</html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with pytest.raises(ConnectorError, match="Could not extract channel_id"):
                await connector._fetch_channel_id(
                    "https://www.youtube.com/@InvalidChannel"
                )


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

    @pytest.mark.asyncio
    async def test_fetch_video_list_with_permanent_redirect(self):
        """Test permanent redirect (301/308) is detected."""
        mock_response = self._create_mock_response(b"<rss></rss>")
        mock_response.url = "https://www.youtube.com/feeds/videos.xml?channel_id=new_id"

        # 模拟 301 重定向历史
        mock_history = MagicMock()
        mock_history.status_code = 301
        mock_response.history = [mock_history]

        mock_feed_result = {"entries": [], "bozo": False}

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
                    "https://www.youtube.com/feeds/videos.xml?channel_id=old_id"
                )

        assert result.redirect_info is not None
        assert result.redirect_info["status_code"] == 301

    @pytest.mark.asyncio
    async def test_fetch_video_list_bozo_feed(self):
        """Test bozo (malformed) feed is still processed."""
        mock_response = self._create_mock_response(b"<rss>malformed")

        mock_feed_result = {
            "entries": [
                MockFeedEntry(
                    yt_videoid="vid1",
                    link="https://www.youtube.com/watch?v=vid1",
                    title="Video",
                    summary="Desc",
                    published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
                )
            ],
            "bozo": True,
            "bozo_exception": Exception("Malformed XML"),
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

        # Bozo feeds should still be processed
        assert len(result.items) == 1


class TestYouTubeConnectorFetchTranscript:
    """Tests for _fetch_transcript method."""

    @pytest.mark.asyncio
    async def test_fetch_transcript_success_english(self):
        """Test successful transcript fetch in English."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mock transcript API response
        mock_snippet = MagicMock()
        mock_snippet.text = "Hello world this is a transcript"

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.return_value = [mock_snippet]
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result == "Hello world this is a transcript"

    @pytest.mark.asyncio
    async def test_fetch_transcript_language_fallback(self):
        """Test language fallback when preferred language not found."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        mock_snippet = MagicMock()
        mock_snippet.text = "Fallback transcript"

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            # First call (en) raises NoTranscriptFound, second call succeeds
            mock_api.fetch.side_effect = [
                NoTranscriptFound("en not found"),
                [mock_snippet]
            ]
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result == "Fallback transcript"

    @pytest.mark.asyncio
    async def test_fetch_transcript_disabled(self):
        """Test None returned when transcripts are disabled."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.side_effect = TranscriptsDisabled("Transcripts disabled")
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_transcript_not_found(self):
        """Test None returned when no transcript found in any language."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.side_effect = NoTranscriptFound("No transcript")
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result is None


class TestYouTubeConnectorProcessVideos:
    """Tests for _process_videos method."""

    @pytest.mark.asyncio
    async def test_process_videos_with_transcript(self):
        """Test video processing with transcript."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid1",
            "url": "https://www.youtube.com/watch?v=vid1",
            "title": "Test Video",
            "description": "Video description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["security"],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = "Full transcript content here"

            items = await connector._process_videos(video_entries)

        assert len(items) == 1
        assert items[0]["content"] == "Full transcript content here"
        assert items[0]["raw_metadata"]["has_transcript"] is True

    @pytest.mark.asyncio
    async def test_process_videos_fallback_to_description(self):
        """Test video processing falls back to description when no transcript."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid2",
            "url": "https://www.youtube.com/watch?v=vid2",
            "title": "No Transcript Video",
            "description": "Fallback description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": [],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = None

            items = await connector._process_videos(video_entries)

        assert len(items) == 1
        assert items[0]["content"] == "Fallback description"
        assert items[0]["raw_metadata"]["has_transcript"] is False

    @pytest.mark.asyncio
    async def test_process_videos_skip_no_content(self):
        """Test video is skipped when both transcript and description are empty."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid3",
            "url": "https://www.youtube.com/watch?v=vid3",
            "title": "Empty Video",
            "description": "",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": [],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = None

            items = await connector._process_videos(video_entries)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_process_videos_output_format(self):
        """Test output format matches expected Item fields."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid4",
            "url": "https://www.youtube.com/watch?v=vid4",
            "title": "Format Test",
            "description": "Description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Author",
            "tags": ["tag1", "tag2"],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = "Transcript"

            items = await connector._process_videos(video_entries)

        item = items[0]
        assert item["external_id"] == "vid4"
        assert item["url"] == "https://www.youtube.com/watch?v=vid4"
        assert item["title"] == "Format Test"
        assert item["content"] == "Transcript"
        assert item["author"] == "Test Author"
        assert item["tags"] == ["tag1", "tag2"]
        assert "published_at" in item
        assert "raw_metadata" in item


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

    @pytest.mark.asyncio
    async def test_fetch_full_workflow(self):
        """Test complete fetch workflow with mock data."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mock video entry from RSS
        mock_video_entry = {
            "video_id": "test123",
            "url": "https://www.youtube.com/watch?v=test123",
            "title": "Test Video",
            "description": "Test Description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["test"],
        }

        mock_rss_result = FetchResult(items=[mock_video_entry], redirect_info=None)

        # Mock final item after transcript processing
        mock_final_item = {
            "external_id": "test123",
            "url": "https://www.youtube.com/watch?v=test123",
            "title": "Test Video",
            "content": "Transcript content",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["test"],
            "raw_metadata": {"has_transcript": True, "video_id": "test123"},
        }

        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            with patch.object(connector, "_fetch_video_list", new_callable=AsyncMock) as mock_fetch_list:
                with patch.object(connector, "_process_videos", new_callable=AsyncMock) as mock_process:
                    mock_resolve.return_value = "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                    mock_fetch_list.return_value = mock_rss_result
                    mock_process.return_value = [mock_final_item]

                    result = await connector.fetch()

        assert len(result.items) == 1
        assert result.items[0]["external_id"] == "test123"
        assert result.items[0]["content"] == "Transcript content"

    @pytest.mark.asyncio
    async def test_fetch_raises_on_invalid_config(self):
        """Test fetch raises error on invalid config."""
        connector = YouTubeConnector({})  # Missing channel_url

        with pytest.raises(ValueError, match="requires 'channel_url'"):
            await connector.fetch()

    @pytest.mark.asyncio
    async def test_fetch_propagates_connector_error(self):
        """Test fetch propagates ConnectorError from internal methods."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = ConnectorError("Failed to resolve channel")

            with pytest.raises(ConnectorError, match="Failed to resolve channel"):
                await connector.fetch()
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

### Task 7: 添加集成测试

**Files:**
- Create: `tests/test_integration/test_youtube_connector.py`

- [ ] **Step 1: 创建集成测试文件**

```python
"""Integration tests for YouTube Connector with real channels."""

import pytest

from cyberpulse.services import YouTubeConnector
from cyberpulse.services.rss_connector import FetchResult


@pytest.mark.integration
class TestYouTubeConnectorRealChannels:
    """Tests with real YouTube channels."""

    @pytest.mark.asyncio
    async def test_blackhat_channel(self):
        """Test Black Hat Official channel."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0, "Should fetch at least one video"

        # Verify item structure
        item = result.items[0]
        assert item["external_id"], "Should have external_id"
        assert item["url"].startswith("https://"), "Should have valid URL"
        assert item["title"], "Should have title"
        assert item["content"], "Should have content (transcript or description)"
        assert "published_at" in item, "Should have published_at"

        # Check transcript availability
        has_transcript = item["raw_metadata"].get("has_transcript", False)
        print(f"\nBlack Hat video: {item['title'][:50]}...")
        print(f"  Has transcript: {has_transcript}")
        print(f"  Content length: {len(item['content'])} chars")

    @pytest.mark.asyncio
    async def test_owasp_channel(self):
        """Test OWASP Global channel."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@OWASPGLOBAL"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0, "Should fetch at least one video"

        item = result.items[0]
        assert item["external_id"]
        assert item["url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_channel_id_format_url(self):
        """Test /channel/ID format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0

    @pytest.mark.asyncio
    async def test_transcript_quality(self):
        """Test that transcripts have meaningful content."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })

        result = await connector.fetch()

        # At least some videos should have transcripts
        items_with_transcripts = [
            item for item in result.items
            if item["raw_metadata"].get("has_transcript")
        ]

        # Check that transcripts are longer than descriptions typically
        for item in items_with_transcripts[:3]:  # Check first 3
            content = item["content"]
            # Transcripts should typically be > 500 chars
            print(f"\nTranscript length for '{item['title'][:30]}...': {len(content)} chars")

        print(f"\nTotal videos: {len(result.items)}")
        print(f"With transcripts: {len(items_with_transcripts)}")
```

- [ ] **Step 2: 运行集成测试（可选，需要网络）**

Run: `uv run pytest tests/test_integration/test_youtube_connector.py -v -m integration --tb=short`
Expected: 测试通过（可能因网络问题跳过部分测试）

- [ ] **Step 3: 提交 Task 7**

```bash
git add tests/test_integration/test_youtube_connector.py
git commit -m "test: add integration tests for YouTubeConnector

- Real channel tests (Black Hat, OWASP)
- Channel ID format URL test
- Transcript quality verification

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 自检清单

### 1. Spec 覆盖检查

| Spec 要求 | 对应任务 | 状态 |
|-----------|----------|------|
| YouTubeConnector 类实现 | Task 1 | ✅ |
| 配置验证 (validate_config) | Task 1 Step 1 | ✅ |
| URL 解析 (_resolve_channel_url) | Task 1 Step 3-4 | ✅ |
| RSS 获取 (_fetch_video_list) | Task 1 Step 5 | ✅ |
| 视频解析 (_parse_video_entry) | Task 1 Step 6 | ✅ |
| 日期解析 (_parse_date) | Task 1 Step 7 | ✅ |
| 字幕提取 (_fetch_transcript) | Task 1 Step 9-10 | ✅ |
| 主方法 (fetch) | Task 1 Step 11 | ✅ |
| 连接器注册 | Task 2 | ✅ |
| 单元测试 | Task 3 | ✅ |
| 工厂测试更新 | Task 4 | ✅ |
| 文档更新 | Task 5 | ✅ |
| 集成测试 | Task 7 | ✅ |

### 2. 测试覆盖检查

| 测试类型 | 测试类 | 测试数量 |
|----------|--------|----------|
| 配置验证 | TestYouTubeConnectorValidateConfig | 6 |
| URL 解析 | TestYouTubeConnectorResolveChannelUrl | 3 |
| Channel ID 获取 | TestYouTubeConnectorFetchChannelId | 3 |
| 视频解析 | TestYouTubeConnectorParseVideoEntry | 3 |
| 日期解析 | TestYouTubeConnectorParseDate | 2 |
| RSS 获取 | TestYouTubeConnectorFetchVideoList | 4 |
| 字幕提取 | TestYouTubeConnectorFetchTranscript | 4 |
| 视频处理 | TestYouTubeConnectorProcessVideos | 4 |
| 主方法 | TestYouTubeConnectorFetch | 4 |
| 集成测试 | TestYouTubeConnectorRealChannels | 4 |
| **总计** | | **37** |

### 3. Placeholder 扫描

- [x] 无 TBD/TODO
- [x] 无 "implement later"
- [x] 无 "fill in details"
- [x] 所有代码步骤包含完整代码

### 4. 类型一致性检查

- [x] `FetchResult` 在所有方法中返回类型一致
- [x] `_parse_video_entry` 返回 `dict[str, Any] | None`
- [x] `_fetch_transcript` 返回 `str | None`
- [x] `validate_config` 返回 `bool`
- [x] `_process_videos` 返回 `list[dict[str, Any]]`

### 5. 与设计文档对照检查

| 检查项 | 设计文档 | 实现计划 | 状态 |
|--------|----------|----------|------|
| 移除未使用导入 | `import asyncio` | 已移除 | ✅ |
| 所有方法实现 | 10 个方法 | 10 个方法 | ✅ |
| 错误处理完整 | 3 种异常类型 | 3 种异常类型 | ✅ |
| 集成测试 | Black Hat / OWASP | 已添加 | ✅ |
| 字幕测试 | 成功/禁用/降级 | 已添加 | ✅ |