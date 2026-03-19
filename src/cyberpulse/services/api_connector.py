"""API Connector implementation for REST API data collection."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .connector_service import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)


class APIConnector(BaseConnector):
    """Connector for REST APIs.

    Supports various authentication types and pagination strategies.
    Implements retry logic with exponential backoff for transient errors.
    """

    # Configuration
    REQUIRED_CONFIG_KEYS = ["base_url"]
    MAX_ITEMS = 50
    MAX_PAGES = 10  # Safety limit for pagination

    # Error handling configuration
    MAX_RETRIES = 3
    CONNECT_TIMEOUT = 30.0  # seconds
    READ_TIMEOUT = 30.0  # seconds
    RETRY_DELAYS = [10.0, 20.0, 40.0]  # exponential backoff in seconds
    RATE_LIMIT_DELAY = 60.0  # seconds to wait on 429

    # Default field mapping
    DEFAULT_FIELD_MAPPING = {
        "external_id": "id",
        "url": "url",
        "title": "title",
        "content": "content",
        "published_at": "published_at",
        "author": "author",
        "tags": "tags",
    }

    def validate_config(self) -> bool:
        """Validate the connector configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        # Check base_url is present and valid
        if "base_url" not in self.config:
            raise ValueError("API connector requires 'base_url' in config")

        base_url = self.config["base_url"]
        if not base_url or not isinstance(base_url, str):
            raise ValueError("API connector 'base_url' must be a non-empty string")

        # Validate auth configuration
        auth_type = self.config.get("auth_type", "none")

        if auth_type == "bearer":
            if "auth_token" not in self.config:
                raise ValueError("API connector with bearer auth requires 'auth_token' in config")

        elif auth_type == "api_key":
            if "api_key" not in self.config:
                raise ValueError("API connector with api_key auth requires 'api_key' in config")

        elif auth_type == "basic":
            if "username" not in self.config or "password" not in self.config:
                raise ValueError(
                    "API connector with basic auth requires 'username' and 'password' in config"
                )

        return True

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from API with pagination support.

        Returns:
            List of item dictionaries with standardized fields

        Raises:
            ConnectorError: If fetch fails after retries
        """
        self.validate_config()

        all_items: List[Dict[str, Any]] = []
        page = 1
        cursor: Optional[str] = None
        offset = 0

        pagination_type = self.config.get("pagination_type", "none")
        total_items: Optional[int] = None

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.CONNECT_TIMEOUT, read=self.READ_TIMEOUT)
        ) as client:
            while page <= self.MAX_PAGES:
                try:
                    # Build request
                    request = self._build_request(page=page, cursor=cursor, offset=offset)

                    # Make request with retry logic
                    data = await self._make_request_with_retry(client, request)

                    # Extract items from response
                    items = self._extract_items(data)
                    parsed_items = self._parse_response(items)
                    all_items.extend(parsed_items)

                    # Check pagination
                    if pagination_type == "none":
                        break

                    elif pagination_type == "page":
                        has_more_path = self.config.get("has_more_path", "has_more")
                        has_more = self._get_nested_value(data, has_more_path)
                        if not has_more:
                            break

                    elif pagination_type == "offset":
                        if total_items is None:
                            total_path = self.config.get("total_path", "total")
                            total_items = self._get_nested_value(data, total_path, 0)
                        page_size = self.config.get("page_size", 50)
                        offset += page_size
                        if offset >= total_items:
                            break

                    elif pagination_type == "cursor":
                        cursor_path = self.config.get("cursor_path", "next_cursor")
                        cursor = self._get_nested_value(data, cursor_path)
                        if not cursor:
                            break

                    page += 1

                    # Safety check for max items
                    if len(all_items) >= self.MAX_ITEMS * self.MAX_PAGES:
                        logger.warning(
                            f"API connector reached max items limit at {len(all_items)} items"
                        )
                        break

                except ConnectorError:
                    raise
                except Exception as e:
                    raise ConnectorError(
                        f"Unexpected error fetching from API '{self.config['base_url']}': {e}"
                    ) from e

        # Limit to MAX_ITEMS
        return all_items[: self.MAX_ITEMS * self.MAX_PAGES]

    def _build_request(
        self, page: int = 1, cursor: Optional[str] = None, offset: int = 0
    ) -> Dict[str, Any]:
        """Build request configuration.

        Args:
            page: Page number for page-based pagination
            cursor: Cursor for cursor-based pagination
            offset: Offset for offset-based pagination

        Returns:
            Dictionary with url, headers, and params
        """
        base_url = self.config["base_url"].rstrip("/")
        endpoint = self.config.get("endpoint", "")
        url = f"{base_url}{endpoint}" if endpoint else base_url

        # Build headers
        headers = dict(self.config.get("headers", {}))

        # Add authentication headers
        auth_type = self.config.get("auth_type", "none")

        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.config['auth_token']}"

        elif auth_type == "api_key":
            location = self.config.get("api_key_location", "header")
            if location == "header":
                header_name = self.config.get("api_key_header", "X-API-Key")
                headers[header_name] = self.config["api_key"]

        elif auth_type == "basic":
            import base64

            credentials = f"{self.config['username']}:{self.config['password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        # Build params
        params = dict(self.config.get("query_params", {}))

        # Add API key to query if configured
        if auth_type == "api_key" and self.config.get("api_key_location") == "query":
            param_name = self.config.get("api_key_param", "api_key")
            params[param_name] = self.config["api_key"]

        # Add pagination params
        pagination_type = self.config.get("pagination_type", "none")
        pagination_param = self.config.get("pagination_param", "page")

        if pagination_type == "page":
            params[pagination_param] = page

        elif pagination_type == "offset":
            params[pagination_param] = offset
            page_size = self.config.get("page_size", 50)
            params[self.config.get("limit_param", "limit")] = page_size

        elif pagination_type == "cursor" and cursor:
            params[pagination_param] = cursor

        return {
            "url": url,
            "headers": headers,
            "params": params,
        }

    async def _make_request_with_retry(
        self, client: httpx.AsyncClient, request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            client: httpx AsyncClient instance
            request: Request configuration dictionary

        Returns:
            Parsed JSON response data

        Raises:
            ConnectorError: If request fails after all retries
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await client.get(
                    request["url"],
                    headers=request["headers"],
                    params=request["params"],
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", self.RATE_LIMIT_DELAY))
                    logger.warning(
                        f"Rate limited by API '{request['url']}', waiting {retry_after}s"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Check for errors
                response.raise_for_status()

                return response.json()

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{self.MAX_RETRIES + 1} "
                    f"for '{request['url']}': {e}"
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
                        f"{self.MAX_RETRIES + 1} for '{request['url']}', retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                # Non-retryable error
                raise

            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    f"Request error on attempt {attempt + 1}/{self.MAX_RETRIES + 1} "
                    f"for '{request['url']}': {e}"
                )
                should_retry, delay = self._handle_error(e, attempt)
                if should_retry and attempt < self.MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue

        # All retries exhausted
        raise ConnectorError(
            f"Max retries exceeded for API '{request['url']}': {last_error}"
        ) from last_error

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

            # Rate limit (429) - retry with long delay
            if status_code == 429:
                retry_after = error.response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else self.RATE_LIMIT_DELAY
                return True, delay

            # Server errors (500, 503) - retry
            if status_code in (500, 502, 503, 504):
                delay = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
                return True, delay

            # Authentication failures (401, 403) - no retry
            if status_code in (401, 403):
                raise ConnectorError(
                    f"Authentication failed for API '{self.config['base_url']}': "
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
                    f"Client error for API '{self.config['base_url']}': HTTP {status_code}"
                ) from error

        # Unknown error - no retry
        return False, 0

    def _extract_items(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract items from API response.

        Args:
            data: Parsed JSON response

        Returns:
            List of item dictionaries
        """
        item_path = self.config.get("item_path", "items")

        if not item_path:
            # Response is the items list directly
            if isinstance(data, list):
                return data
            return [data] if isinstance(data, dict) else []

        items = self._get_nested_value(data, item_path, [])
        return items if isinstance(items, list) else []

    def _parse_response(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse API response items to standard format.

        Args:
            items: List of raw item dictionaries from API

        Returns:
            List of standardized item dictionaries
        """
        field_mapping = self.config.get("field_mapping", self.DEFAULT_FIELD_MAPPING)
        parsed_items = []

        for item in items:
            try:
                parsed_item = self._parse_item(item, field_mapping)
                if parsed_item:
                    parsed_items.append(parsed_item)
            except Exception as e:
                item_id = self._get_nested_value(
                    item, field_mapping.get("external_id", "id"), "unknown"
                )
                logger.warning(f"Skipping malformed API item '{item_id}': {e}")
                continue

        return parsed_items

    def _parse_item(
        self, item: Dict[str, Any], field_mapping: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Parse a single API item into standardized format.

        Args:
            item: Raw item dictionary from API
            field_mapping: Mapping from standard fields to API fields

        Returns:
            Standardized item dictionary or None if invalid
        """
        # Get external_id
        external_id_field = field_mapping.get("external_id", "id")
        external_id = self._get_nested_value(item, external_id_field)
        if not external_id:
            return None

        # Get URL
        url_field = field_mapping.get("url", "url")
        url = self._get_nested_value(item, url_field)
        if not url:
            return None

        # Get other fields
        title = self._get_nested_value(item, field_mapping.get("title", "title"), "")

        content_field = field_mapping.get("content", "content")
        content = self._get_nested_value(item, content_field, "")
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)

        published_at_field = field_mapping.get("published_at", "published_at")
        published_at_str = self._get_nested_value(item, published_at_field)
        published_at = self._parse_date(published_at_str)

        author = self._get_nested_value(item, field_mapping.get("author", "author"), "")

        tags_field = field_mapping.get("tags", "tags")
        tags = self._get_nested_value(item, tags_field, [])
        if isinstance(tags, str):
            tags = [tags]

        # Generate content hash
        content_hash = self.generate_content_hash(content)

        return {
            "external_id": str(external_id),
            "url": str(url),
            "title": str(title),
            "published_at": published_at,
            "content": str(content),
            "content_hash": content_hash,
            "author": str(author),
            "tags": list(tags),
        }

    def _parse_date(self, date_value: Optional[Any]) -> datetime:
        """Parse date from various formats.

        Args:
            date_value: Date value from API (string, None, etc.)

        Returns:
            Timezone-aware datetime (defaults to current UTC time if parsing fails)
        """
        if not date_value:
            return self.get_current_utc_time()

        if isinstance(date_value, datetime):
            if date_value.tzinfo is None:
                return date_value.replace(tzinfo=timezone.utc)
            return date_value.astimezone(timezone.utc)

        if isinstance(date_value, str):
            # Try ISO format first
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

    def _get_nested_value(
        self, data: Dict[str, Any], path: str, default: Any = None
    ) -> Any:
        """Get a nested value from a dictionary using dot notation.

        Args:
            data: Dictionary to get value from
            path: Dot-separated path (e.g., "data.results")
            default: Default value if path not found

        Returns:
            Value at path or default
        """
        if not path:
            return default

        current = data
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current