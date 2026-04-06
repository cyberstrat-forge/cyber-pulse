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
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from .base import SSRFError, validate_url_for_ssrf
from .connector_service import BaseConnector, ConnectorError
from .http_headers import get_browser_headers
from .rss_connector import FetchResult  # Reuse RSS FetchResult dataclass

logger = logging.getLogger(__name__)


class YouTubeConnector(BaseConnector):
    """Connector for YouTube channels.

    Fetches video transcripts using RSS Feed + youtube-transcript-api.
    No API Key required.
    """

    # Configuration
    REQUIRED_CONFIG_KEYS = ["channel_url"]
    MAX_ITEMS = 15  # RSS Feed default returns 15 items

    # Transcript language priority
    TRANSCRIPT_LANGUAGE_PRIORITY = ["en", "en-US", "en-GB"]

    # Allowed domains
    ALLOWED_DOMAINS = frozenset(["www.youtube.com", "youtube.com", "m.youtube.com"])

    def validate_config(self) -> bool:
        """Validate that channel_url is present and valid.

        Supports both 'channel_url' and 'feed_url' config keys for compatibility
        with api.sh script which uses 'feed_url'.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If channel_url is missing or invalid
        """
        # Support both channel_url and feed_url (api.sh uses feed_url)
        # Use "in" check to distinguish between missing key and empty string
        if "channel_url" in self.config:
            channel_url = self.config["channel_url"]
        elif "feed_url" in self.config:
            channel_url = self.config["feed_url"]
        else:
            raise ValueError(
                "YouTube connector requires 'channel_url' (or 'feed_url') in config"
            )

        if not channel_url or not isinstance(channel_url, str):
            raise ValueError(
                "YouTube connector 'channel_url' must be a non-empty string"
            )

        # Store normalized key for fetch()
        self.config["channel_url"] = channel_url

        # SSRF protection: validate URL scheme and destination
        try:
            validate_url_for_ssrf(channel_url)
        except SSRFError as e:
            raise ValueError(f"Invalid channel_url: {e}") from e

        # Validate YouTube domain
        parsed = urlparse(channel_url)
        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            raise ValueError(
                f"Invalid YouTube URL: domain must be youtube.com, "
                f"got '{parsed.netloc}'"
            )

        return True

    async def fetch(self) -> FetchResult:  # type: ignore[override]
        # Note: type ignore needed because BaseConnector.fetch has different
        # return type signature. This is intentional for connector polymorphism.
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
        except ConnectorError:
            raise
        except httpx.HTTPStatusError as e:
            raise ConnectorError(
                f"Failed to resolve YouTube channel: HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ConnectorError(
                f"Failed to resolve YouTube channel: {type(e).__name__}: {e}"
            ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error resolving channel {channel_url}: "
                f"{type(e).__name__}: {e}"
            )
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

            # Extract content outside async with to avoid scope issues
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
                            f"YouTube RSS permanently redirected: "
                            f"{rss_url} -> {final_url}"
                        )
                        break

            # Parse RSS with feedparser
            feed = feedparser.parse(content)

            # Handle bozo (malformed) feeds
            if feed.get("bozo"):
                logger.warning(
                    f"YouTube RSS feed has malformed content: "
                    f"{feed.get('bozo_exception')}"
                )

            entries = feed.get("entries", [])[: self.MAX_ITEMS]

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
                f"Failed to fetch YouTube RSS '{rss_url}': "
                f"HTTP {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ConnectorError(
                f"Failed to fetch YouTube RSS '{rss_url}': {type(e).__name__}: {e}"
            ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error fetching YouTube RSS '{rss_url}': "
                f"{type(e).__name__}: {e}"
            )
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
                # feedparser returns time.struct_time which is 9-tuple
                # First 6 elements: year, month, day, hour, minute, second
                time_tuple = entry.published_parsed
                dt = datetime(
                    time_tuple[0],  # year
                    time_tuple[1],  # month
                    time_tuple[2],  # day
                    time_tuple[3],  # hour
                    time_tuple[4],  # minute
                    time_tuple[5],  # second
                    tzinfo=UTC,
                )
                return dt
            except (TypeError, ValueError) as e:
                logger.debug(f"Failed to parse published_parsed: {e}")

        # Try published string
        published = entry.get("published") or entry.get("pubDate")
        if published:
            try:
                parsed = email.utils.parsedate_to_datetime(published)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed
            except (TypeError, ValueError) as e:
                logger.debug(f"Failed to parse date string '{published}': {e}")

        # Fallback to current time
        logger.debug("No valid publication date found, using current UTC time")
        return self.get_current_utc_time()

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

            items.append(
                {
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
                }
            )

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

            # Try preferred languages (wrap synchronous API in asyncio.to_thread)
            for lang in self.TRANSCRIPT_LANGUAGE_PRIORITY:
                try:
                    transcript_list = await asyncio.to_thread(
                        api.fetch, video_id, [lang]
                    )
                    return self._format_transcript(transcript_list)
                except NoTranscriptFound:
                    continue

            # Try auto-generated English
            try:
                transcript_list = await asyncio.to_thread(
                    api.fetch, video_id, ["en"], preserve_formatting=True
                )
                return self._format_transcript(transcript_list)
            except (TranscriptsDisabled, NoTranscriptFound) as e:
                logger.debug(
                    f"No transcript available for video {video_id}: "
                    f"{type(e).__name__}"
                )
                return None

        except TranscriptsDisabled as e:
            logger.debug(f"Transcripts disabled for video {video_id}: {e}")
            return None
        except Exception as e:
            logger.warning(
                f"Unexpected error fetching transcript for {video_id}: "
                f"{type(e).__name__}: {e}"
            )
            return None

    def _format_transcript(self, transcript_list: Any) -> str:
        """Format transcript list into text.

        Args:
            transcript_list: Transcript data from youtube-transcript-api
                (FetchedTranscript or list-like object)

        Returns:
            Formatted transcript text
        """
        # Convert to list if needed (handle FetchedTranscript wrapper)
        transcripts = (
            list(transcript_list)
            if not isinstance(transcript_list, list)
            else transcript_list
        )

        # Extract text from snippets
        texts = []
        for snippet in transcripts:
            # Use attribute access (FetchedTranscriptSnippet)
            text = getattr(snippet, "text", None) or snippet.get("text", "")
            if text:
                texts.append(text)

        return " ".join(texts)
