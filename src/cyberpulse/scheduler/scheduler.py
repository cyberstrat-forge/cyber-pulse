"""APScheduler service for periodic job scheduling.

This module provides the SchedulerService class for managing scheduled jobs
using APScheduler with PostgreSQL as the job store for persistence.
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobEvent

from ..config import settings

logger = logging.getLogger(__name__)


class SchedulerService:
    """APScheduler service for managing periodic jobs.

    This service manages the lifecycle of the APScheduler scheduler,
    providing methods to start/stop the scheduler and schedule jobs
    for source collection.

    Jobs are persisted in PostgreSQL for recovery after restarts.

    Attributes:
        scheduler: The APScheduler AsyncIOScheduler instance.
        database_url: The database URL for the job store.
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the scheduler service.

        Args:
            database_url: Database URL for job store. If not provided,
                uses settings.database_url.
        """
        self.database_url = database_url or settings.database_url

        # Configure job store with PostgreSQL
        jobstores = {
            "default": SQLAlchemyJobStore(url=self.database_url)
        }

        self.scheduler = AsyncIOScheduler(jobstores=jobstores)

        # Track running state
        self._running = False

        # Register event listeners for job execution monitoring
        self.scheduler.add_listener(
            self._job_executed_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        logger.info(f"SchedulerService initialized with database: {self._mask_url(self.database_url)}")

    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of database URL for logging.

        Args:
            url: Database URL to mask.

        Returns:
            URL with password masked.
        """
        if "@" in url:
            # Mask password in postgresql://user:password@host/db
            parts = url.split("@")
            prefix = parts[0].rsplit(":", 1)[0]
            return f"{prefix}:***@{parts[1]}"
        return url

    def _job_executed_listener(self, event: JobEvent) -> None:
        """Listen for job execution events.

        Args:
            event: The job execution event.
        """
        # JobEvent.exception is only present for error events
        exception = getattr(event, "exception", None)
        if exception:
            logger.error(
                f"Job {event.job_id} failed with exception: {exception}"
            )
        else:
            logger.info(f"Job {event.job_id} executed successfully")

    def start(self) -> None:
        """Start the scheduler.

        This starts the scheduler's internal event loop and begins
        processing scheduled jobs. Jobs persisted in the database
        will be automatically loaded.
        """
        if self._running:
            logger.warning("Scheduler is already running")
            return

        self.scheduler.start()
        self._running = True
        logger.info("Scheduler started")

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler.

        Args:
            wait: If True, wait for running jobs to complete.
                If False, shutdown immediately.
        """
        if not self._running:
            logger.warning("Scheduler is not running")
            return

        self.scheduler.shutdown(wait=wait)
        self._running = False
        logger.info(f"Scheduler stopped (wait={wait})")

    def is_running(self) -> bool:
        """Check if the scheduler is running.

        Returns:
            True if the scheduler is running, False otherwise.
        """
        return self._running

    def schedule_source_collection(
        self,
        source_id: str,
        interval: int = 3600,
        replace: bool = True,
    ) -> str:
        """Schedule periodic collection for a source.

        Args:
            source_id: The ID of the source to schedule collection for.
            interval: Collection interval in seconds. Defaults to 3600 (1 hour).
            replace: If True, replace existing job with same ID.
                If False, raise exception if job exists.

        Returns:
            The job ID for the scheduled job.

        Raises:
            ValueError: If interval is less than 60 seconds.
        """
        if interval < 60:
            raise ValueError("Interval must be at least 60 seconds")

        from .jobs import collect_source

        job_id = f"collect_source_{source_id}"

        trigger = IntervalTrigger(seconds=interval)

        job = self.scheduler.add_job(
            collect_source,
            trigger=trigger,
            id=job_id,
            args=[source_id],
            name=f"Collect from source {source_id}",
            replace_existing=replace,
            max_instances=1,  # Prevent concurrent runs for same source
            coalesce=True,  # Combine missed runs into one
            misfire_grace_time=300,  # 5 minutes grace period for missed runs
        )

        logger.info(
            f"Scheduled collection for source {source_id} "
            f"(interval={interval}s, job_id={job_id})"
        )

        return job.id

    def unschedule_source_collection(self, source_id: str) -> bool:
        """Remove scheduled collection for a source.

        Args:
            source_id: The ID of the source to unschedule.

        Returns:
            True if job was removed, False if job didn't exist.
        """
        job_id = f"collect_source_{source_id}"
        job = self.scheduler.get_job(job_id)

        if job:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled collection for source {source_id}")
            return True

        logger.warning(f"No scheduled collection found for source {source_id}")
        return False

    def get_scheduled_jobs(self) -> list:
        """Get list of all scheduled jobs.

        Returns:
            List of job dictionaries with id, name, next_run_time, and trigger info.
        """
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get details of a specific job.

        Args:
            job_id: The ID of the job to get.

        Returns:
            Job details dictionary or None if job doesn't exist.
        """
        job = self.scheduler.get_job(job_id)
        if job:
            return {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
                "args": job.args,
                "kwargs": job.kwargs,
                "max_instances": job.max_instances,
                "misfire_grace_time": job.misfire_grace_time,
            }
        return None

    def run_job_now(self, job_id: str) -> bool:
        """Trigger a job to run immediately.

        Args:
            job_id: The ID of the job to run.

        Returns:
            True if job was triggered, False if job doesn't exist.
        """
        job = self.scheduler.get_job(job_id)
        if job:
            job.modify(next_run_time=None)  # Run immediately
            logger.info(f"Triggered immediate execution of job {job_id}")
            return True

        logger.warning(f"Job {job_id} not found")
        return False

    def schedule_all_active_sources(self) -> int:
        """Schedule collection for all active sources.

        This is a convenience method to schedule collection for multiple
        sources at once. It queries the database for active sources and
        schedules each one.

        Returns:
            Number of sources scheduled.

        Note:
            This method requires a database session. For proper integration,
            it should be called from a context that has database access.
        """
        # This will be properly implemented when integrated with the database
        # For now, return 0 as we don't want to create database dependencies here
        logger.warning(
            "schedule_all_active_sources is a placeholder. "
            "Use schedule_source_collection for individual sources."
        )
        return 0


# Module-level scheduler instance for convenience
_scheduler_instance: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """Get or create the global scheduler instance.

    Returns:
        The global SchedulerService instance.
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SchedulerService()
    return _scheduler_instance