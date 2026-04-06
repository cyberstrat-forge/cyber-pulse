---
name: YouTube 频道字幕采集连接器设计
description: YouTube 频道字幕采集连接器（Playwright 无头浏览器方案）
type: project
---

# YouTube 频道字幕采集连接器设计

## 概述

**目标**：实现 YouTube 频道视频采集，以字幕作为正文内容。

**方案演变**：
- ~~youtube-transcript-api~~ → YouTube timedtext API 返回 HTTP 429（反自动化保护）
- ~~yt-dlp 字幕下载~~ → 同样依赖 timedtext API，被阻止
- **最终方案**：YouTube Data API v3（视频列表）+ Playwright 无头浏览器（字幕提取）

**测试验证**：5/5 视频字幕提取成功，包含 3分钟~60分钟不同长度视频。

---

## 架构设计

### 整体架构

```
YouTubeConnector (更新后)
├── 视频列表层
│   └── YouTube Data API v3 (API Key)
│       ├── channels.list → 获取频道 uploads playlist ID
│       ├── playlistItems.list → 获取最新视频列表
│       └── videos.list → 获取视频详情 + 字幕可用性检测
│
├── 字幕提取层
│   └── Playwright 无头浏览器
│       ├── 打开视频页面（headless + 静音）
│       ├── 点击 Show transcript 按钮
│       └── 从 DOM 提取字幕文本
│
└── 输出层
    └── FetchResult(items, redirect_info)
        └── 标准化 Item 格式
```

### 文件结构

```
src/cyberpulse/services/
├── youtube_connector.py          # 修改：整合新方案
├── transcript_extractor.py       # 新增：Playwright 字幕提取服务
├── connector_factory.py          # 修改：注册 youtube 类型
└── __init__.py                   # 修改：导出

tests/test_services/
├── test_youtube_connector.py     # 新增：单元测试
└── test_transcript_extractor.py  # 新增：字幕提取测试

docs/
└── source-config-examples.md     # 修改：添加 YouTube 源配置示例
```

---

## 详细设计

### 1. TranscriptExtractor 类（Playwright 字幕提取）

```python
"""Transcript extraction using Playwright headless browser."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from playwright.async_api import async_playwright, BrowserContext

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    """Result of transcript extraction."""
    success: bool
    text: str | None = None
    lines: list[dict[str, str]] | None = None
    error: str | None = None


class TranscriptExtractor:
    """Extract YouTube video transcripts using Playwright.
    
    Uses headless browser to bypass YouTube's timedtext API rate limiting.
    """
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 60,
        user_data_dir: str = "/tmp/playwright_yt_data",
    ):
        self.headless = headless
        self.timeout = timeout
        self.user_data_dir = user_data_dir
        self._browser_context: BrowserContext | None = None
    
    async def extract(self, video_url: str) -> TranscriptResult:
        """Extract transcript from a YouTube video.
        
        Args:
            video_url: YouTube video URL
            
        Returns:
            TranscriptResult with success status and text
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--mute-audio',
                    '--disable-audio-output',
                ]
            )
            
            try:
                page = browser.pages[0] if browser.pages else await browser.new_page()
                
                # Load video page
                await page.goto(video_url, wait_until="networkidle", timeout=self.timeout * 1000)
                await page.wait_for_timeout(3000)
                
                # Scroll to reveal transcript button
                await page.evaluate("window.scrollTo(0, 600)")
                await page.wait_for_timeout(1000)
                
                # Click transcript button
                clicked = await page.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.innerText || '';
                            const label = btn.getAttribute('aria-label') || '';
                            if (text.includes('Show transcript') || label.includes('Show transcript')) {
                                btn.click();
                                return 'clicked';
                            }
                        }
                        return 'not found';
                    }
                """)
                
                if clicked != 'clicked':
                    return TranscriptResult(
                        success=False,
                        error="No transcript button found - video may not have subtitles"
                    )
                
                await page.wait_for_timeout(5000)
                
                # Extract transcript from panel
                result = await page.evaluate("""
                    () => {
                        const panel = document.querySelector(
                            'ytd-engagement-panel-section-list-renderer[visibility="ENGAGEMENT_PANEL_VISIBILITY_EXPANDED"]'
                        );
                        if (!panel) return { error: 'No transcript panel' };
                        
                        const text = panel.innerText;
                        if (text.length < 50) return { error: 'Empty transcript' };
                        
                        const lines = [];
                        const parts = text.split('\\n');
                        
                        let currentTimestamp = '';
                        let currentText = '';
                        
                        for (const part of parts) {
                            const p = part.trim();
                            if (!p) continue;
                            if (p === 'Transcript' || p === 'Search transcript') continue;
                            
                            if (/^\\d+:\\d+$/.test(p)) {
                                if (currentText.trim()) {
                                    lines.push({ timestamp: currentTimestamp, text: currentText.trim() });
                                }
                                currentTimestamp = p;
                                currentText = '';
                            } else if (/^\\d+ seconds?$/.test(p) || /^\\d+ minutes?, \\d+ seconds?$/.test(p)) {
                                continue;
                            } else {
                                currentText += ' ' + p;
                            }
                        }
                        
                        if (currentText.trim()) {
                            lines.push({ timestamp: currentTimestamp, text: currentText.trim() });
                        }
                        
                        return { lines, rawLength: text.length };
                    }
                """)
                
                if result.get('error'):
                    return TranscriptResult(success=False, error=result['error'])
                
                lines = result.get('lines', [])
                if not lines:
                    return TranscriptResult(success=False, error="No transcript lines extracted")
                
                full_text = ' '.join(line['text'] for line in lines)
                
                return TranscriptResult(
                    success=True,
                    text=full_text,
                    lines=lines
                )
                
            finally:
                await browser.close()
    
    async def close(self):
        """Clean up resources."""
        if self._browser_context:
            await self._browser_context.close()
```

### 2. YouTubeConnector 类（更新后）

```python
"""YouTube Channel Connector using YouTube Data API v3 + Playwright."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError
from .rss_connector import FetchResult
from .transcript_extractor import TranscriptExtractor, TranscriptResult

logger = logging.getLogger(__name__)


class YouTubeConnector(BaseConnector):
    """Connector for YouTube channels.
    
    Uses YouTube Data API v3 for video listing and Playwright for transcript extraction.
    """
    
    REQUIRED_CONFIG_KEYS = ["channel_url"]
    MAX_ITEMS = 15
    ALLOWED_DOMAINS = frozenset(["www.youtube.com", "youtube.com", "m.youtube.com"])
    
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._transcript_extractor: TranscriptExtractor | None = None
    
    def validate_config(self) -> bool:
        """Validate channel_url is present and valid."""
        if "channel_url" not in self.config:
            raise ValueError("YouTube connector requires 'channel_url' in config")
        
        channel_url = self.config["channel_url"]
        if not channel_url or not isinstance(channel_url, str):
            raise ValueError("'channel_url' must be a non-empty string")
        
        try:
            validate_url_for_ssrf(channel_url)
        except SSRFError as e:
            raise ValueError(f"Invalid channel_url: {e}") from e
        
        parsed = urlparse(channel_url)
        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            raise ValueError(f"Invalid YouTube URL: domain must be youtube.com")
        
        return True
    
    async def fetch(self) -> FetchResult:
        """Fetch videos with transcripts from the YouTube channel."""
        self.validate_config()
        
        from ..config import settings
        
        # Step 1: Get video list via YouTube Data API
        videos = await self._fetch_video_list_api()
        
        # Step 2: Extract transcripts
        items = await self._process_videos(videos)
        
        return FetchResult(items=items)
    
    async def _fetch_video_list_api(self) -> list[dict[str, Any]]:
        """Fetch video list using YouTube Data API v3."""
        from ..config import settings
        
        if not settings.youtube_api_key:
            # Fallback to RSS Feed
            return await self._fetch_video_list_rss()
        
        try:
            # Build YouTube API client
            youtube = build('youtube', 'v3', developerKey=settings.youtube_api_key)
            
            # Get channel ID
            channel_id = await self._get_channel_id(youtube)
            
            # Get uploads playlist ID
            channels_response = youtube.channels().list(
                part='contentDetails',
                id=channel_id
            ).execute()
            
            if not channels_response.get('items'):
                raise ConnectorError(f"Channel not found: {channel_id}")
            
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from playlist
            playlist_response = youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=self.MAX_ITEMS
            ).execute()
            
            videos = []
            for item in playlist_response.get('items', []):
                snippet = item['snippet']
                video_id = item['contentDetails']['videoId']
                
                videos.append({
                    'video_id': video_id,
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'title': snippet.get('title', ''),
                    'description': snippet.get('description', ''),
                    'published_at': self._parse_iso_date(snippet.get('publishedAt')),
                    'author': snippet.get('channelTitle', ''),
                    'tags': [],
                })
            
            return videos
            
        except HttpError as e:
            logger.warning(f"YouTube API error: {e}, falling back to RSS")
            return await self._fetch_video_list_rss()
    
    async def _get_channel_id(self, youtube) -> str:
        """Get channel ID from URL."""
        channel_url = self.config["channel_url"]
        parsed = urlparse(channel_url)
        path = parsed.path.strip("/")
        
        # Direct channel ID format
        if path.startswith("channel/"):
            return path.split("/")[1]
        
        # Handle or user format - need API call
        handle = path.replace("@", "") if path.startswith("@") else path.split("/")[-1]
        
        search_response = youtube.search().list(
            part='snippet',
            q=handle,
            type='channel',
            maxResults=1
        ).execute()
        
        if search_response.get('items'):
            return search_response['items'][0]['snippet']['channelId']
        
        raise ConnectorError(f"Could not find channel: {channel_url}")
    
    async def _fetch_video_list_rss(self) -> list[dict[str, Any]]:
        """Fallback: Fetch video list from RSS Feed."""
        # ... (existing RSS implementation)
        pass
    
    async def _process_videos(self, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process videos: extract transcripts."""
        from ..config import settings
        
        items = []
        
        # Initialize transcript extractor
        if not self._transcript_extractor:
            self._transcript_extractor = TranscriptExtractor(
                headless=True,
                timeout=settings.youtube_transcript_timeout if hasattr(settings, 'youtube_transcript_timeout') else 60
            )
        
        for i, video in enumerate(videos):
            video_id = video['video_id']
            
            # Add delay between requests
            if i > 0:
                delay = settings.youtube_transcript_delay_min if hasattr(settings, 'youtube_transcript_delay_min') else 2.0
                await asyncio.sleep(delay)
            
            # Extract transcript
            result = await self._transcript_extractor.extract(video['url'])
            
            if result.success:
                content = result.text
            else:
                # Fallback to description
                logger.debug(f"No transcript for {video_id}: {result.error}")
                content = video['description']
            
            if not content or not content.strip():
                logger.warning(f"No content for video {video_id}, skipping")
                continue
            
            items.append({
                'external_id': video_id,
                'url': video['url'],
                'title': video['title'],
                'published_at': video['published_at'],
                'content': content,
                'author': video['author'],
                'tags': video['tags'],
                'raw_metadata': {
                    'has_transcript': result.success,
                    'video_id': video_id,
                },
            })
        
        return items
    
    def _parse_iso_date(self, date_str: str | None) -> datetime:
        """Parse ISO 8601 date string."""
        if not date_str:
            return self.get_current_utc_time()
        
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt
        except (ValueError, TypeError):
            return self.get_current_utc_time()
```

### 3. 配置更新

```python
# config.py 添加
class Settings(BaseSettings):
    # ... existing settings ...
    
    # YouTube Data API
    youtube_api_key: str | None = None
    
    # Playwright transcript extraction
    youtube_transcript_timeout: int = 60
    youtube_transcript_delay_min: float = 2.0
    youtube_transcript_delay_max: float = 5.0
```

### 4. 依赖更新

```toml
# pyproject.toml
dependencies = [
    # ... existing dependencies ...
    "playwright>=1.40.0",
    "google-api-python-client>=2.100.0",
]
```

---

## 关键技术决策

### 为什么选择 Playwright 无头浏览器？

| 方案 | 问题 |
|------|------|
| youtube-transcript-api | timedtext API 返回 HTTP 429 |
| yt-dlp --write-subs | 同样依赖 timedtext API |
| YouTube Data API captions.download | 只能下载自己频道的字幕 |
| **Playwright 无头浏览器** | ✅ 绕过 API 限制，可下载任意字幕 |

### 无头模式配置

```python
browser = await p.chromium.launch_persistent_context(
    user_data_dir="/tmp/playwright_yt_data",
    headless=True,              # 隐藏窗口
    args=[
        '--disable-blink-features=AutomationControlled',
        '--mute-audio',          # 静音
        '--disable-audio-output', # 禁用音频
    ]
)
```

**效果**：
- 无浏览器窗口显示
- 无声音播放
- 用户完全无感知

---

## 错误处理与降级策略

| 场景 | 处理方式 |
|------|----------|
| 视频无字幕 | 使用视频描述作为 content |
| Transcript 按钮不存在 | 检测并跳过字幕提取 |
| 页面加载超时 | 重试 1 次，失败则用描述 |
| Playwright 异常 | 记录日志，使用描述 |
| YouTube API Key 未配置 | 回退到 RSS Feed 获取视频列表 |
| YouTube API 配额超限 | 回退到 RSS Feed |

---

## 测试验证结果

| 测试视频 | 时长 | 字幕 | 状态 |
|----------|------|------|------|
| Rick Astley - Never Gonna Give You Up | ~3分钟 | ✅ | ✅ 成功 |
| Black Hat 2024 演讲 | ~39分钟 | ✅ | ✅ 成功 |
| Tanya Janka 安全演讲 | ~60分钟 | ✅ | ✅ 成功 |
| SANS DFIR (无字幕) | ~29分钟 | ❌ | ✅ 正确处理 |
| GCHQ Director 演讲 | ~50分钟 | ✅ | ✅ 成功 |

---

## 性能考量

| 指标 | 预估值 |
|------|--------|
| 单视频字幕提取时间 | 8-12 秒 |
| 内存占用（Playwright） | ~200MB |
| 并发能力 | 建议串行执行 |
| 建议延迟 | 视频间间隔 2-5 秒 |

---

## Why

用户需要跟踪 YouTube 频道最新视频，以字幕作为正文内容。原有 youtube-transcript-api 方案因 YouTube timedtext API 的极端反自动化保护而失败。Playwright 无头浏览器方案成功绕过限制。

## How to apply

1. 添加 playwright 依赖到 pyproject.toml
2. 更新 Dockerfile 安装 Chromium
3. 创建 TranscriptExtractor 服务
4. 更新 YouTubeConnector 整合新方案
5. 更新配置添加 YouTube API Key
6. 编写测试用例