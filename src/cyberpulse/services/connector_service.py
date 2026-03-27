"""Base connector class for data collection."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any


class BaseConnector(ABC):
    """Abstract base class for all connectors.

    Connectors are responsible for fetching data from external sources.
    Each connector type (RSS, API, Web Scraper, Media API) implements
    this base class.
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the connector with configuration.

        Args:
            config: Connector-specific configuration dictionary
        """
        self.config = config

    @abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch items from the source.

        Returns:
            List of item dictionaries, each containing:
                - external_id: Unique identifier from source
                - url: Item URL
                - title: Item title
                - published_at: Publication datetime (timezone-aware)
                - content: Raw content
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
    def get_current_utc_time() -> datetime:
        """Get current UTC time.

        Returns:
            Current datetime with UTC timezone
        """
        return datetime.now(UTC)


class ConnectorError(Exception):
    """Exception raised when connector operations fail."""

    pass
