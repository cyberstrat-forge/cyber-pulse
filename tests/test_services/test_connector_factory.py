"""Tests for Connector Factory."""

from unittest.mock import MagicMock

import pytest

from cyberpulse.services import (
    RSSConnector,
    APIConnector,
    WebScraperConnector,
    MediaAPIConnector,
    CONNECTOR_REGISTRY,
    get_connector,
    get_connector_for_source,
)
from cyberpulse.services.connector_service import BaseConnector


class TestGetConnector:
    """Tests for get_connector function."""

    def test_get_connector_rss(self):
        """Test get_connector returns RSSConnector for 'rss' type."""
        config = {"feed_url": "https://example.com/feed.xml"}
        connector = get_connector("rss", config)
        assert isinstance(connector, RSSConnector)
        assert connector.config == config

    def test_get_connector_api(self):
        """Test get_connector returns APIConnector for 'api' type."""
        config = {"base_url": "https://api.example.com"}
        connector = get_connector("api", config)
        assert isinstance(connector, APIConnector)
        assert connector.config == config

    def test_get_connector_web(self):
        """Test get_connector returns WebScraperConnector for 'web' type."""
        config = {"base_url": "https://example.com"}
        connector = get_connector("web", config)
        assert isinstance(connector, WebScraperConnector)
        assert connector.config == config

    def test_get_connector_media(self):
        """Test get_connector returns MediaAPIConnector for 'media' type."""
        config = {
            "platform": "youtube",
            "api_key": "test-key",
            "channel_id": "test-channel",
        }
        connector = get_connector("media", config)
        assert isinstance(connector, MediaAPIConnector)
        assert connector.config == config

    def test_get_connector_unknown_type(self):
        """Test get_connector raises ValueError for unknown type."""
        with pytest.raises(ValueError, match="Unknown connector type: unknown"):
            get_connector("unknown", {})

    def test_get_connector_error_message_includes_available_types(self):
        """Test error message includes list of available types."""
        with pytest.raises(ValueError) as exc_info:
            get_connector("invalid_type", {})

        error_message = str(exc_info.value)
        assert "Unknown connector type: invalid_type" in error_message
        assert "Available types:" in error_message
        # Check that all known types are mentioned
        for type_name in CONNECTOR_REGISTRY.keys():
            assert type_name in error_message


class TestGetConnectorForSource:
    """Tests for get_connector_for_source function."""

    def test_get_connector_for_source_rss(self):
        """Test get_connector_for_source with RSS source."""
        mock_source = MagicMock()
        mock_source.connector_type = "rss"
        mock_source.config = {"feed_url": "https://example.com/feed.xml"}

        connector = get_connector_for_source(mock_source)
        assert isinstance(connector, RSSConnector)
        assert connector.config == mock_source.config

    def test_get_connector_for_source_api(self):
        """Test get_connector_for_source with API source."""
        mock_source = MagicMock()
        mock_source.connector_type = "api"
        mock_source.config = {"base_url": "https://api.example.com"}

        connector = get_connector_for_source(mock_source)
        assert isinstance(connector, APIConnector)
        assert connector.config == mock_source.config

    def test_get_connector_for_source_web(self):
        """Test get_connector_for_source with Web source."""
        mock_source = MagicMock()
        mock_source.connector_type = "web"
        mock_source.config = {"base_url": "https://example.com"}

        connector = get_connector_for_source(mock_source)
        assert isinstance(connector, WebScraperConnector)
        assert connector.config == mock_source.config

    def test_get_connector_for_source_media(self):
        """Test get_connector_for_source with Media source."""
        mock_source = MagicMock()
        mock_source.connector_type = "media"
        mock_source.config = {
            "platform": "youtube",
            "api_key": "test-key",
            "channel_id": "test-channel",
        }

        connector = get_connector_for_source(mock_source)
        assert isinstance(connector, MediaAPIConnector)
        assert connector.config == mock_source.config

    def test_get_connector_for_source_unknown_type(self):
        """Test get_connector_for_source raises error for unknown type."""
        mock_source = MagicMock()
        mock_source.connector_type = "unknown"
        mock_source.config = {}

        with pytest.raises(ValueError, match="Unknown connector type: unknown"):
            get_connector_for_source(mock_source)


class TestConnectorRegistry:
    """Tests for CONNECTOR_REGISTRY."""

    def test_registry_contains_all_types(self):
        """Test registry contains all expected connector types."""
        expected_types = {"rss", "api", "web", "media"}
        assert set(CONNECTOR_REGISTRY.keys()) == expected_types

    def test_registry_values_are_connector_classes(self):
        """Test all registry values are connector classes."""
        for connector_type, connector_class in CONNECTOR_REGISTRY.items():
            assert issubclass(connector_class, BaseConnector), (
                f"{connector_type} connector class should be a subclass of BaseConnector"
            )