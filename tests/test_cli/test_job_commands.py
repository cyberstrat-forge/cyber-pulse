"""Tests for job CLI commands."""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cyberpulse.cli.commands.job import app
from cyberpulse.models import Source

runner = CliRunner()


class TestJobList:
    """Tests for job list command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_empty(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with no jobs."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = []
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No scheduled jobs found" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_with_jobs(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with scheduled jobs."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = [
            {
                "id": "collect_source_src_abc123",
                "name": "Collect from source src_abc123",
                "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
                "trigger": "interval[1:00:00]",
            },
            {
                "id": "collect_source_src_def456",
                "name": "Collect from source src_def456",
                "next_run_time": datetime(2026, 3, 19, 13, 0, 0, tzinfo=timezone.utc),
                "trigger": "interval[2:00:00]",
            },
        ]
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "collect_source_src_abc123" in result.stdout
        assert "collect_source_src_def456" in result.stdout
        assert "Total: 2 job(s)" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_json_output(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with JSON output."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = [
            {
                "id": "collect_source_src_abc123",
                "name": "Collect from source src_abc123",
                "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
                "trigger": "interval[1:00:00]",
            },
        ]
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["id"] == "collect_source_src_abc123"

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_filter_scheduled(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with scheduled filter."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = [
            {
                "id": "job1",
                "name": "Job 1",
                "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
                "trigger": "interval[1:00:00]",
            },
            {
                "id": "job2",
                "name": "Job 2",
                "next_run_time": None,  # Paused
                "trigger": "interval[1:00:00]",
            },
        ]
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list", "--status", "scheduled"])
        assert result.exit_code == 0
        assert "job1" in result.stdout
        assert "job2" not in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_filter_paused(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with paused filter."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = [
            {
                "id": "job1",
                "name": "Job 1",
                "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
                "trigger": "interval[1:00:00]",
            },
            {
                "id": "job2",
                "name": "Job 2",
                "next_run_time": None,  # Paused
                "trigger": "interval[1:00:00]",
            },
        ]
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list", "--status", "paused"])
        assert result.exit_code == 0
        assert "job1" not in result.stdout
        assert "job2" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_invalid_status(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command with invalid status filter."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_scheduled_jobs.return_value = []
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["list", "--status", "invalid"])
        assert result.exit_code == 1
        assert "Invalid status filter" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_list_error(self, mock_get_scheduler: MagicMock) -> None:
        """Test list command handles errors gracefully."""
        mock_get_scheduler.side_effect = Exception("Database error")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Error listing jobs" in result.stdout


class TestJobRun:
    """Tests for job run command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_run_source_not_found(self, mock_get_scheduler: MagicMock) -> None:
        """Test run command with non-existent source."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_local.return_value = mock_db

            result = runner.invoke(app, ["run", "src_nonexistent"])
            assert result.exit_code == 1
            assert "Source not found" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_run_with_scheduled_job(self, mock_get_scheduler: MagicMock) -> None:
        """Test run command triggers scheduled job."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            # Setup mock source
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            # Setup mock scheduler
            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = {
                "id": "collect_source_src_abc123",
                "name": "Collect from source src_abc123",
            }
            mock_scheduler.run_job_now.return_value = True
            mock_get_scheduler.return_value = mock_scheduler

            result = runner.invoke(app, ["run", "src_abc123"])
            assert result.exit_code == 0
            assert "Triggered scheduled job" in result.stdout
            mock_scheduler.run_job_now.assert_called_once_with("collect_source_src_abc123")

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_run_without_scheduled_job(self, mock_get_scheduler: MagicMock) -> None:
        """Test run command queues task when no scheduled job."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            # Setup mock source
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            # Setup mock scheduler with no scheduled job
            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = None
            mock_get_scheduler.return_value = mock_scheduler

            # Setup mock Dramatiq actor
            with patch("cyberpulse.tasks.ingestion_tasks.ingest_source") as mock_ingest_source:
                mock_send = MagicMock()
                mock_ingest_source.send = mock_send

                result = runner.invoke(app, ["run", "src_abc123"])
                assert result.exit_code == 0
                assert "Queued ingestion task" in result.stdout
                mock_send.assert_called_once_with("src_abc123")

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_run_with_wait(self, mock_get_scheduler: MagicMock) -> None:
        """Test run command with --wait flag."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            mock_scheduler = MagicMock()
            mock_scheduler.get_job.return_value = None
            mock_get_scheduler.return_value = mock_scheduler

            with patch("cyberpulse.tasks.ingestion_tasks.ingest_source"):
                result = runner.invoke(app, ["run", "src_abc123", "--wait"])

            assert result.exit_code == 0
            assert "not yet implemented" in result.stdout


class TestJobCancel:
    """Tests for job cancel command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_cancel_success(self, mock_get_scheduler: MagicMock) -> None:
        """Test cancel command removes job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = {
            "id": "collect_source_src_abc123",
            "name": "Collect from source src_abc123",
        }
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["cancel", "collect_source_src_abc123"])
        assert result.exit_code == 0
        assert "Cancelled job" in result.stdout
        mock_scheduler.scheduler.remove_job.assert_called_once_with("collect_source_src_abc123")

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_cancel_not_found(self, mock_get_scheduler: MagicMock) -> None:
        """Test cancel command with non-existent job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["cancel", "nonexistent_job"])
        assert result.exit_code == 1
        assert "Job not found" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_cancel_with_force(self, mock_get_scheduler: MagicMock) -> None:
        """Test cancel command with --force flag."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = {
            "id": "collect_source_src_abc123",
            "name": "Collect from source src_abc123",
        }
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["cancel", "collect_source_src_abc123", "--force"])
        assert result.exit_code == 0
        assert "Cancelled job" in result.stdout


class TestJobStatus:
    """Tests for job status command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_status_success(self, mock_get_scheduler: MagicMock) -> None:
        """Test status command shows job details."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = {
            "id": "collect_source_src_abc123",
            "name": "Collect from source src_abc123",
            "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
            "trigger": "interval[1:00:00]",
            "args": ["src_abc123"],
            "kwargs": {},
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["status", "collect_source_src_abc123"])
        assert result.exit_code == 0
        assert "collect_source_src_abc123" in result.stdout
        assert "Collect from source src_abc123" in result.stdout
        assert "Status: Scheduled" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_status_paused(self, mock_get_scheduler: MagicMock) -> None:
        """Test status command shows paused job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = {
            "id": "collect_source_src_abc123",
            "name": "Collect from source src_abc123",
            "next_run_time": None,  # Paused
            "trigger": "interval[1:00:00]",
            "args": ["src_abc123"],
            "kwargs": {},
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["status", "collect_source_src_abc123"])
        assert result.exit_code == 0
        assert "Status: Paused" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_status_not_found(self, mock_get_scheduler: MagicMock) -> None:
        """Test status command with non-existent job."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["status", "nonexistent_job"])
        assert result.exit_code == 1
        assert "Job not found" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_status_json_output(self, mock_get_scheduler: MagicMock) -> None:
        """Test status command with JSON output."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = {
            "id": "collect_source_src_abc123",
            "name": "Collect from source src_abc123",
            "next_run_time": datetime(2026, 3, 19, 12, 0, 0, tzinfo=timezone.utc),
            "trigger": "interval[1:00:00]",
            "args": ["src_abc123"],
            "kwargs": {},
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["status", "collect_source_src_abc123", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "collect_source_src_abc123"


class TestJobSchedule:
    """Tests for job schedule command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_schedule_success(self, mock_get_scheduler: MagicMock) -> None:
        """Test schedule command creates scheduled job."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            mock_scheduler = MagicMock()
            mock_scheduler.schedule_source_collection.return_value = "collect_source_src_abc123"
            mock_get_scheduler.return_value = mock_scheduler

            result = runner.invoke(app, ["schedule", "src_abc123"])
            assert result.exit_code == 0
            assert "Scheduled collection for source" in result.stdout
            assert "3600 seconds" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_schedule_custom_interval(self, mock_get_scheduler: MagicMock) -> None:
        """Test schedule command with custom interval."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            mock_scheduler = MagicMock()
            mock_scheduler.schedule_source_collection.return_value = "collect_source_src_abc123"
            mock_get_scheduler.return_value = mock_scheduler

            result = runner.invoke(app, ["schedule", "src_abc123", "--interval", "1800"])
            assert result.exit_code == 0
            assert "1800 seconds" in result.stdout
            mock_scheduler.schedule_source_collection.assert_called_once_with(
                "src_abc123", interval=1800
            )

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_schedule_source_not_found(self, mock_get_scheduler: MagicMock) -> None:
        """Test schedule command with non-existent source."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_local.return_value = mock_db

            result = runner.invoke(app, ["schedule", "src_nonexistent"])
            assert result.exit_code == 1
            assert "Source not found" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_schedule_invalid_interval(self, mock_get_scheduler: MagicMock) -> None:
        """Test schedule command with interval too small."""
        with patch("cyberpulse.database.SessionLocal") as mock_session_local:
            mock_source = MagicMock(spec=Source)
            mock_source.source_id = "src_abc123"
            mock_source.name = "Test Source"

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = mock_source
            mock_session_local.return_value = mock_db

            result = runner.invoke(app, ["schedule", "src_abc123", "--interval", "30"])
            assert result.exit_code == 1
            assert "Interval must be at least 60 seconds" in result.stdout


class TestJobUnschedule:
    """Tests for job unschedule command."""

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_unschedule_success(self, mock_get_scheduler: MagicMock) -> None:
        """Test unschedule command removes scheduled collection."""
        mock_scheduler = MagicMock()
        mock_scheduler.unschedule_source_collection.return_value = True
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["unschedule", "src_abc123"])
        assert result.exit_code == 0
        assert "Unscheduled collection for source" in result.stdout

    @patch("cyberpulse.cli.commands.job._get_scheduler")
    def test_job_unschedule_not_found(self, mock_get_scheduler: MagicMock) -> None:
        """Test unschedule command when no scheduled collection exists."""
        mock_scheduler = MagicMock()
        mock_scheduler.unschedule_source_collection.return_value = False
        mock_get_scheduler.return_value = mock_scheduler

        result = runner.invoke(app, ["unschedule", "src_abc123"])
        assert result.exit_code == 0
        assert "No scheduled collection found" in result.stdout


class TestJobHelp:
    """Tests for job command help."""

    def test_job_help(self) -> None:
        """Test job command shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Manage collection jobs" in result.stdout
        assert "list" in result.stdout
        assert "run" in result.stdout
        assert "cancel" in result.stdout
        assert "status" in result.stdout
        assert "schedule" in result.stdout
        assert "unschedule" in result.stdout

    def test_job_list_help(self) -> None:
        """Test job list command help."""
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List all scheduled jobs" in result.stdout

    def test_job_run_help(self) -> None:
        """Test job run command help."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "Run a collection job immediately" in result.stdout

    def test_job_cancel_help(self) -> None:
        """Test job cancel command help."""
        result = runner.invoke(app, ["cancel", "--help"])
        assert result.exit_code == 0
        assert "Cancel a scheduled job" in result.stdout

    def test_job_status_help(self) -> None:
        """Test job status command help."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "Get details of a specific job" in result.stdout