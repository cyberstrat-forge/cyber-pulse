"""Dramatiq worker configuration for cyber-pulse.

This module configures the Dramatiq broker with Redis for async task processing.
The broker is configured with:
- Redis broker for message queue
- Redis result backend for storing task results
- Results middleware for result tracking

Usage:
    from cyberpulse.tasks.worker import broker, dramatiq

    @dramatiq.actor
    def my_task(arg):
        return process(arg)
"""

import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

from ..config import settings

logger = logging.getLogger(__name__)


def _mask_url(url: str) -> str:
    """Mask sensitive parts of Redis URL for logging.

    Args:
        url: Redis URL to mask.

    Returns:
        URL with password masked.
    """
    if "@" in url:
        # Mask password in redis://user:password@host/db
        parts = url.split("@")
        prefix = parts[0].rsplit(":", 1)[0]
        return f"{prefix}:***@{parts[1]}"
    return url


# Get Redis URL from settings
# Use dramatiq_broker_url (DB 1) for separation from general Redis (DB 0)
redis_url = settings.dramatiq_broker_url

# Configure Redis broker
broker = RedisBroker(url=redis_url)

# Configure result backend for storing task results
result_backend = RedisBackend(url=redis_url)

# Add Results middleware for result tracking
broker.add_middleware(Results(backend=result_backend))

# Set as the default broker for dramatiq
dramatiq.set_broker(broker)

logger.info(f"Dramatiq broker configured with Redis: {_mask_url(redis_url)}")


__all__ = ["broker", "dramatiq", "result_backend"]