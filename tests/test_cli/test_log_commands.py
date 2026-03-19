"""Tests for log command module."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cyberpulse.cli.commands.log import app, parse_time_delta, format_file_size

runner = CliRunner()


class TestTailLogs:
    """Tests for log tail command."""

    def test_log_tail_missing_file(self) -> None:
        """Test tail command when log file doesn't exist."""
        with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
            mock_path.return_value = Path('/nonexistent/path.log')
            result = runner.invoke(app, ['tail'])
            assert result.exit_code == 0
            assert 'Log file not found' in result.stdout

    def test_log_tail_empty_file(self) -> None:
        """Test tail command with empty log file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['tail'])
                assert result.exit_code == 0
                assert 'No log entries found' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_tail_with_entries(self) -> None:
        """Test tail command with log entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - cyberpulse.test - INFO - Test message\n')
            f.write('2024-01-15 10:31:00,456 - cyberpulse.test - ERROR - Error message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['tail'])
                assert result.exit_code == 0
                assert 'INFO' in result.stdout
                assert 'ERROR' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_tail_with_line_count(self) -> None:
        """Test tail command with custom line count."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            for i in range(10):
                f.write(f'2024-01-15 10:30:{i:02d},123 - test - INFO - Message {i}\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['tail', '-n', '5'])
                assert result.exit_code == 0
        finally:
            os.unlink(temp_path)


class TestErrorLogs:
    """Tests for log errors command."""

    def test_log_errors_missing_file(self) -> None:
        """Test errors command when log file doesn't exist."""
        with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
            mock_path.return_value = Path('/nonexistent/path.log')
            result = runner.invoke(app, ['errors'])
            assert result.exit_code == 0
            assert 'Log file not found' in result.stdout

    def test_log_errors_no_errors(self) -> None:
        """Test errors command when no errors in log."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Info message\n')
            f.write('2024-01-15 10:31:00,456 - test - WARNING - Warning message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['errors'])
                assert result.exit_code == 0
                assert 'No error logs found' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_errors_with_errors(self) -> None:
        """Test errors command with error entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Info message\n')
            f.write('2024-01-15 10:31:00,456 - test - ERROR - Error message\n')
            f.write('2024-01-15 10:32:00,789 - test - CRITICAL - Critical message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['errors'])
                assert result.exit_code == 0
                assert 'ERROR' in result.stdout
                assert 'CRITICAL' in result.stdout
                assert 'Error message' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_errors_invalid_since(self) -> None:
        """Test errors command with invalid since parameter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - ERROR - Error message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['errors', '--since', 'invalid'])
                assert result.exit_code == 1
                assert 'Invalid time format' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_errors_filter_by_source(self) -> None:
        """Test errors command with source filter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - cyberpulse.tasks - ERROR - Task error\n')
            f.write('2024-01-15 10:31:00,456 - cyberpulse.api - ERROR - API error\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['errors', '--source', 'tasks'])
                assert result.exit_code == 0
                assert 'Task error' in result.stdout
                assert 'API error' not in result.stdout
        finally:
            os.unlink(temp_path)


class TestSearchLogs:
    """Tests for log search command."""

    def test_log_search_missing_file(self) -> None:
        """Test search command when log file doesn't exist."""
        with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
            mock_path.return_value = Path('/nonexistent/path.log')
            result = runner.invoke(app, ['search', 'test'])
            assert result.exit_code == 0
            assert 'Log file not found' in result.stdout

    def test_log_search_no_matches(self) -> None:
        """Test search command with no matches."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Some message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['search', 'nonexistent'])
                assert result.exit_code == 0
                assert 'No matches found' in result.stdout
        finally:
            os.unlink(temp_path)

    def test_log_search_with_matches(self) -> None:
        """Test search command with matches."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Connection established\n')
            f.write('2024-01-15 10:31:00,456 - test - ERROR - Connection failed\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['search', 'connection'])
                assert result.exit_code == 0
                assert 'Found' in result.stdout
                assert 'connection' in result.stdout.lower()
        finally:
            os.unlink(temp_path)

    def test_log_search_filter_by_level(self) -> None:
        """Test search command with level filter."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - test - INFO - Connection established\n')
            f.write('2024-01-15 10:31:00,456 - test - ERROR - Connection failed\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['search', 'connection', '--level', 'ERROR'])
                assert result.exit_code == 0
                assert 'ERROR' in result.stdout
                assert 'INFO' not in result.stdout
        finally:
            os.unlink(temp_path)


class TestLogStats:
    """Tests for log stats command."""

    def test_log_stats_missing_file(self) -> None:
        """Test stats command when log file doesn't exist."""
        with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
            mock_path.return_value = Path('/nonexistent/path.log')
            result = runner.invoke(app, ['stats'])
            assert result.exit_code == 0
            assert 'Log file not found' in result.stdout

    def test_log_stats_with_entries(self) -> None:
        """Test stats command with log entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write('2024-01-15 10:30:00,123 - cyberpulse.tasks - INFO - Task started\n')
            f.write('2024-01-15 10:31:00,456 - cyberpulse.api - ERROR - API error\n')
            f.write('2024-01-15 10:32:00,789 - cyberpulse.tasks - WARNING - Task warning\n')
            f.write('2024-01-15 10:33:00,012 - cyberpulse.tasks - DEBUG - Debug message\n')
            temp_path = f.name

        try:
            with patch('cyberpulse.cli.commands.log.get_log_file_path') as mock_path:
                mock_path.return_value = Path(temp_path)
                result = runner.invoke(app, ['stats'])
                assert result.exit_code == 0
                assert 'Log Statistics' in result.stdout
                assert 'Entries by Level' in result.stdout
                assert 'Top 10 Loggers' in result.stdout
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
        # Allow 1 second tolerance
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_hours(self) -> None:
        """Test parsing hours."""
        from datetime import datetime, timedelta
        result = parse_time_delta('2h')
        assert result is not None
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_days(self) -> None:
        """Test parsing days."""
        from datetime import datetime, timedelta
        result = parse_time_delta('7d')
        assert result is not None
        expected = datetime.now() - timedelta(days=7)
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_weeks(self) -> None:
        """Test parsing weeks."""
        from datetime import datetime, timedelta
        result = parse_time_delta('1w')
        assert result is not None
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 1

    def test_parse_invalid(self) -> None:
        """Test parsing invalid format."""
        result = parse_time_delta('invalid')
        assert result is None

    def test_parse_missing_unit(self) -> None:
        """Test parsing missing unit."""
        result = parse_time_delta('30')
        assert result is None


class TestFormatFileSize:
    """Tests for format_file_size function."""

    def test_format_bytes(self) -> None:
        """Test formatting bytes."""
        assert 'B' in format_file_size(500)

    def test_format_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        result = format_file_size(1024)
        assert 'KB' in result

    def test_format_megabytes(self) -> None:
        """Test formatting megabytes."""
        result = format_file_size(1024 * 1024)
        assert 'MB' in result

    def test_format_gigabytes(self) -> None:
        """Test formatting gigabytes."""
        result = format_file_size(1024 * 1024 * 1024)
        assert 'GB' in result


class TestLogHelp:
    """Tests for log command help."""

    def test_log_help(self) -> None:
        """Test log command help output."""
        result = runner.invoke(app, ['--help'])
        assert result.exit_code == 0
        assert 'tail' in result.stdout
        assert 'errors' in result.stdout
        assert 'search' in result.stdout
        assert 'stats' in result.stdout

    def test_tail_help(self) -> None:
        """Test tail command help."""
        result = runner.invoke(app, ['tail', '--help'])
        assert result.exit_code == 0
        assert '--lines' in result.stdout
        assert '--follow' in result.stdout

    def test_errors_help(self) -> None:
        """Test errors command help."""
        result = runner.invoke(app, ['errors', '--help'])
        assert result.exit_code == 0
        assert '--since' in result.stdout
        assert '--source' in result.stdout

    def test_search_help(self) -> None:
        """Test search command help."""
        result = runner.invoke(app, ['search', '--help'])
        assert result.exit_code == 0
        assert '--level' in result.stdout