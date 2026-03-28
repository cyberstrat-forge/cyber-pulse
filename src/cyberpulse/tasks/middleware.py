"""Concurrency limit middleware for dramatiq actors.

This middleware allows setting max_concurrency on actors to limit
the number of concurrent messages being processed for that actor.

Usage:
    broker.add_middleware(ConcurrencyLimitMiddleware())

    @dramatiq.actor(max_retries=2, max_concurrency=3)
    def my_task():
        ...
"""

import logging
import threading
from collections import defaultdict

from dramatiq import Middleware

logger = logging.getLogger(__name__)


class ConcurrencyLimitMiddleware(Middleware):
    """Middleware that limits concurrent message processing per actor.

    This middleware tracks how many messages are currently being processed
    for each actor and defers new messages when the limit is reached.
    """

    def __init__(self):
        self.actor_limits: dict[str, dict] = defaultdict(
            lambda: {"max": None, "current": 0}
        )
        self.lock = threading.Lock()

    @property
    def actor_options(self) -> set[str]:
        """Return the actor options this middleware handles."""
        return {"max_concurrency"}

    def after_declare_actor(self, broker, actor):
        """Store the max_concurrency setting for the actor."""
        max_concurrency = actor.options.get("max_concurrency")
        if max_concurrency is not None:
            with self.lock:
                self.actor_limits[actor.actor_name]["max"] = max_concurrency
            logger.debug(
                f"Actor {actor.actor_name} configured with "
                f"max_concurrency={max_concurrency}"
            )

    def before_process_message(self, broker, message):
        """Check if actor has reached its concurrency limit.

        If limit is reached, the message is deferred.

        Returns:
            True if message should be processed, False if deferred.
        """
        actor_name = message.actor_name
        with self.lock:
            actor_limit = self.actor_limits[actor_name]
            max_concurrency = actor_limit["max"]

            if max_concurrency is None:
                # No limit configured for this actor
                return True

            current = actor_limit["current"]
            if current >= max_concurrency:
                # Limit reached - defer message
                logger.debug(
                    f"Actor {actor_name} at max_concurrency "
                    f"({current}/{max_concurrency}), deferring message"
                )
                broker.defer_message(message)
                return False

            # Increment counter
            actor_limit["current"] += 1
            return True

    def after_process_message(self, broker, message, *, result=None, exception=None):
        """Decrement the concurrent message counter."""
        actor_name = message.actor_name
        with self.lock:
            actor_limit = self.actor_limits[actor_name]
            if actor_limit["max"] is not None and actor_limit["current"] > 0:
                actor_limit["current"] -= 1

    def after_skip_message(self, broker, message):
        """Handle skipped messages (shouldn't increment counter)."""
        # No action needed - counter wasn't incremented for skipped messages
        pass
