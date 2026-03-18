"""RSS Connector implementation for RSS feed collection."""

import email.utils
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import feedparser

from .connector_service import BaseConnector, ConnectorError


class RSSConnector(BaseConnector):
    """Connector for RSS/Atom feeds.

    Uses feedparser to parse RSS feeds. Supports both standard and
    bozo (malformed) feeds.
    """

    MAX_ITEMS = 50
    REQUIRED_CONFIG_KEYS = ["feed_url"]

    def validate_config(self) -> bool:
        """Validate that feed_url is present in config.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If feed_url is missing
        """
        if "feed_url" not in self.config:
            raise ValueError("RSS connector requires 'feed_url' in config")

        feed_url = self.config["feed_url"]
        if not feed_url or not isinstance(feed_url, str):
            raise ValueError("RSS connector 'feed_url' must be a non-empty string")

        return True

    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from the RSS feed.

        Returns:
            List of item dictionaries with standardized fields

        Raises:
            ConnectorError: If feed cannot be fetched or parsed
        """
        self.validate_config()

        feed_url = self.config["feed_url"]

        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            raise ConnectorError(f"Failed to fetch RSS feed: {e}")

        # Check for fatal errors (not bozo errors, which we tolerate)
        if feed.get("bozo") and not isinstance(
            feed.get("bozo_exception"), feedparser.NonXMLContentType
        ):
            # Log bozo errors but continue processing
            # Bozo feeds are allowed as per requirements
            pass

        # Get entries, limited to MAX_ITEMS
        entries = feed.get("entries", [])[: self.MAX_ITEMS]

        items = []
        for entry in entries:
            try:
                item = self._parse_entry(entry)
                if item:
                    items.append(item)
            except Exception:
                # Skip malformed entries
                continue

        return items

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

        return {
            "external_id": external_id,
            "url": url,
            "title": title,
            "published_at": published_at,
            "content": content,
            "content_hash": content_hash,
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