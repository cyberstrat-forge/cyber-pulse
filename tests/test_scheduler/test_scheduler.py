"""Tests for the scheduler service."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from cyberpulse.scheduler.scheduler import SchedulerService, get_scheduler
from cyberpulse.scheduler.jobs import collect_source, run_scheduled_collection, update_source_scores


class TestSchedulerService:
    """Tests for SchedulerService class."""

    def test_init_with_database_url(self):
        """Test initialization with explicit database URL."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler:
            service = SchedulerService(database_url="postgresql://test:test@localhost/testdb")

            assert service.database_url == "postgresql://test:test@localhost/testdb"
            assert service._running is False
            mock_scheduler.assert_called_once()

    def test_init_with_settings_default(self):
        """Test initialization using settings default."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler"):
            with patch("cyberpulse.scheduler.scheduler.settings") as mock_settings:
                mock_settings.database_url = "postgresql://default:default@localhost/default"
                service = SchedulerService()

                assert service.database_url == "postgresql://default:default@localhost/default"

    def test_mask_url(self):
        """Test URL masking for logging."""
        service = SchedulerService.__new__(SchedulerService)
        service.database_url = "test"

        masked = service._mask_url("postgresql://user:password@localhost:5432/db")
        assert masked == "postgresql://user:***@localhost:5432/db"

        # URL without password
        masked = service._mask_url("postgresql://localhost:5432/db")
        assert masked == "postgresql://localhost:5432/db"

    def test_start(self):
        """Test starting the scheduler."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()

            service.start()

            mock_scheduler.start.assert_called_once()
            assert service._running is True

    def test_start_already_running(self):
        """Test starting when already running."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            service._running = True

            service.start()

            mock_scheduler.start.assert_not_called()

    def test_stop(self):
        """Test stopping the scheduler."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            service._running = True

            service.stop(wait=True)

            mock_scheduler.shutdown.assert_called_once_with(wait=True)
            assert service._running is False

    def test_stop_not_running(self):
        """Test stopping when not running."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()

            service.stop()

            mock_scheduler.shutdown.assert_not_called()

    def test_is_running(self):
        """Test is_running check."""
        service = SchedulerService.__new__(SchedulerService)
        service._running = False

        assert service.is_running() is False

        service._running = True
        assert service.is_running() is True

    def test_schedule_source_collection(self):
        """Test scheduling a source collection job."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_job = MagicMock()
            mock_job.id = "collect_source_src_test123"
            mock_scheduler.add_job.return_value = mock_job
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            job_id = service.schedule_source_collection("src_test123", interval=3600)

            assert job_id == "collect_source_src_test123"
            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args
            assert call_kwargs[1]["id"] == "collect_source_src_test123"
            assert call_kwargs[1]["args"] == ["src_test123"]
            assert call_kwargs[1]["max_instances"] == 1

    def test_schedule_source_collection_invalid_interval(self):
        """Test scheduling with invalid interval."""
        service = SchedulerService.__new__(SchedulerService)
        service.scheduler = MagicMock()

        with pytest.raises(ValueError, match="Interval must be at least 60 seconds"):
            service.schedule_source_collection("src_test123", interval=30)

    def test_unschedule_source_collection(self):
        """Test unscheduling a source collection job."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_job = MagicMock()
            mock_scheduler.get_job.return_value = mock_job
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            result = service.unschedule_source_collection("src_test123")

            assert result is True
            mock_scheduler.remove_job.assert_called_once_with("collect_source_src_test123")

    def test_unschedule_source_collection_not_found(self):
        """Test unscheduling a job that doesn't exist."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = None
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            result = service.unschedule_source_collection("src_test123")

            assert result is False
            mock_scheduler.remove_job.assert_not_called()

    def test_get_scheduled_jobs(self):
        """Test getting list of scheduled jobs."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_job1 = MagicMock()
            mock_job1.id = "job1"
            mock_job1.name = "Test Job 1"
            mock_job1.next_run_time = datetime(2026, 3, 19, 12, 0, 0)
            mock_job1.trigger = MagicMock()
            mock_job1.trigger.__str__ = lambda self: "interval[0:01:00]"

            mock_job2 = MagicMock()
            mock_job2.id = "job2"
            mock_job2.name = "Test Job 2"
            mock_job2.next_run_time = datetime(2026, 3, 19, 13, 0, 0)
            mock_job2.trigger = MagicMock()
            mock_job2.trigger.__str__ = lambda self: "interval[1:00:00]"

            mock_scheduler.get_jobs.return_value = [mock_job1, mock_job2]
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            jobs = service.get_scheduled_jobs()

            assert len(jobs) == 2
            assert jobs[0]["id"] == "job1"
            assert jobs[1]["id"] == "job2"

    def test_get_job(self):
        """Test getting a specific job."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_job = MagicMock()
            mock_job.id = "test_job"
            mock_job.name = "Test Job"
            mock_job.next_run_time = datetime(2026, 3, 19, 12, 0, 0)
            mock_job.trigger = MagicMock()
            mock_job.trigger.__str__ = lambda self: "interval[0:01:00]"
            mock_job.args = ["arg1"]
            mock_job.kwargs = {}
            mock_job.max_instances = 1
            mock_job.misfire_grace_time = 300

            mock_scheduler.get_job.return_value = mock_job
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            job = service.get_job("test_job")

            assert job is not None
            assert job["id"] == "test_job"
            assert job["name"] == "Test Job"
            assert job["args"] == ["arg1"]

    def test_get_job_not_found(self):
        """Test getting a job that doesn't exist."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = None
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            job = service.get_job("nonexistent")

            assert job is None

    def test_run_job_now(self):
        """Test triggering a job to run immediately."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_job = MagicMock()
            mock_scheduler.get_job.return_value = mock_job
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            result = service.run_job_now("test_job")

            assert result is True
            mock_job.modify.assert_called_once_with(next_run_time=None)

    def test_run_job_now_not_found(self):
        """Test triggering a job that doesn't exist."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = None
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()
            result = service.run_job_now("nonexistent")

            assert result is False


class TestGetScheduler:
    """Tests for get_scheduler function."""

    def test_get_scheduler_creates_instance(self):
        """Test that get_scheduler creates a new instance."""
        import cyberpulse.scheduler.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None

        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler"):
            scheduler = get_scheduler()

            assert scheduler is not None
            assert isinstance(scheduler, SchedulerService)

    def test_get_scheduler_returns_same_instance(self):
        """Test that get_scheduler returns the same instance."""
        import cyberpulse.scheduler.scheduler as scheduler_module
        scheduler_module._scheduler_instance = None

        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler"):
            scheduler1 = get_scheduler()
            scheduler2 = get_scheduler()

            assert scheduler1 is scheduler2


class TestJobFunctions:
    """Tests for job functions."""

    def test_collect_source(self):
        """Test collect_source job function."""
        with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
            mock_ingest.send = MagicMock()

            result = collect_source("src_test123")

            assert result["source_id"] == "src_test123"
            assert result["status"] == "queued"
            mock_ingest.send.assert_called_once_with("src_test123")

    def test_run_scheduled_collection(self):
        """Test run_scheduled_collection job function."""
        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = []

            result = run_scheduled_collection()

            assert result["status"] == "completed"
            assert result["sources_count"] == 0

    def test_update_source_scores(self):
        """Test update_source_scores job function."""
        with patch("cyberpulse.scheduler.jobs.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = []

            result = update_source_scores()

            assert result["status"] == "completed"
            assert result["sources_updated"] == 0


class TestSchedulerIntegration:
    """Integration tests for scheduler with mocked database."""

    @pytest.mark.asyncio
    async def test_scheduler_lifecycle(self):
        """Test complete scheduler lifecycle."""
        with patch("cyberpulse.scheduler.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            service = SchedulerService()

            # Start
            service.start()
            assert service.is_running() is True

            # Stop
            service.stop()
            assert service.is_running() is False

    def test_job_event_listener_success(self, caplog):
        """Test job event listener logs successful execution."""
        import logging

        service = SchedulerService.__new__(SchedulerService)
        service._running = False
        service.database_url = "test"

        event = MagicMock()
        event.job_id = "test_job"
        event.exception = None

        with caplog.at_level(logging.INFO):
            service._job_executed_listener(event)

        assert "executed successfully" in caplog.text or "test_job" in caplog.text

    def test_job_event_listener_failure(self, caplog):
        """Test job event listener logs failed execution."""
        import logging

        service = SchedulerService.__new__(SchedulerService)
        service._running = False
        service.database_url = "test"

        event = MagicMock()
        event.job_id = "test_job"
        event.exception = Exception("Test error")

        with caplog.at_level(logging.ERROR):
            service._job_executed_listener(event)

        assert "failed" in caplog.text.lower() or "error" in caplog.text.lower()