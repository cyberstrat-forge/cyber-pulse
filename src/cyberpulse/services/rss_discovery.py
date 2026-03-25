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
                    href_raw = link.get("href")
                    if href_raw and isinstance(href_raw, str):
                        # 处理相对路径
                        if href_raw.startswith("/"):
                            href = urljoin(site_url, href_raw)
                        elif not href_raw.startswith(("http://", "https://")):
                            href = urljoin(site_url, href_raw)
                        else:
                            href = href_raw
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