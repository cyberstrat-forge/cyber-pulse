"""RSS Connector implementation for RSS feed collection."""

import email.utils
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """RSS 采集结果"""
    items: List[Dict[str, Any]]
    redirect_info: Optional[Dict[str, Any]] = None  # {"original_url": "...", "final_url": "...", "status_code": 301}


class RSSConnector(BaseConnector):
    """Connector for RSS/Atom feeds.

    Uses feedparser to parse RSS feeds. Supports both standard and
    bozo (malformed) feeds.
    """

    MAX_ITEMS = 50
    REQUIRED_CONFIG_KEYS = ["feed_url"]

    # 默认浏览器 User-Agent
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def validate_config(self) -> bool:
        """Validate that feed_url is present in config.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If feed_url is missing or invalid
        """
        if "feed_url" not in self.config:
            raise ValueError("RSS connector requires 'feed_url' in config")

        feed_url = self.config["feed_url"]
        if not feed_url or not isinstance(feed_url, str):
            raise ValueError("RSS connector 'feed_url' must be a non-empty string")

        # SSRF protection: validate URL scheme and destination
        try:
            validate_url_for_ssrf(feed_url)
        except SSRFError as e:
            raise ValueError(f"Invalid feed_url: {e}") from e

        return True

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
            # Log bozo errors but continue processing
            # Bozo feeds are allowed as per requirements
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
                # Skip malformed entries but log the error
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

    def _parse_entry(self, entry: Any) -> Optional[Dict[str, Any]]:
        """Parse a single RSS entry into standardized format.

        Args:
            entry: feedparser entry object

        Returns:
            Standardized item dictionary or None if entry is invalid
        """
        # Get external_id - prefer guid, fallback to link
        external_id = entry.get("guid") or entry.get("id") or entry.get("link")
        if not external_id:
            return None

        # Get URL - use link
        url = entry.get("link")
        if not url:
            return None

        # Get title
        title = entry.get("title", "")

        # Get content
        content = self._get_content(entry)

        # Parse published date
        published_at = self._parse_date(entry)

        # Generate content hash
        content_hash = self.generate_content_hash(content)

        # Get author
        author = entry.get("author", "")

        # Get tags
        tags = []
        if hasattr(entry, "tags") and entry.tags:
            tags = [t.term for t in entry.tags if hasattr(t, "term")]

        return {
            "external_id": external_id,
            "url": url,
            "title": title,
            "published_at": published_at,
            "content": content,
            "content_hash": content_hash,
            "author": author,
            "tags": tags,
        }

    def _parse_date(self, entry: Any) -> datetime:
        """Parse publication date from RSS entry.

        Tries multiple date fields and formats.

        Args:
            entry: feedparser entry object

        Returns:
            Timezone-aware datetime (defaults to current UTC time if parsing fails)
        """
        # Try published_parsed first
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                # feedparser returns time.struct_time
                dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                pass

        # Try published string
        published = entry.get("published") or entry.get("pubDate")
        if published:
            try:
                # Try email.utils parsedate_to_datetime (RFC 2822 format)
                parsed = email.utils.parsedate_to_datetime(published)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except (TypeError, ValueError):
                pass

        # Fallback to current time
        logger.debug(
            "No valid publication date found in RSS entry, using current UTC time"
        )
        return self.get_current_utc_time()

    def _get_content(self, entry: Any) -> str:
        """Extract content from RSS entry.

        Tries multiple content fields in order of preference.

        Args:
            entry: feedparser entry object

        Returns:
            Content string (may be empty)
        """
        # Try content field first (often contains full content)
        if hasattr(entry, "content") and entry.content:
            # content is a list of content objects
            for content_obj in entry.content:
                if hasattr(content_obj, "value"):
                    return content_obj.value

        # Try summary/description
        summary = entry.get("summary") or entry.get("description") or ""
        return summary