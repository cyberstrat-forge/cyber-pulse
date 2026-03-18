"""Base connector class for data collection."""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List


class BaseConnector(ABC):
    """Abstract base class for all connectors.

    Connectors are responsible for fetching data from external sources.
    Each connector type (RSS, API, Web Scraper, Media API) implements
    this base class.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the connector with configuration.

        Args:
            config: Connector-specific configuration dictionary
        """
        self.config = config

    @abstractmethod
    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from the source.

        Returns:
            List of item dictionaries, each containing:
                - external_id: Unique identifier from source
                - url: Item URL
                - title: Item title
                - published_at: Publication datetime (timezone-aware)
                - content: Raw content
                - content_hash: MD5 hash of content
                - author: Author name (may be empty)
                - tags: List of tags (may be empty)

        Raises:
            ConnectorError: If fetch fails
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate the connector configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        pass

    @staticmethod
    def generate_content_hash(content: str) -> str:
        """Generate MD5 hash for content deduplication.

        Args:
            content: Content string to hash

        Returns:
            MD5 hash as hex string
        """
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    @staticmethod
    def get_current_utc_time() -> datetime:
        """Get current UTC time.

        Returns:
            Current datetime with UTC timezone
        """
        return datetime.now(timezone.utc)


class ConnectorError(Exception):
    """Exception raised when connector operations fail."""

    pass