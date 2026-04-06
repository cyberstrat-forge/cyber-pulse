# YouTube 频道字幕采集连接器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 YouTube 频道连接器，使用 YouTube Data API v3 获取视频列表，Playwright 无头浏览器提取字幕作为正文内容。

**Architecture:** 分层设计 - 视频列表层（YouTube Data API v3）+ 字幕提取层（Playwright 无头浏览器）+ 输出层（标准化 FetchResult）。

**Tech Stack:** Python 3.11+, httpx, feedparser, playwright, google-api-python-client, asyncio

---

## 文件结构

```
src/cyberpulse/services/
├── transcript_extractor.py      # 新增：Playwright 字幕提取服务
├── youtube_connector.py         # 修改：整合新方案
├── connector_factory.py         # 修改：注册 youtube 类型
└── __init__.py                  # 修改：导出

src/cyberpulse/
├── config.py                    # 修改：添加 YouTube 配置

tests/test_services/
├── test_transcript_extractor.py # 新增：字幕提取测试
└── test_youtube_connector.py    # 新增：单元测试

Dockerfile                       # 修改：安装 Playwright Chromium
pyproject.toml                   # 修改：添加 playwright 依赖
```

---

### Task 1: 添加 Playwright 依赖并更新 Dockerfile

**Files:**
- Modify: `pyproject.toml`
- Modify: `Dockerfile`

- [x] **Step 1: 确认 pyproject.toml 中的依赖**

已更新：移除 `youtube-transcript-api` 和 `yt-dlp`，添加 `playwright>=1.40.0`。

```toml
dependencies = [
    # ... existing ...
    "playwright>=1.40.0",
]
```

- [x] **Step 2: 更新 Dockerfile 安装 Playwright Chromium**

在 Dockerfile 中添加：

```dockerfile
# Install Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps chromium
```

- [x] **Step 3: 验证依赖安装**

Run: `uv sync && uv run playwright install chromium`
Expected: 成功安装 playwright 和 chromium

---

### Task 2: 创建 TranscriptExtractor 字幕提取服务

**Files:**
- Create: `src/cyberpulse/services/transcript_extractor.py`

- [x] **Step 1: 创建 transcript_extractor.py**

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
    
    Features:
    - Headless mode: No visible browser window
    - Muted audio: No sound during extraction
    - Automatic fallback detection: Handles videos without subtitles
    """
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 60,
        user_data_dir: str = "/tmp/playwright_yt_data",
    ):
        """Initialize transcript extractor.
        
        Args:
            headless: Run browser in headless mode (no window)
            timeout: Page load timeout in seconds
            user_data_dir: Directory for browser profile data
        """
        self.headless = headless
        self.timeout = timeout
        self.user_data_dir = user_data_dir
        self._browser_context: BrowserContext | None = None
    
    async def extract(self, video_url: str) -> TranscriptResult:
        """Extract transcript from a YouTube video.
        
        Args:
            video_url: Full YouTube video URL
            
        Returns:
            TranscriptResult with:
            - success: True if transcript extracted
            - text: Full transcript text (success only)
            - lines: List of {timestamp, text} dicts (success only)
            - error: Error message (failure only)
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
                
                logger.debug(f"Loading video page: {video_url}")
                await page.goto(
                    video_url,
                    wait_until="networkidle",
                    timeout=self.timeout * 1000
                )
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
                            
                            // Match timestamp (e.g., "0:03", "1:23", "10:45")
                            if (/^\\d+:\\d+$/.test(p)) {
                                if (currentText.trim()) {
                                    lines.push({ timestamp: currentTimestamp, text: currentText.trim() });
                                }
                                currentTimestamp = p;
                                currentText = '';
                            } else if (/^\\d+ seconds?$/.test(p) || /^\\d+ minutes?, \\d+ seconds?$/.test(p)) {
                                // Skip duration hints
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
                
                logger.info(f"Extracted {len(lines)} transcript lines, {len(full_text)} chars")
                
                return TranscriptResult(
                    success=True,
                    text=full_text,
                    lines=lines
                )
                
            except Exception as e:
                logger.error(f"Transcript extraction error: {e}")
                return TranscriptResult(success=False, error=str(e))
                
            finally:
                await browser.close()
    
    async def close(self):
        """Clean up browser resources."""
        if self._browser_context:
            await self._browser_context.close()
            self._browser_context = None
```

- [x] **Step 2: 验证导入**

Run: `uv run python -c "from cyberpulse.services.transcript_extractor import TranscriptExtractor; print('Import OK')"`
Expected: "Import OK"

---

### Task 3: 更新配置添加 YouTube 相关设置

**Files:**
- Modify: `src/cyberpulse/config.py`

- [x] **Step 1: 添加 YouTube 配置项**

在 Settings 类中添加：

```python
# YouTube Data API
youtube_api_key: str | None = None

# Playwright transcript extraction
youtube_transcript_timeout: int = 60  # Page load timeout (seconds)
```

- [x] **Step 2: 验证配置加载**

Run: `uv run python -c "from cyberpulse.config import settings; print('youtube_api_key:', settings.youtube_api_key)"`
Expected: "youtube_api_key: None" (或配置的值)

---

### Task 4: 重写 YouTubeConnector 整合新方案

**Files:**
- Modify: `src/cyberpulse/services/youtube_connector.py`

- [x] **Step 1: 更新导入**

移除 `yt_dlp` 和 `youtube_transcript_api`，添加新导入：

```python
"""YouTube Channel Connector implementation for video transcript collection."""

import asyncio
import email.utils
import logging
import random
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx

from ..config import settings
from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError
from .http_headers import get_browser_headers
from .rss_connector import FetchResult
from .transcript_extractor import TranscriptExtractor, TranscriptResult

logger = logging.getLogger(__name__)
```

- [x] **Step 2: 更新 _fetch_transcript 方法**

替换为使用 TranscriptExtractor：

```python
async def _fetch_transcript(self, video_id: str) -> str | None:
    """Fetch transcript for a YouTube video using Playwright.
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Transcript text or None if unavailable
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Initialize extractor if needed
    if not self._transcript_extractor:
        self._transcript_extractor = TranscriptExtractor(
            headless=True,
            timeout=getattr(settings, 'youtube_transcript_timeout', 60)
        )
    
    try:
        result = await self._transcript_extractor.extract(url)
        
        if result.success:
            return result.text
        else:
            logger.debug(f"No transcript for {video_id}: {result.error}")
            return None
            
    except Exception as e:
        logger.warning(f"Transcript extraction failed for {video_id}: {e}")
        return None
```

- [x] **Step 3: 添加类属性**

在类定义中添加：

```python
def __init__(self, config: dict[str, Any]):
    super().__init__(config)
    self._transcript_extractor: TranscriptExtractor | None = None
```

- [x] **Step 4: 移除无用方法**

删除以下不再需要的方法：
- `_run_ytdlp()`
- `_download_subtitle()`
- `_parse_vtt()`
- `_get_cookies()`
- `_parse_cookies_string()`

---

### Task 5: 更新 Dockerfile

**Files:**
- Modify: `Dockerfile`

- [x] **Step 1: 添加 Playwright 安装**

在 Dockerfile 的依赖安装部分添加：

```dockerfile
# Install Playwright dependencies and Chromium
RUN pip install playwright && \
    playwright install chromium && \
    playwright install-deps chromium
```

或在已有的 pip install 后添加：

```dockerfile
# Install Playwright for YouTube transcript extraction
RUN playwright install chromium && \
    playwright install-deps chromium
```

---

### Task 6: 编写测试用例

**Files:**
- Create: `tests/test_services/test_transcript_extractor.py`
- Modify: `tests/test_services/test_youtube_connector.py`

- [x] **Step 1: 创建 TranscriptExtractor 测试**

```python
"""Tests for TranscriptExtractor."""

import pytest
from cyberpulse.services.transcript_extractor import TranscriptExtractor, TranscriptResult


class TestTranscriptExtractor:
    """Tests for transcript extraction."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_success(self):
        """Test successful transcript extraction."""
        extractor = TranscriptExtractor(headless=True, timeout=60)
        
        # Test with a known video with subtitles
        result = await extractor.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        
        assert result.success is True
        assert result.text is not None
        assert len(result.text) > 100
        assert result.lines is not None
        assert len(result.lines) > 0
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_no_subtitles(self):
        """Test video without subtitles."""
        extractor = TranscriptExtractor(headless=True, timeout=60)
        
        # Test with a video known to have no subtitles
        result = await extractor.extract("https://www.youtube.com/watch?v=y-CSDxMMXb0")
        
        assert result.success is False
        assert result.error is not None
    
    @pytest.mark.asyncio
    async def test_extract_transcript_invalid_url(self):
        """Test with invalid URL."""
        extractor = TranscriptExtractor(headless=True, timeout=30)
        
        result = await extractor.extract("https://www.youtube.com/watch?v=invalid")
        
        # Should handle gracefully
        assert result.success is False or result.text is None
```

- [x] **Step 2: 运行测试**

Run: `uv run pytest tests/test_services/test_transcript_extractor.py -v -m integration`
Expected: 测试通过

---

### Task 7: 更新部署配置

**Files:**
- Modify: `deploy/.env`

- [x] **Step 1: 添加 YouTube API Key 配置**

在 `.env` 文件中添加：

```bash
# YouTube Data API (optional, fallback to RSS if not set)
YOUTUBE_API_KEY=your_api_key_here
```

- [x] **Step 2: 更新 docker-compose.yml**

确保 worker 服务有足够内存运行 Playwright：

```yaml
worker:
  # ... existing config ...
  environment:
    YOUTUBE_API_KEY: ${YOUTUBE_API_KEY:-}
  deploy:
    resources:
      limits:
        memory: 1G  # Playwright needs more memory
```

---

### Task 8: 端到端验证

- [x] **Step 1: 本地测试**

Run: `uv run pytest tests/test_integration/test_youtube_connector.py -v`
Expected: 集成测试通过

- [x] **Step 2: Docker 构建测试**

Run: `docker build --no-cache -t cyber-pulse:test .`
Expected: 成功构建，包含 Playwright

- [x] **Step 3: Docker 运行测试**

Run: `./scripts/cyber-pulse.sh deploy --env dev --local`
Expected: 服务正常启动

---

## 变更摘要

| 文件 | 操作 | 说明 |
|------|------|------|
| `pyproject.toml` | 修改 | 移除 yt-dlp，添加 playwright |
| `Dockerfile` | 修改 | 安装 Playwright Chromium |
| `src/cyberpulse/config.py` | 修改 | 添加 YouTube 配置项 |
| `src/cyberpulse/services/transcript_extractor.py` | 新增 | Playwright 字幕提取服务 |
| `src/cyberpulse/services/youtube_connector.py` | 修改 | 整合新方案 |
| `tests/test_services/test_transcript_extractor.py` | 新增 | 字幕提取测试 |
| `deploy/.env` | 修改 | 添加 YOUTUBE_API_KEY |

---

## 回滚计划

如果 Playwright 方案出现问题，可以：
1. 使用视频描述作为内容（已实现的降级）
2. 回退到 RSS Feed 获取视频列表（已实现）
3. 完全禁用字幕提取，仅使用描述