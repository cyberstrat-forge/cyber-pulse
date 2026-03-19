"""Tasks module for cyber-pulse.

This module provides Dramatiq-based async task processing for the system.
Tasks are executed by worker processes and communicate via Redis.

Components:
- worker.py: Broker configuration and dramatiq setup
- ingestion_tasks.py: Source ingestion tasks
- normalization_tasks.py: Content normalization tasks
- quality_tasks.py: Quality check tasks
"""

from .worker import broker, dramatiq, result_backend
from .ingestion_tasks import ingest_source
from .normalization_tasks import normalize_item, normalize_item_with_result
from .quality_tasks import quality_check_item, recheck_item

__all__ = [
    "broker",
    "dramatiq",
    "result_backend",
    "ingest_source",
    "normalize_item",
    "normalize_item_with_result",
    "quality_check_item",
    "recheck_item",
]