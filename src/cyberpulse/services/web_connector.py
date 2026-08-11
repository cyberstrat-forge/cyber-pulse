"""Web Scraper Connector implementation for web page scraping."""

import asyncio
import hashlib
import logging
import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import trafilatura

from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError
from .http_headers import get_browser_headers

logger = logging.getLogger(__name__)


class WebScraperConnector(BaseConnector):
    """Connector for web scraping.

    Uses httpx for HTTP requests and trafilatura for content extraction.
    Supports both auto-detection and manual extraction modes.
    """

    # Configuration
    REQUIRED_CONFIG_KEYS = ["base_url"]
    MAX_ITEMS = 50
    MAX_PAGES = 10  # Safety limit for pagination

    # Navigation word blacklist (完全匹配排除，避免误杀 slug 含导航词的 URL)
    NAV_BLACKLIST = frozenset({
        "about", "contact", "team", "terms", "privacy",
        "policy", "careers", "tags", "category", "archive",
    })

    # Error handling configuration
    MAX_RETRIES = 3
    CONNECT_TIMEOUT = 60.0  # seconds (web pages may load slowly)
    READ_TIMEOUT = 60.0  # seconds
    RETRY_DELAYS = [10.0, 20.0, 40.0]  # exponential backoff in seconds
    SERVER_ERROR_DELAY = 30.0  # seconds to wait on server errors
    MAX_RATE_LIMIT_RETRIES = 3  # max consecutive 429 responses before giving up

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._existing_urls: set[str] | None = None

    def set_existing_ids(self, urls: set[str]) -> None:
        """注入已收录 URL 集合（内部统一规范化，保证与 _extract_links 输出同形态）。

        fetch 阶段二跳过这些链接的正文抓取（增量采集）。
        """
        self._existing_urls = {self._normalize_url(u) for u in urls}

    def validate_config(self) -> bool:
        """Validate the connector configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        # Check base_url is present and valid
        if "base_url" not in self.config:
            raise ValueError("Web scraper connector requires 'base_url' in config")

        base_url = self.config["base_url"]
        if not base_url or not isinstance(base_url, str):
            raise ValueError("Web scraper connector 'base_url' must be a non-empty string")

        # SSRF protection: validate URL
        try:
            validate_url_for_ssrf(base_url)
        except SSRFError as e:
            raise ValueError(f"Invalid base_url: {e}") from e

        # Validate extraction_mode if provided
        extraction_mode = self.config.get("extraction_mode", "auto")
        valid_modes = {"auto", "manual"}
        if extraction_mode not in valid_modes:
            raise ValueError(
                f"Invalid extraction_mode '{extraction_mode}'. "
                f"Must be one of: {', '.join(sorted(valid_modes))}"
            )

        # Validate manual mode requires selectors
        if extraction_mode == "manual":
            selectors = self.config.get("selectors", {})
            if not selectors:
                raise ValueError(
                    "Web scraper with manual extraction_mode requires 'selectors' in config"
                )

        return True

    async def fetch(self) -> list[dict[str, Any]]:
        """Scrape web pages and extract content (two-phase).

        Phase 1: fetch listing pages (base_url + pagination pages), extract
        article links as candidates.
        Phase 2: fetch content for new article URLs only (skip existing /
        non-article URLs via URL shape pre-filter).

        Returns:
            List of item dictionaries with standardized fields

        Raises:
            ConnectorError: If listing fetch fails after retries
        """
        self.validate_config()

        base_url = self.config["base_url"]
        extraction_mode = self.config.get("extraction_mode", "auto")

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.CONNECT_TIMEOUT, read=self.READ_TIMEOUT),
            follow_redirects=True,
        ) as client:
            # 阶段一：抓 listing（base_url + 分页页），提取文章链接
            listing_htmls = await self._fetch_listing_pages(client, base_url)
            candidates: list[str] = []
            for html in listing_htmls:
                candidates.extend(self._extract_links(html, base_url))
            candidates = list(dict.fromkeys(candidates))  # 跨页去重（保序）

            # 兼容路径：candidates 为空且 base_url 命中 article_url_pattern
            # （直接配置文章 URL 的源，base_url 本身即文章页）
            compat_mode = False
            if not candidates and listing_htmls and self._is_article_page(
                base_url, listing_htmls[0]
            ):
                candidates = [base_url]
                compat_mode = True

            # 阶段二：抓正文（请求前 URL 预筛，避免无效请求）
            min_content_length = self.config.get("min_content_length", 150)
            items: list[dict[str, Any]] = []
            for url in candidates:
                if self._existing_urls is not None and url in self._existing_urls:
                    continue
                # 统一候选判定（#129）：pattern 优先 -> 形态三规则
                if not compat_mode and not self._is_article_page(url, ""):
                    continue
                if len(items) >= self.MAX_ITEMS:
                    logger.warning(
                        f"Web scraper reached max items limit at {self.MAX_ITEMS} items"
                    )
                    break
                try:
                    html = await self._fetch_page_with_retry(client, url)
                except ConnectorError as e:
                    # 单 URL 失败：跳过继续（listing 是源健康信号，单篇是局部问题）
                    logger.warning(f"Skipping article '{url}': {e}")
                    continue
                item = self._extract_content(html, url, extraction_mode)
                # JS 渲染降级：render_js=true 且正文不足时用浏览器重抓
                if (
                    not item or len(item["content"]) < min_content_length
                ) and self.config.get("render_js"):
                    rendered = await self._render_with_browser(url)
                    if rendered:
                        html = rendered
                        item = self._extract_content(html, url, extraction_mode)
                # 正文裁决：提取内容 >= min_content_length 才入库（内容质量门）
                if item and len(item["content"]) >= min_content_length:
                    items.append(item)

        return items

    async def _render_with_browser(self, url: str) -> str | None:
        """Playwright 渲染页面（render_js=true 时降级用）。"""
        from .browser_fetcher import BrowserFetcher

        fetcher = BrowserFetcher(headless=True)
        return await fetcher.render(url)

    async def _fetch_listing_pages(
        self, client: httpx.AsyncClient, base_url: str
    ) -> list[str]:
        """Fetch listing pages (base_url + pagination pages), return HTML list.

        Args:
            client: httpx AsyncClient instance
            base_url: Listing page URL

        Returns:
            List of listing page HTML strings

        Raises:
            ConnectorError: If a listing page fails to fetch
        """
        pagination_type = self.config.get("pagination_type", "none")
        pagination_param = self.config.get("pagination_param", "page")
        max_pages = self.config.get("max_pages", self.MAX_PAGES)

        pages: list[str] = []
        for page_num in range(1, max_pages + 1):
            if pagination_type != "page" and page_num > 1:
                break  # 非 page 分页：只抓第一页
            url = base_url if page_num == 1 else self._get_next_page_url(
                base_url, page_num, pagination_param
            )
            try:
                html = await self._fetch_page_with_retry(client, url)
            except ConnectorError as e:
                if page_num > 1:
                    # 分页页失败（常见 404 = 没有更多页）：静默停止，不整体失败（#130）
                    logger.warning(
                        f"Pagination page {page_num} failed for '{base_url}': {e}"
                    )
                    break
                raise  # base_url 失败 = 源健康信号，整体失败
            if html:
                pages.append(html)
        return pages

    def _looks_like_article_url(self, url: str) -> bool:
        """URL 形态三规则预筛：与 base_url 同路径 -> 排除；末段纯数字 -> 排除；导航词黑名单完全匹配 -> 排除。"""
        base_path = urllib.parse.urlparse(self.config["base_url"]).path.rstrip("/")
        path = urllib.parse.urlparse(url).path.rstrip("/")
        if base_path and path == base_path:
            return False
        last_segment = path.rsplit("/", 1)[-1] if path else ""
        if last_segment.isdigit():
            return False
        if last_segment.lower() in self.NAV_BLACKLIST:
            return False
        return True

    async def _fetch_page_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        """Fetch page HTML with retry logic.

        Args:
            client: httpx AsyncClient instance
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            ConnectorError: If fetch fails after all retries
        """
        last_error: Exception | None = None
        rate_limit_count = 0

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Build headers
                headers = self._build_headers()

                response = await client.get(url, headers=headers)

                # Handle rate limiting (429)
                if response.status_code == 429:
                    rate_limit_count += 1
                    if rate_limit_count > self.MAX_RATE_LIMIT_RETRIES:
                        raise ConnectorError(
                            f"Web scraper '{url}' rate limit exceeded "
                            f"after {self.MAX_RATE_LIMIT_RETRIES} retries"
                        )
                    retry_after = float(response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limited by '{url}', waiting {retry_after}s "
                        f"(attempt {rate_limit_count}/{self.MAX_RATE_LIMIT_RETRIES})"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Check for errors
                response.raise_for_status()

                return response.text

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.MAX_RETRIES + 1} "
                    f"for '{url}': {e}"
                )
                should_retry, delay = self._handle_error(e, attempt)
                if should_retry and attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue

            except httpx.HTTPStatusError as e:
                should_retry, delay = self._handle_error(e, attempt)
                if should_retry and attempt < self.MAX_RETRIES:
                    logger.warning(
                        f"HTTP error {e.response.status_code} on attempt {attempt + 1}/"
                        f"{self.MAX_RETRIES + 1} for '{url}', retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                # Non-retryable error
                raise

            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    f"Request error on attempt {attempt + 1}/{self.MAX_RETRIES + 1} "
                    f"for '{url}': {e}"
                )
                should_retry, delay = self._handle_error(e, attempt)
                if should_retry and attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue

        # All retries exhausted
        raise ConnectorError(
            f"Max retries exceeded for web scraper '{url}': {last_error}"
        ) from last_error

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for requests.

        Returns:
            Dictionary of headers
        """
        # Use shared browser headers as base
        headers = get_browser_headers()

        # Allow config override for user_agent
        if user_agent := self.config.get("user_agent"):
            headers["User-Agent"] = user_agent

        # Add custom headers from config
        custom_headers = self.config.get("headers", {})
        headers.update(custom_headers)

        return headers

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract article links from page.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute URLs (URL-normalized, deduplicated)
        """
        links: list[str] = []

        # Get link selector from config
        link_selector = self.config.get("link_selector")
        link_pattern = self.config.get("link_pattern")

        # Use lxml for HTML parsing
        try:
            from lxml import html as lxml_html

            tree = lxml_html.fromstring(html)

            if link_selector:
                # Use XPath selector
                elements = tree.xpath(link_selector)
            else:
                # Default: find all anchor tags with href
                elements = tree.xpath("//a[@href]")

            for element in elements:
                href = element.get("href")
                if not href:
                    continue

                # Skip anchor links, javascript, and mailto
                if href.startswith(("#", "javascript:", "mailto:")):
                    continue

                # Resolve relative URLs
                absolute_url = urllib.parse.urljoin(base_url, href)

                # URL 规范化（quote 非 ASCII，safe 含 % 防二次编码）
                absolute_url = self._normalize_url(absolute_url)

                # Apply pattern filter if configured
                if link_pattern:
                    if not re.search(link_pattern, absolute_url):
                        continue

                # Only include HTTP(S) URLs
                if absolute_url.startswith(("http://", "https://")):
                    links.append(absolute_url)

        except Exception as e:
            logger.warning(f"Error extracting links from '{base_url}': {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)

        return unique_links

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL: percent-encode non-ASCII chars, keep existing escapes.

        safe 含 '%' 防止对已有 %XX 转义二次编码；external_id 以规范化 URL 为
        输入（R08），保证非 ASCII URL 的 external_id 稳定。
        """
        return urllib.parse.quote(url, safe="%/:#@?&=+~,;!$'()*_-")

    def _extract_content(
        self, html: str, url: str, extraction_mode: str = "auto"
    ) -> dict[str, Any] | None:
        """Extract content from article page using trafilatura.

        Args:
            html: HTML content
            url: URL of the page
            extraction_mode: 'auto' or 'manual'

        Returns:
            Standardized item dictionary or None if extraction fails
        """
        try:
            if extraction_mode == "manual":
                return self._extract_content_manual(html, url)
            else:
                return self._extract_content_auto(html, url)
        except Exception as e:
            logger.warning(f"Error extracting content from '{url}': {e}")
            return None

    def _extract_content_auto(self, html: str, url: str) -> dict[str, Any] | None:
        """Extract content using trafilatura's auto-detection.

        Args:
            html: HTML content
            url: URL of the page

        Returns:
            Standardized item dictionary or None if extraction fails
        """
        # Use trafilatura for extraction
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            with_metadata=True,
        )

        if not extracted:
            # Fallback: try to get at least some content
            logger.warning(f"Trafilatura extraction failed for '{url}', trying fallback")
            extracted = trafilatura.extract(html, url=url, favor_precision=False)

        if not extracted:
            logger.warning(f"No content extracted from '{url}'")
            return None

        # Get metadata
        metadata = trafilatura.extract_metadata(html)

        # Build item
        title = ""
        author = ""
        published_at = self.get_current_utc_time()

        if metadata:
            title = metadata.title or ""
            author = metadata.author or ""
            if metadata.date:
                published_at = self._parse_date(metadata.date)
                # 轻量校验：明显未来日期（> now + 7d）回退收录时间
                # （实测部分站点 metadata.date 返回页面生成日期，偏差大）
                if published_at > self.get_current_utc_time() + timedelta(days=7):
                    logger.warning(
                        f"Suspicious future date '{metadata.date}' for '{url}', "
                        f"falling back to current UTC time"
                    )
                    published_at = self.get_current_utc_time()

        # Generate external_id from URL
        external_id = self._generate_external_id(url)

        return {
            "external_id": external_id,
            "url": url,
            "title": title,
            "published_at": published_at,
            "content": extracted,
            "author": author,
            "tags": [],
        }

    def _extract_content_manual(self, html: str, url: str) -> dict[str, Any] | None:
        """Extract content using manual XPath/CSS selectors.

        Args:
            html: HTML content
            url: URL of the page

        Returns:
            Standardized item dictionary or None if extraction fails
        """
        selectors = self.config.get("selectors", {})

        try:
            from lxml import html as lxml_html

            tree = lxml_html.fromstring(html)

            # Extract title
            title = ""
            title_selector = selectors.get("title")
            if title_selector:
                title_elements = tree.xpath(title_selector)
                if title_elements:
                    title = self._get_element_text(title_elements[0])

            # Extract content
            content = ""
            content_selector = selectors.get("content")
            if content_selector:
                content_elements = tree.xpath(content_selector)
                if content_elements:
                    # Join multiple elements if needed
                    content_parts = []
                    for elem in content_elements:
                        text = self._get_element_text(elem)
                        if text:
                            content_parts.append(text)
                    content = "\n\n".join(content_parts)

            # If content extraction failed, fall back to trafilatura
            if not content:
                logger.warning(
                    f"Manual content extraction failed for '{url}', using trafilatura fallback"
                )
                content = trafilatura.extract(html, url=url) or ""

            if not content:
                return None

            # Extract author
            author = ""
            author_selector = selectors.get("author")
            if author_selector:
                author_elements = tree.xpath(author_selector)
                if author_elements:
                    author = self._get_element_text(author_elements[0])

            # Extract date
            published_at = self.get_current_utc_time()
            date_selector = selectors.get("date")
            if date_selector:
                date_elements = tree.xpath(date_selector)
                if date_elements:
                    date_text = self._get_element_text(date_elements[0])
                    published_at = self._parse_date(date_text)

            # Generate external_id from URL
            external_id = self._generate_external_id(url)

            return {
                "external_id": external_id,
                "url": url,
                "title": title,
                "published_at": published_at,
                "content": content,
                "author": author,
                "tags": [],
            }

        except Exception as e:
            logger.warning(f"Manual extraction failed for '{url}': {e}, using trafilatura fallback")
            return self._extract_content_auto(html, url)

    def _get_element_text(self, element: Any) -> str:
        """Get text content from an lxml element.

        Args:
            element: lxml element

        Returns:
            Text content string
        """
        if hasattr(element, "text_content"):
            return element.text_content().strip()
        elif isinstance(element, str):
            return element.strip()
        return ""

    def _parse_date(self, date_str: str | None) -> datetime:
        """Parse date string to timezone-aware datetime.

        Args:
            date_str: Date string to parse

        Returns:
            Timezone-aware datetime (defaults to current UTC time if parsing fails)
        """
        if not date_str:
            return self.get_current_utc_time()

        date_str = date_str.strip()

        # Try ISO format first (including with timezone)
        try:
            # Handle 'Z' suffix
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            pass

        # Try common formats
        date_formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y/%m/%d",
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                continue

        # Fallback to current time
        logger.debug(f"Could not parse date '{date_str}', using current UTC time")
        return self.get_current_utc_time()

    def _generate_external_id(self, url: str) -> str:
        """Generate external_id from URL.

        Uses URL hash as the external_id for deduplication.

        Args:
            url: URL to generate ID from

        Returns:
            External ID string
        """
        # Use MD5 hash of URL as external_id
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def _is_article_page(self, url: str, html: str) -> bool:
        """Determine if the page is an article page vs listing page.

        Article detection (R21):
        1. article_url_pattern 优先（信任管理员配置）
        2. base_url 恒按 listing
        3. URL 形态三规则（与 base_url 同路径 / 末段纯数字 / 导航词黑名单）

        Args:
            url: URL of the page
            html: HTML content (kept for signature compatibility)

        Returns:
            True if this appears to be an article page
        """
        # 1. article_url_pattern 优先（信任管理员配置）
        article_pattern = self.config.get("article_url_pattern")
        if article_pattern:
            return bool(re.search(article_pattern, url))

        # 2. base_url 恒按 listing
        if url == self.config["base_url"]:
            return False

        # 3. URL 形态排除（Task 1 已实现三规则）
        return self._looks_like_article_url(url)

    def _get_next_page_url(self, base_url: str, page: int, param: str) -> str:
        """Get URL for the next page in pagination.

        Args:
            base_url: Base URL
            page: Page number
            param: Query parameter name for page

        Returns:
            URL for the next page
        """
        parsed = urllib.parse.urlparse(base_url)
        query_params = urllib.parse.parse_qs(parsed.query)
        query_params[param] = [str(page)]

        new_query = urllib.parse.urlencode(query_params, doseq=True)
        return urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )

    def _handle_error(self, error: Exception, retry_count: int) -> tuple[bool, float]:
        """Handle errors with retry logic.

        Temporary errors (retry):
        - Network timeout
        - HTTP 500/503 (server error)

        Permanent errors (no retry):
        - HTTP 401/403 (auth failure)
        - HTTP 404 (not found)
        - Parse failures (use trafilatura fallback)

        Args:
            error: The exception that occurred
            retry_count: Current retry attempt number

        Returns:
            Tuple of (should_retry, delay_seconds)

        Raises:
            ConnectorError: For non-retryable errors
        """
        # Network timeout - retry
        if isinstance(error, httpx.TimeoutException):
            delay = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
            return True, delay

        # Request error (connection issues) - retry
        if isinstance(error, httpx.RequestError):
            delay = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
            return True, delay

        # HTTP status errors
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code

            # Server errors (500, 502, 503, 504) - retry with fixed delay
            if status_code in (500, 502, 503, 504):
                return True, self.SERVER_ERROR_DELAY

            # Authentication failures (401, 403) - no retry
            if status_code in (401, 403):
                raise ConnectorError(
                    f"Authentication failed for web scraper '{self.config['base_url']}': "
                    f"HTTP {status_code}"
                ) from error

            # Not found (404) - no retry
            if status_code == 404:
                raise ConnectorError(
                    f"Resource not found at '{self.config['base_url']}': HTTP 404"
                ) from error

            # Other client errors (4xx) - no retry
            if 400 <= status_code < 500:
                raise ConnectorError(
                    f"Client error for web scraper '{self.config['base_url']}': "
                    f"HTTP {status_code}"
                ) from error

        # Unknown error - no retry
        return False, 0
