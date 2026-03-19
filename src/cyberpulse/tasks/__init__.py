"""Tasks module for cyber-pulse.

This module provides Dramatiq-based async task processing for the system.
Tasks are executed by worker processes and communicate via Redis.

Components:
- worker.py: Broker configuration and dramatiq setup
- (Future) ingestion_tasks.py: Ingestion pipeline tasks
- (Future) processing_tasks.py: Processing pipeline tasks
"""

from .worker import broker, dramatiq, result_backend

__all__ = ["broker", "dramatiq", "result_backend"]