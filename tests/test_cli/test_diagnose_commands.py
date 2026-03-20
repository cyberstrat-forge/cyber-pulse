"""Tests for diagnose command module."""
import tempfile
import os
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from cyberpulse.cli.commands.diagnose import (
    app, parse_time_delta, format_size
)

runner = CliRunner()


class TestDiagnoseSystem:
    """Tests for diagnose system command."""

    def test_diagnose_system_healthy(self) -> None:
        """Test system diagnosis when all systems healthy."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            # Mock database
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://user:pass@localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True

            # Mock redis - it's imported inside the function
            mock_redis = MagicMock()
            mock_redis.ping.return_value = None

            with patch.dict('sys.modules', {'redis': MagicMock(from_url=MagicMock(return_value=mock_redis))}):
                result = runner.invoke(app, ['system'])
                assert result.exit_code == 0
                assert 'Database connection: healthy' in result.stdout

    def test_diagnose_system_database_unhealthy(self) -> None:
        """Test system diagnosis when database is unhealthy."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            # Mock database failure
            mock_db.side_effect = Exception('Connection refused')
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True

            result = runner.invoke(app, ['system'])
            assert result.exit_code == 1
            assert 'unhealthy' in result.stdout

    def test_diagnose_system_redis_unhealthy(self) -> None:
        """Test system diagnosis when Redis is unhealthy."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            # Mock database
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True

            # Mock redis failure
            mock_redis = MagicMock()
            mock_redis.ping.side_effect = Exception('Connection refused')
            mock_redis_module = MagicMock()
            mock_redis_module.from_url.return_value = mock_redis

            with patch.dict('sys.modules', {'redis': mock_redis_module}):
                result = runner.invoke(app, ['system'])
                assert result.exit_code == 1
                assert 'unhealthy' in result.stdout

    def test_diagnose_system_with_log_file(self) -> None:
        """Test system diagnosis with log file existing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('test log content\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
                 patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
                # Mock database
                mock_session = MagicMock()
                mock_session.execute.return_value = None
                mock_db.return_value = mock_session
                mock_settings.database_url = 'postgresql://localhost/db'
                mock_settings.redis_url = 'redis://localhost:6379/0'
                mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
                mock_settings.log_level = 'INFO'
                mock_settings.log_file = temp_path
                mock_settings.scheduler_enabled = True

                mock_redis = MagicMock()
                mock_redis.ping.return_value = None
                mock_redis_module = MagicMock()
                mock_redis_module.from_url.return_value = mock_redis

                with patch.dict('sys.modules', {'redis': mock_redis_module}):
                    result = runner.invoke(app, ['system'])
                    assert result.exit_code == 0
                    assert 'Log file size' in result.stdout
        finally:
            os.unlink(temp_path)


class TestDiagnoseSources:
    """Tests for diagnose sources command."""

    def test_diagnose_sources_no_sources(self) -> None:
        """Test sources diagnosis when no sources exist."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = []
            mock_query.filter.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session

            result = runner.invoke(app, ['sources'])
            assert result.exit_code == 0
            assert 'No sources found' in result.stdout

    def test_diagnose_sources_with_sources(self) -> None:
        """Test sources diagnosis with existing sources."""
        from datetime import datetime, timezone
        from cyberpulse.models import Source, SourceTier, SourceStatus

        mock_source = MagicMock(spec=Source)
        mock_source.source_id = 'src_abc123'
        mock_source.name = 'Test Source'
        mock_source.tier = SourceTier.T1
        mock_source.score = 70.0
        mock_source.status = SourceStatus.ACTIVE
        mock_source.is_in_observation = False
        mock_source.observation_until = None
        mock_source.pending_review = False
        mock_source.review_reason = None
        mock_source.last_fetched_at = datetime.now(timezone.utc)
        mock_source.total_items = 100

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_source]
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 1
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session

            result = runner.invoke(app, ['sources'])
            assert result.exit_code == 0
            assert 'Total sources: 1' in result.stdout
            assert 'Active: 1' in result.stdout

    def test_diagnose_sources_pending_only(self) -> None:
        """Test sources diagnosis with --pending flag."""
        from cyberpulse.models import Source, SourceTier, SourceStatus

        mock_source = MagicMock(spec=Source)
        mock_source.source_id = 'src_abc123'
        mock_source.name = 'Pending Source'
        mock_source.tier = SourceTier.T2
        mock_source.score = 50.0
        mock_source.status = SourceStatus.ACTIVE
        mock_source.is_in_observation = False
        mock_source.observation_until = None
        mock_source.pending_review = True
        mock_source.review_reason = 'Quality issues'
        mock_source.last_fetched_at = None
        mock_source.total_items = 10

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_source]
            mock_query.filter.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session

            result = runner.invoke(app, ['sources', '--pending'])
            assert result.exit_code == 0
            assert 'pending review' in result.stdout.lower()

    def test_diagnose_sources_invalid_tier(self) -> None:
        """Test sources diagnosis with invalid tier."""
        result = runner.invoke(app, ['sources', '--tier', 'T9'])
        assert result.exit_code == 1
        assert 'Invalid tier' in result.stdout

    def test_diagnose_sources_filter_by_tier(self) -> None:
        """Test sources diagnosis with tier filter."""
        from datetime import datetime, timezone
        from cyberpulse.models import Source, SourceTier, SourceStatus

        mock_source = MagicMock(spec=Source)
        mock_source.source_id = 'src_abc123'
        mock_source.name = 'T0 Source'
        mock_source.tier = SourceTier.T0
        mock_source.score = 90.0
        mock_source.status = SourceStatus.ACTIVE
        mock_source.is_in_observation = False
        mock_source.observation_until = None
        mock_source.pending_review = False
        mock_source.review_reason = None
        mock_source.last_fetched_at = datetime.now(timezone.utc)
        mock_source.total_items = 500

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_source]
            mock_query.filter.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session

            result = runner.invoke(app, ['sources', '--tier', 'T0'])
            assert result.exit_code == 0


class TestDiagnoseErrors:
    """Tests for diagnose errors command."""

    def test_diagnose_errors_no_rejected_items(self) -> None:
        """Test errors diagnosis with no rejected items."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = []
            mock_query.count.return_value = 0
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            assert 'No rejected items found' in result.stdout

    def test_diagnose_errors_with_rejected_items(self) -> None:
        """Test errors diagnosis with rejected items."""
        from datetime import datetime, timezone
        from cyberpulse.models import Item

        mock_item = MagicMock(spec=Item)
        mock_item.item_id = 'item_abc123'
        mock_item.source_id = 'src_xyz'
        mock_item.title = 'Test Item Title'
        mock_item.fetched_at = datetime.now(timezone.utc)
        mock_item.raw_metadata = None

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_item]
            mock_query.count.return_value = 1
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            assert 'Found 1 rejected items' in result.stdout

    def test_diagnose_errors_invalid_since(self) -> None:
        """Test errors diagnosis with invalid since parameter."""
        result = runner.invoke(app, ['errors', '--since', 'invalid'])
        assert result.exit_code == 1
        assert 'Invalid time format' in result.stdout

    def test_diagnose_errors_filter_by_source(self) -> None:
        """Test errors diagnosis with source filter."""
        from datetime import datetime, timezone
        from cyberpulse.models import Item

        mock_item = MagicMock(spec=Item)
        mock_item.item_id = 'item_abc123'
        mock_item.source_id = 'src_target'
        mock_item.title = 'Test Item'
        mock_item.fetched_at = datetime.now(timezone.utc)
        mock_item.raw_metadata = None

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_item]
            mock_query.count.return_value = 1
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors', '--source', 'src_target'])
            assert result.exit_code == 0

    def test_diagnose_errors_with_log_file(self) -> None:
        """Test errors diagnosis reads log file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - ERROR - Test error message\n')
            f.write('2024-01-15 10:31:00,456 - test - INFO - Info message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
                 patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
                mock_session = MagicMock()
                mock_query = MagicMock()
                mock_query.all.return_value = []
                mock_query.count.return_value = 0
                mock_query.filter.return_value = mock_query
                mock_query.order_by.return_value = mock_query
                mock_query.limit.return_value = mock_query
                mock_session.query.return_value = mock_query
                mock_db.return_value = mock_session
                mock_settings.log_file = temp_path

                result = runner.invoke(app, ['errors'])
                assert result.exit_code == 0
                assert 'Found 1 error entries' in result.stdout
                assert 'ERROR' in result.stdout
        finally:
            os.unlink(temp_path)


class TestParseTimeDelta:
    """Tests for parse_time_delta function."""

    def test_parse_minutes(self) -> None:
        """Test parsing minutes."""
        from datetime import datetime, timedelta
        result = parse_time_delta('30m')
        assert result is not None
        expected = datetime.now() - timedelta(minutes=30)
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_hours(self) -> None:
        """Test parsing hours."""
        from datetime import datetime, timedelta
        result = parse_time_delta('24h')
        assert result is not None
        expected = datetime.now() - timedelta(hours=24)
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_invalid(self) -> None:
        """Test parsing invalid format."""
        result = parse_time_delta('invalid')
        assert result is None


class TestFormatSize:
    """Tests for format_size function."""

    def test_format_bytes(self) -> None:
        """Test formatting bytes."""
        assert 'B' in format_size(500)

    def test_format_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        result = format_size(2048)
        assert 'KB' in result

    def test_format_megabytes(self) -> None:
        """Test formatting megabytes."""
        result = format_size(2 * 1024 * 1024)
        assert 'MB' in result


class TestDiagnoseHelp:
    """Tests for diagnose command help."""

    def test_diagnose_help(self) -> None:
        """Test diagnose command help output."""
        result = runner.invoke(app, ['--help'])
        assert result.exit_code == 0
        assert 'system' in result.stdout
        assert 'sources' in result.stdout
        assert 'errors' in result.stdout

    def test_system_help(self) -> None:
        """Test system command help."""
        result = runner.invoke(app, ['system', '--help'])
        assert result.exit_code == 0
        assert 'health' in result.stdout.lower()

    def test_sources_help(self) -> None:
        """Test sources command help."""
        result = runner.invoke(app, ['sources', '--help'])
        assert result.exit_code == 0
        assert '--pending' in result.stdout
        assert '--tier' in result.stdout

    def test_errors_help(self) -> None:
        """Test errors command help."""
        result = runner.invoke(app, ['errors', '--help'])
        assert result.exit_code == 0
        assert '--since' in result.stdout
        assert '--source' in result.stdout


class TestDiagnoseErrorsWithReason:
    """Tests for diagnose errors with rejection reason."""

    def test_diagnose_errors_shows_rejection_reason(self) -> None:
        """Test errors diagnosis shows rejection reason from raw_metadata."""
        from datetime import datetime, timezone
        from cyberpulse.models import Item

        mock_item = MagicMock(spec=Item)
        mock_item.item_id = 'item_abc123'
        mock_item.source_id = 'src_xyz'
        mock_item.title = 'Test Item Title'
        mock_item.fetched_at = datetime.now(timezone.utc)
        mock_item.raw_metadata = {
            'rejection_reason': 'Title too short; Empty body',
            'quality_warnings': ['Missing author']
        }

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_item]
            mock_query.count.return_value = 1
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            assert 'Title too short' in result.stdout
            assert 'Empty body' in result.stdout

    def test_diagnose_errors_shows_dash_when_no_reason(self) -> None:
        """Test errors diagnosis shows dash when no rejection reason."""
        from datetime import datetime, timezone
        from cyberpulse.models import Item

        mock_item = MagicMock(spec=Item)
        mock_item.item_id = 'item_abc123'
        mock_item.source_id = 'src_xyz'
        mock_item.title = 'Test Item Title'
        mock_item.fetched_at = datetime.now(timezone.utc)
        mock_item.raw_metadata = None

        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [mock_item]
            mock_query.count.return_value = 1
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_session.query.return_value = mock_query
            mock_db.return_value = mock_session
            mock_settings.log_file = None

            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            # Should show dash when no rejection reason
            assert '-' in result.stdout


class TestDiagnoseSystemServices:
    """Tests for diagnose system service status checks."""

    def test_diagnose_system_shows_api_status(self) -> None:
        """Test system diagnosis shows API service status."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True
            mock_settings.api_host = '0.0.0.0'
            mock_settings.api_port = 8000

            mock_redis = MagicMock()
            mock_redis.ping.return_value = None
            mock_redis.llen.return_value = 0

            mock_redis_module = MagicMock()
            mock_redis_module.from_url.return_value = mock_redis

            with patch.dict('sys.modules', {'redis': mock_redis_module}), \
                 patch('urllib.request.urlopen') as mock_urlopen:
                mock_urlopen.return_value.__enter__ = MagicMock()
                mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value.read.return_value = b'{"status":"healthy"}'

                result = runner.invoke(app, ['system'])
                assert result.exit_code == 0
                assert 'API' in result.stdout

    def test_diagnose_system_shows_queue_status(self) -> None:
        """Test system diagnosis shows task queue status."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True
            mock_settings.api_host = '127.0.0.1'
            mock_settings.api_port = 8000

            mock_redis = MagicMock()
            mock_redis.ping.return_value = None
            mock_redis.llen.return_value = 5

            mock_redis_module = MagicMock()
            mock_redis_module.from_url.return_value = mock_redis

            with patch.dict('sys.modules', {'redis': mock_redis_module}), \
                 patch('urllib.request.urlopen') as mock_urlopen:
                # Make API check fail gracefully
                mock_urlopen.side_effect = Exception('Connection refused')

                result = runner.invoke(app, ['system'])
                assert result.exit_code == 0
                assert 'Queue' in result.stdout or 'Task' in result.stdout

    def test_diagnose_system_api_not_reachable(self) -> None:
        """Test system diagnosis handles API not reachable gracefully."""
        with patch('cyberpulse.cli.commands.diagnose.SessionLocal') as mock_db, \
             patch('cyberpulse.cli.commands.diagnose.settings') as mock_settings:
            mock_session = MagicMock()
            mock_session.execute.return_value = None
            mock_db.return_value = mock_session
            mock_settings.database_url = 'postgresql://localhost/db'
            mock_settings.redis_url = 'redis://localhost:6379/0'
            mock_settings.dramatiq_broker_url = 'redis://localhost:6379/1'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None
            mock_settings.scheduler_enabled = True
            mock_settings.api_host = '127.0.0.1'
            mock_settings.api_port = 8000

            mock_redis = MagicMock()
            mock_redis.ping.return_value = None
            mock_redis.llen.return_value = 0

            mock_redis_module = MagicMock()
            mock_redis_module.from_url.return_value = mock_redis

            with patch.dict('sys.modules', {'redis': mock_redis_module}), \
                 patch('urllib.request.urlopen') as mock_urlopen:
                import urllib.error
                mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

                result = runner.invoke(app, ['system'])
                # Should still succeed - API not reachable is a warning, not an error
                assert result.exit_code == 0
                assert 'API' in result.stdout
                assert 'not reachable' in result.stdout or 'unavailable' in result.stdout.lower()