"""Scheduler main entry point for standalone execution.

This module provides the entry point for running the scheduler as a
standalone process, typically in a Docker container.

Usage:
    python -m cyberpulse.scheduler.main
"""

import logging
import signal
import sys
import time

from .scheduler import SchedulerService
from .jobs import run_scheduled_collection, update_source_scores

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: SchedulerService | None = None


def signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully.

    Args:
        signum: Signal number.
        frame: Current stack frame.
    """
    logger.info(f"Received signal {signum}, shutting down scheduler...")
    if scheduler:
        scheduler.stop(wait=True)
    sys.exit(0)


def main() -> None:
    """Run the scheduler as a standalone process."""
    global scheduler

    logger.info("Starting cyber-pulse scheduler...")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and start the scheduler
    scheduler = SchedulerService()
    scheduler.start()

    # Schedule default jobs
    # Run collection for all active sources every hour
    scheduler.scheduler.add_job(
        run_scheduled_collection,
        "interval",
        hours=1,
        id="scheduled_collection",
        name="Scheduled Collection",
        replace_existing=True,
    )
    logger.info("Scheduled: collection job (every 1 hour)")

    # Update source scores every 6 hours
    scheduler.scheduler.add_job(
        update_source_scores,
        "interval",
        hours=6,
        id="update_scores",
        name="Update Source Scores",
        replace_existing=True,
    )
    logger.info("Scheduled: score update job (every 6 hours)")

    logger.info("Scheduler started and running. Press Ctrl+C to stop.")

    # Keep the main thread alive
    try:
        while scheduler.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        scheduler.stop(wait=True)


if __name__ == "__main__":
    main()