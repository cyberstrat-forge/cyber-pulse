"""Tests for content CLI commands."""

import json
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from cyberpulse.cli.app import app
from cyberpulse.models import Content, ContentStatus

runner = CliRunner()


class MockContentService:
    """Mock ContentService for testing."""

    def __init__(self, contents=None, stats=None):
        self._contents = contents or []
        self._stats = stats or {"total_contents": 0, "total_source_references": 0}

    def get_contents(self, since=None, until=None, source_tier=None, limit=100, cursor=None):
        """Return mocked contents."""
        return self._contents[:limit]

    def get_content_by_id(self, content_id):
        """Return mocked content by ID."""
        for c in self._contents:
            if c.content_id == content_id:
                return c
        return None

    def get_content_statistics(self):
        """Return mocked statistics."""
        return self._stats


def create_mock_content(content_id, title, body="Test body", source_count=1):
    """Create a mock Content object."""
    content = MagicMock(spec=Content)
    content.content_id = content_id
    content.canonical_hash = hashlib.sha256(content_id.encode()).hexdigest()
    content.normalized_title = title
    content.normalized_body = body
    content.first_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    content.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
    content.source_count = source_count
    content.status = ContentStatus.ACTIVE
    return content


class TestContentList:
    """Tests for content list command."""

    def test_content_list_empty(self):
        """Test listing content when none exist."""
        mock_service = MockContentService(contents=[])
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list"])
                assert result.exit_code == 0
                assert "No content found" in result.stdout

    def test_content_list_with_content(self):
        """Test listing content with existing content."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
            create_mock_content("cnt_test_002_def", "Test Content 2"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list"])
                assert result.exit_code == 0
                assert "Content" in result.stdout
                assert "cnt_test_001_abc" in result.stdout

    def test_content_list_with_limit(self):
        """Test listing content with limit."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
            create_mock_content("cnt_test_002_def", "Test Content 2"),
            create_mock_content("cnt_test_003_ghi", "Test Content 3"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--limit", "2"])
                assert result.exit_code == 0
                # Should show only 2 results
                assert result.stdout.count("cnt_test_") == 2

    def test_content_list_json_format(self):
        """Test listing content in JSON format."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--format", "json"])
                assert result.exit_code == 0
                output = json.loads(result.stdout)
                assert isinstance(output, list)
                assert len(output) == 1
                assert "content_id" in output[0]
                assert "normalized_title" in output[0]

    def test_content_list_with_since(self):
        """Test listing content with since filter."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--since", "2020-01-01"])
                assert result.exit_code == 0
                assert "cnt_test_001_abc" in result.stdout

    def test_content_list_with_relative_since(self):
        """Test listing content with relative since filter."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--since", "-24h"])
                assert result.exit_code == 0

    def test_content_list_tier_warning(self):
        """Test that --tier shows warning about not implemented."""
        mock_service = MockContentService(contents=[])
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--tier", "T0"])
                assert result.exit_code == 0
                assert "not yet implemented" in result.stdout

    def test_content_list_invalid_since(self):
        """Test listing content with invalid since format."""
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            result = runner.invoke(app, ["content", "list", "--since", "invalid-date"])
            assert result.exit_code == 1
            assert "Invalid date format" in result.stdout


class TestContentGet:
    """Tests for content get command."""

    def test_content_get_by_id(self):
        """Test getting content by ID."""
        content = create_mock_content("cnt_test_001_abc", "Test Content Title")
        mock_service = MockContentService(contents=[content])
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "cnt_test_001_abc"])
                assert result.exit_code == 0
                output = json.loads(result.stdout)
                assert output["content_id"] == "cnt_test_001_abc"
                assert output["normalized_title"] == "Test Content Title"

    def test_content_get_by_id_text_format(self):
        """Test getting content by ID in text format."""
        content = create_mock_content("cnt_test_001_abc", "Test Content Title")
        mock_service = MockContentService(contents=[content])
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "cnt_test_001_abc", "--format", "text"])
                assert result.exit_code == 0
                assert "cnt_test_001_abc" in result.stdout
                assert "Test Content Title" in result.stdout
                assert "First seen" in result.stdout
                assert "Source count" in result.stdout

    def test_content_get_not_found(self):
        """Test getting non-existent content."""
        mock_service = MockContentService(contents=[])
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "cnt_nonexistent"])
                assert result.exit_code == 1
                assert "not found" in result.stdout.lower()

    def test_content_get_without_id(self):
        """Test getting content without ID lists content."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
            create_mock_content("cnt_test_002_def", "Test Content 2"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "--limit", "2"])
                assert result.exit_code == 0
                output = json.loads(result.stdout)
                assert isinstance(output, list)
                assert len(output) <= 2

    def test_content_get_without_id_text_format(self):
        """Test getting content without ID in text format."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "--limit", "1", "--format", "text"])
                assert result.exit_code == 0
                # Should show content with panel
                assert "cnt_test_001_abc" in result.stdout

    def test_content_get_with_since(self):
        """Test getting content with since filter."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "--since", "2020-01-01", "--limit", "5"])
                assert result.exit_code == 0
                output = json.loads(result.stdout)
                assert isinstance(output, list)

    def test_content_get_tier_warning(self):
        """Test that --tier shows warning when getting without ID."""
        contents = [
            create_mock_content("cnt_test_001_abc", "Test Content 1"),
        ]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "get", "--tier", "T1"])
                assert result.exit_code == 0
                assert "not yet implemented" in result.stdout


class TestContentStats:
    """Tests for content stats command."""

    def test_content_stats_empty(self):
        """Test stats when no content exists."""
        mock_service = MockContentService(contents=[], stats={"total_contents": 0, "total_source_references": 0})
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "stats"])
                assert result.exit_code == 0
                assert "Total Contents" in result.stdout
                assert "0" in result.stdout

    def test_content_stats_with_content(self):
        """Test stats with existing content."""
        mock_service = MockContentService(
            contents=[create_mock_content(f"cnt_{i}", f"Content {i}") for i in range(3)],
            stats={"total_contents": 3, "total_source_references": 6}
        )
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "stats"])
                assert result.exit_code == 0
                assert "Total Contents" in result.stdout
                assert "3" in result.stdout
                assert "6" in result.stdout

    def test_content_stats_json_format(self):
        """Test stats in JSON format."""
        mock_service = MockContentService(
            stats={"total_contents": 3, "total_source_references": 6}
        )
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "stats", "--format", "json"])
                assert result.exit_code == 0
                output = json.loads(result.stdout)
                assert "total_contents" in output
                assert "total_source_references" in output
                assert output["total_contents"] == 3
                assert output["total_source_references"] == 6

    def test_content_stats_avg_sources(self):
        """Test stats shows average sources per content."""
        mock_service = MockContentService(
            stats={"total_contents": 3, "total_source_references": 6}
        )
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "stats"])
                assert result.exit_code == 0
                # Average should be 6/3 = 2.00
                assert "2.00" in result.stdout


class TestContentHelp:
    """Tests for content command help."""

    def test_content_help(self):
        """Test content module help is accessible."""
        result = runner.invoke(app, ["content", "--help"])
        assert result.exit_code == 0
        assert "Manage collected content" in result.stdout
        assert "list" in result.stdout
        assert "get" in result.stdout
        assert "stats" in result.stdout

    def test_content_list_help(self):
        """Test content list command help."""
        result = runner.invoke(app, ["content", "list", "--help"])
        assert result.exit_code == 0
        assert "--since" in result.stdout
        assert "--tier" in result.stdout
        assert "--limit" in result.stdout
        assert "--format" in result.stdout

    def test_content_get_help(self):
        """Test content get command help."""
        result = runner.invoke(app, ["content", "get", "--help"])
        assert result.exit_code == 0
        assert "CONTENT_ID" in result.stdout or "content_id" in result.stdout
        assert "--since" in result.stdout
        assert "--format" in result.stdout

    def test_content_stats_help(self):
        """Test content stats command help."""
        result = runner.invoke(app, ["content", "stats", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.stdout


class TestDatetimeParsing:
    """Tests for datetime parsing in CLI."""

    def test_invalid_relative_time(self):
        """Test invalid relative time format shows error."""
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            result = runner.invoke(app, ["content", "list", "--since", "-invalid"])
            assert result.exit_code == 1
            assert "Invalid" in result.stdout

    def test_iso_datetime(self):
        """Test ISO datetime format."""
        contents = [create_mock_content("cnt_test_001_abc", "Test Content 1")]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                now = datetime.now(timezone.utc)
                iso_str = now.strftime("%Y-%m-%dT%H:%M:%S")
                result = runner.invoke(app, ["content", "list", "--since", iso_str])
                assert result.exit_code == 0

    def test_date_only(self):
        """Test date-only format."""
        contents = [create_mock_content("cnt_test_001_abc", "Test Content 1")]
        mock_service = MockContentService(contents=contents)
        with patch("cyberpulse.cli.commands.content.SessionLocal"):
            with patch("cyberpulse.cli.commands.content.ContentService", return_value=mock_service):
                result = runner.invoke(app, ["content", "list", "--since", "2026-03-01"])
                assert result.exit_code == 0