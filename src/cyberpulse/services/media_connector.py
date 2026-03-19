"""Media API Connector implementation for media platform data collection."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .connector_service import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class YouTubeRetryableError(Exception):
    """Exception for YouTube errors that should be retried."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


class MediaAPIConnector(BaseConnector):
    """Connector for media platforms (YouTube).

    Fetches video content from media platform APIs.
    Supports YouTube Data API v3.
    """

    # Configuration
    REQUIRED_CONFIG_KEYS = ["platform", "api_key"]
    MAX_ITEMS = 50
    SUPPORTED_PLATFORMS = {"youtube"}

    # Error handling configuration (per Spec 4.7.2)
    MAX_RETRIES = 3
    CONNECT_TIMEOUT = 30.0  # seconds
    READ_TIMEOUT = 30.0  # seconds
    RETRY_DELAYS = [10.0, 20.0, 40.0]  # exponential backoff in seconds

    # YouTube API endpoints
    YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    YOUTUBE_CAPTIONS_URL = "https://www.googleapis.com/youtube/v3/captions"

    def validate_config(self) -> bool:
        """Validate the connector configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        # Check platform is present
        if "platform" not in self.config:
            raise ValueError("Media API connector requires 'platform' in config")

        platform = self.config["platform"]
        if not platform or not isinstance(platform, str):
            raise ValueError("Media API connector 'platform' must be a non-empty string")

        # Check platform is supported
        if platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform '{platform}'. "
                f"Supported platforms: {', '.join(sorted(self.SUPPORTED_PLATFORMS))}"
            )

        # Check api_key is present
        if "api_key" not in self.config:
            raise ValueError("Media API connector requires 'api_key' in config")

        api_key = self.config["api_key"]
        if not api_key or not isinstance(api_key, str):
            raise ValueError("Media API connector 'api_key' must be a non-empty string")

        # Platform-specific validation
        if platform == "youtube":
            if "channel_id" not in self.config:
                raise ValueError("YouTube connector requires 'channel_id' in config")

            channel_id = self.config["channel_id"]
            if not channel_id or not isinstance(channel_id, str):
                raise ValueError("YouTube connector 'channel_id' must be a non-empty string")

        return True

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from media API.

        Returns:
            List of item dictionaries with standardized fields

        Raises:
            ConnectorError: If fetch fails after retries
        """
        self.validate_config()

        platform = self.config["platform"]

        if platform == "youtube":
            return await self._fetch_youtube_videos()

        # This shouldn't happen due to validation, but handle it gracefully
        raise ConnectorError(f"Unsupported platform: {platform}")

    async def _fetch_youtube_videos(self) -> List[Dict[str, Any]]:
        """Fetch videos from YouTube channel.

        Returns:
            List of standardized item dictionaries

        Raises:
            ConnectorError: If fetch fails after retries
        """
        channel_id = self.config["channel_id"]
        api_key = self.config["api_key"]
        max_results = self.config.get("max_results", self.MAX_ITEMS)

        params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "maxResults": max_results,
            "type": "video",
            "key": api_key,
        }

        all_items: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.CONNECT_TIMEOUT, read=self.READ_TIMEOUT)
        ) as client:
            try:
                data = await self._make_request_with_retry(
                    client, self.YOUTUBE_SEARCH_URL, params
                )

                # Parse videos from response
                items = data.get("items", [])
                for item in items:
                    parsed_item = self._parse_youtube_video(item)
                    if parsed_item:
                        all_items.append(parsed_item)

            except ConnectorError:
                raise
            except Exception as e:
                raise ConnectorError(
                    f"Unexpected error fetching YouTube videos for channel '{channel_id}': {e}"
                ) from e

        return all_items[: self.MAX_ITEMS]

    def _parse_youtube_video(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a YouTube video item into standardized format.

        Args:
            item: Raw video item from YouTube API

        Returns:
            Standardized item dictionary or None if invalid
        """
        # Get video ID
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            return None

        snippet = item.get("snippet", {})

        # Get title
        title = snippet.get("title", "")

        # Get description as content
        content = snippet.get("description", "")

        # Get publication date
        published_at_str = snippet.get("publishedAt")
        published_at = self._parse_date(published_at_str)

        # Get author (channel name)
        author = snippet.get("channelTitle", "")

        # Get tags
        tags = snippet.get("tags", [])

        # Build URL
        url = f"https://www.youtube.com/watch?v={video_id}"

        # Generate content hash
        content_hash = self.generate_content_hash(content)

        return {
            "external_id": video_id,
            "url": url,
            "title": title,
            "published_at": published_at,
            "content": content,
            "content_hash": content_hash,
            "author": author,
            "tags": tags,
        }

    async def _check_captions(self, client: httpx.AsyncClient, video_id: str) -> bool:
        """Check if video has captions.

        Args:
            client: httpx AsyncClient instance
            video_id: YouTube video ID

        Returns:
            True if video has captions, False otherwise
        """
        api_key = self.config["api_key"]

        params = {
            "part": "snippet",
            "videoId": video_id,
            "key": api_key,
        }

        try:
            response = await client.get(self.YOUTUBE_CAPTIONS_URL, params=params)
            response.raise_for_status()
            data = response.json()
            return len(data.get("items", [])) > 0
        except Exception as e:
            logger.debug(f"Error checking captions for video {video_id}: {e}")
            return False

    async def _make_request_with_retry(
        self, client: httpx.AsyncClient, url: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            client: httpx AsyncClient instance
            url: Request URL
            params: Query parameters

        Returns:
            Parsed JSON response data

        Raises:
            ConnectorError: If request fails after all retries
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await client.get(url, params=params)

                # Check for YouTube-specific errors before raising for status
                if response.status_code >= 400:
                    self._check_youtube_error(response, attempt)

                response.raise_for_status()
                return response.json()

            except YouTubeRetryableError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(
                        f"YouTube {e.reason}, will retry in {delay}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise ConnectorError(
                    f"YouTube API {e.reason}, max retries exhausted"
                ) from e

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

            except ConnectorError:
                raise

        # All retries exhausted
        raise ConnectorError(
            f"Max retries exceeded for YouTube API '{url}': {last_error}"
        ) from last_error

    def _check_youtube_error(self, response: httpx.Response, attempt: int) -> None:
        """Check for YouTube-specific errors in response.

        Args:
            response: HTTP response with error status
            attempt: Current retry attempt number

        Raises:
            YouTubeRetryableError: For retryable errors (quota exceeded)
            ConnectorError: For non-retryable errors
        """
        try:
            error_data = response.json()
            errors = error_data.get("error", {}).get("errors", [])

            for error in errors:
                reason = error.get("reason", "")

                # Quota exceeded - retry
                if reason == "quotaExceeded":
                    raise YouTubeRetryableError(
                        reason, "YouTube API quota exceeded"
                    )

                # Invalid API key - no retry
                if reason == "keyInvalid":
                    raise ConnectorError(
                        "Invalid API key for YouTube API"
                    )

                # Channel not found - no retry
                if reason == "channelNotFound":
                    raise ConnectorError(
                        f"Channel not found: {self.config.get('channel_id')}"
                    )

        except ConnectorError:
            raise
        except YouTubeRetryableError:
            raise
        except Exception as e:
            # Not a structured YouTube error, log and fall through to generic handling
            logger.debug(f"Could not parse YouTube error response: {e}")

    def _handle_error(self, error: Exception, retry_count: int) -> tuple[bool, float]:
        """Handle errors with retry logic.

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

            # Server errors (500, 503) - retry
            if status_code in (500, 502, 503, 504):
                delay = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
                return True, delay

            # Authentication failures (401, 403) - no retry
            if status_code in (401, 403):
                raise ConnectorError(
                    f"Authentication failed for YouTube API: HTTP {status_code}"
                ) from error

            # Not found (404) - no retry
            if status_code == 404:
                raise ConnectorError(
                    "Resource not found on YouTube API: HTTP 404"
                ) from error

            # Other client errors (4xx) - no retry
            if 400 <= status_code < 500:
                raise ConnectorError(
                    f"Client error for YouTube API: HTTP {status_code}"
                ) from error

        # Unknown error - no retry
        return False, 0

    def _parse_date(self, date_value: Optional[str]) -> datetime:
        """Parse date from ISO 8601 format.

        Args:
            date_value: ISO 8601 date string

        Returns:
            Timezone-aware datetime (defaults to current UTC time if parsing fails)
        """
        if not date_value:
            return self.get_current_utc_time()

        if isinstance(date_value, str):
            # YouTube uses ISO 8601 format
            try:
                # Handle 'Z' suffix
                if date_value.endswith("Z"):
                    date_value = date_value[:-1] + "+00:00"
                dt = datetime.fromisoformat(date_value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass

        # Fallback to current time
        logger.debug(f"Could not parse date '{date_value}', using current UTC time")
        return self.get_current_utc_time()