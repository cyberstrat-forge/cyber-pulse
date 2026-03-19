"""Connector factory for creating connector instances."""

from typing import TYPE_CHECKING, Any, Dict, Type

from .connector_service import BaseConnector
from .rss_connector import RSSConnector
from .api_connector import APIConnector
from .web_connector import WebScraperConnector
from .media_connector import MediaAPIConnector

if TYPE_CHECKING:
    from ..models.source import Source


# Connector type registry
# Note: RSSConnector is already implemented from Phase 1
CONNECTOR_REGISTRY: Dict[str, Type[BaseConnector]] = {
    "rss": RSSConnector,
    "api": APIConnector,
    "web": WebScraperConnector,
    "media": MediaAPIConnector,
}


def get_connector(connector_type: str, config: Dict[str, Any]) -> BaseConnector:
    """Get appropriate connector instance for a source.

    Args:
        connector_type: Type string (rss, api, web, media)
        config: Connector configuration dict

    Returns:
        Connector instance

    Raises:
        ValueError: If connector_type is unknown
    """
    connector_class = CONNECTOR_REGISTRY.get(connector_type)
    if not connector_class:
        raise ValueError(
            f"Unknown connector type: {connector_type}. "
            f"Available types: {list(CONNECTOR_REGISTRY.keys())}"
        )
    return connector_class(config)


def get_connector_for_source(source: "Source") -> BaseConnector:
    """Get connector instance for a Source model.

    Args:
        source: Source model instance

    Returns:
        Connector instance configured from source.config
    """
    # SQLAlchemy Column attributes are typed as Column[T] at class level
    # but resolve to T at instance level
    return get_connector(source.connector_type, source.config)  # type: ignore[arg-type]