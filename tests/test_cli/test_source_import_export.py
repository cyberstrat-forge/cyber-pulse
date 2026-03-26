"""Tests for CLI source import/export commands."""

import tempfile
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner

from cyberpulse.cli.app import app
from cyberpulse.models import Source, SourceTier
from cyberpulse.services import SourceService

runner = CliRunner()


# Sample OPML content
OPML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>Test OPML</title>
  </head>
  <body>
    <outline text="Tier T0">
      <outline text="RSS Feed 1" title="RSS Feed 1" type="rss" xmlUrl="https://example.com/feed1.xml" cyberpulse_tier="T0" cyberpulse_score="90"/>
    </outline>
    <outline text="Tier T1">
      <outline text="RSS Feed 2" title="RSS Feed 2" type="rss" xmlUrl="https://example.com/feed2.xml" cyberpulse_tier="T1" cyberpulse_score="70"/>
    </outline>
  </body>
</opml>
"""

# Sample YAML content
YAML_SAMPLE = """
sources:
  - name: "Test RSS Source"
    connector_type: "rss"
    tier: "T1"
    score: 70.0
    config:
      feed_url: "https://example.com/feed.xml"

  - name: "Test API Source"
    connector_type: "api"
    tier: "T0"
    score: 85.0
    config:
      url: "https://api.example.com/v1"
      api_key: "test_key"
"""


class TestDetectFormat:
    """Tests for format detection."""

    def test_detect_opml_by_extension(self) -> None:
        """Test detecting OPML format by file extension."""
        from cyberpulse.cli.commands.source import _detect_format

        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            f.write(OPML_SAMPLE.encode())
            f.flush()
            result = _detect_format(Path(f.name))

        assert result == "opml"

    def test_detect_yaml_by_extension(self) -> None:
        """Test detecting YAML format by file extension."""
        from cyberpulse.cli.commands.source import _detect_format

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()
            result = _detect_format(Path(f.name))

        assert result == "yaml"

    def test_detect_opml_by_content(self) -> None:
        """Test detecting OPML format by content."""
        from cyberpulse.cli.commands.source import _detect_format

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(OPML_SAMPLE.encode())
            f.flush()
            result = _detect_format(Path(f.name))

        assert result == "opml"

    def test_detect_yaml_by_content(self) -> None:
        """Test detecting YAML format by content."""
        from cyberpulse.cli.commands.source import _detect_format

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()
            result = _detect_format(Path(f.name))

        assert result == "yaml"

    def test_detect_unknown_format(self) -> None:
        """Test detecting unknown format."""
        from cyberpulse.cli.commands.source import _detect_format

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"random content")
            f.flush()
            result = _detect_format(Path(f.name))

        assert result == "unknown"


class TestParseOPML:
    """Tests for OPML parsing."""

    def test_parse_opml_success(self) -> None:
        """Test parsing valid OPML."""
        from cyberpulse.cli.commands.source import _parse_opml

        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            f.write(OPML_SAMPLE.encode())
            f.flush()
            sources = _parse_opml(Path(f.name))

        assert len(sources) == 2
        assert sources[0]["name"] == "RSS Feed 1"
        assert sources[0]["connector_type"] == "rss"
        assert sources[0]["config"]["feed_url"] == "https://example.com/feed1.xml"
        assert sources[0]["tier"] == "T0"

    def test_parse_opml_invalid(self) -> None:
        """Test parsing invalid OPML."""
        from cyberpulse.cli.commands.source import _parse_opml

        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            f.write(b"not valid xml")
            f.flush()

        try:
            _parse_opml(Path(f.name))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestParseYAML:
    """Tests for YAML parsing."""

    def test_parse_yaml_success(self) -> None:
        """Test parsing valid YAML."""
        from cyberpulse.cli.commands.source import _parse_yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()
            sources = _parse_yaml(Path(f.name))

        assert len(sources) == 2
        assert sources[0]["name"] == "Test RSS Source"
        assert sources[0]["connector_type"] == "rss"
        assert sources[1]["connector_type"] == "api"

    def test_parse_yaml_invalid_structure(self) -> None:
        """Test parsing YAML with invalid structure."""
        from cyberpulse.cli.commands.source import _parse_yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"just a string")
            f.flush()

        try:
            _parse_yaml(Path(f.name))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_parse_yaml_missing_sources_key(self) -> None:
        """Test parsing YAML without sources key."""
        from cyberpulse.cli.commands.source import _parse_yaml

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"other_key: value")
            f.flush()

        try:
            _parse_yaml(Path(f.name))
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


class TestImportSources:
    """Tests for source import command."""

    def test_import_yaml_dry_run(self, db_session) -> None:
        """Test importing YAML with dry run."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name, "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run complete" in result.stdout
        # Rich table may wrap text across lines, so check without whitespace
        assert "Test RSS" in result.stdout and "Source" in result.stdout

    def test_import_yaml_success(self, db_session) -> None:
        """Test importing YAML successfully."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name])

        assert result.exit_code == 0
        assert "Imported: 2" in result.stdout

    def test_import_opml_success(self, db_session) -> None:
        """Test importing OPML successfully."""
        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            f.write(OPML_SAMPLE.encode())
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name])

        assert result.exit_code == 0
        assert "Imported:" in result.stdout

    def test_import_file_not_found(self, db_session) -> None:
        """Test importing non-existent file."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", "/nonexistent/file.yaml"])

        assert result.exit_code == 1
        assert "File not found" in result.stdout

    def test_import_invalid_format(self, db_session) -> None:
        """Test importing with invalid format."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"random content")
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name])

        assert result.exit_code == 1
        assert "Could not detect file format" in result.stdout

    def test_import_skip_existing(self, db_session) -> None:
        """Test importing with existing sources skipped."""
        service = SourceService(db_session)
        service.add_source("Test RSS Source", "rss", tier=SourceTier.T1)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(YAML_SAMPLE.encode())
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name, "--skip-existing"])

        assert result.exit_code == 0
        assert "Skipped:" in result.stdout


class TestExportSources:
    """Tests for source export command."""

    def test_export_yaml_success(self, db_session) -> None:
        """Test exporting to YAML."""
        service = SourceService(db_session)
        service.add_source("Export Test 1", "rss", tier=SourceTier.T0)
        service.add_source("Export Test 2", "api", tier=SourceTier.T1)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            output_path = f.name

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "-o", output_path])

        assert result.exit_code == 0
        assert "Exported to:" in result.stdout

        # Verify file content
        content = Path(output_path).read_text()
        assert "Export Test 1" in content
        assert "Export Test 2" in content

    def test_export_opml_success(self, db_session) -> None:
        """Test exporting to OPML."""
        service = SourceService(db_session)
        service.add_source("OPML Export Test", "rss", tier=SourceTier.T0, config={"feed_url": "https://example.com/feed.xml"})

        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            output_path = f.name

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "-o", output_path, "--format", "opml"])

        assert result.exit_code == 0
        assert "Exported to:" in result.stdout

        # Verify file content
        content = Path(output_path).read_text()
        assert "<?xml" in content
        assert "<opml" in content

    def test_export_filter_by_tier(self, db_session) -> None:
        """Test exporting with tier filter."""
        service = SourceService(db_session)
        service.add_source("T0 Source", "rss", tier=SourceTier.T0)
        service.add_source("T2 Source", "rss", tier=SourceTier.T2)

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            output_path = f.name

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "-o", output_path, "--tier", "T0"])

        assert result.exit_code == 0

        # Verify only T0 exported
        content = Path(output_path).read_text()
        assert "T0 Source" in content
        assert "T2 Source" not in content

    def test_export_empty(self, db_session) -> None:
        """Test exporting when no sources."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export"])

        assert result.exit_code == 0
        assert "No sources to export" in result.stdout

    def test_export_invalid_format(self, db_session) -> None:
        """Test exporting with invalid format."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "--format", "invalid"])

        assert result.exit_code == 1
        assert "Invalid format" in result.stdout


class TestListSources:
    """Tests for source list command."""

    def test_list_sources_table(self, db_session) -> None:
        """Test listing sources in table format."""
        service = SourceService(db_session)
        service.add_source("List Test 1", "rss", tier=SourceTier.T1)
        service.add_source("List Test 2", "api", tier=SourceTier.T0)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list"])

        assert result.exit_code == 0
        # Table output should show sources found
        assert "found" in result.stdout.lower()

    def test_list_sources_yaml_format(self, db_session) -> None:
        """Test listing sources in YAML format."""
        service = SourceService(db_session)
        service.add_source("YAML List Test", "rss", tier=SourceTier.T1)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--format", "yaml"])

        assert result.exit_code == 0
        assert "YAML List Test" in result.stdout
        assert "sources:" in result.stdout

    def test_list_sources_json_format(self, db_session) -> None:
        """Test listing sources in JSON format."""
        service = SourceService(db_session)
        service.add_source("JSON List Test", "rss", tier=SourceTier.T1)

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--format", "json"])

        assert result.exit_code == 0
        assert "JSON List Test" in result.stdout
        assert '"sources"' in result.stdout

    def test_list_sources_filter_by_tier(self, db_session) -> None:
        """Test listing sources filtered by tier."""
        service = SourceService(db_session)
        t0_source, _ = service.add_source("T0 Filter Test", "rss", tier=SourceTier.T0)
        t2_source, _ = service.add_source("T2 Filter Test", "rss", tier=SourceTier.T2)

        assert t0_source is not None, "Failed to create T0 source"
        assert t2_source is not None, "Failed to create T2 source"

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--tier", "T0"])

        assert result.exit_code == 0
        assert t0_source.source_id in result.stdout  # type: ignore[operator]
        assert t2_source.source_id not in result.stdout  # type: ignore[operator]

    def test_list_sources_empty(self, db_session) -> None:
        """Test listing when no sources."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list"])

        assert result.exit_code == 0
        assert "No sources found" in result.stdout

    def test_list_sources_invalid_tier(self, db_session) -> None:
        """Test listing with invalid tier filter."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--tier", "T9"])

        assert result.exit_code == 1
        assert "Invalid tier" in result.stdout

    def test_list_sources_invalid_status(self, db_session) -> None:
        """Test listing with invalid status filter."""
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "list", "--status", "invalid"])

        assert result.exit_code == 1
        assert "Invalid status" in result.stdout


class TestExportImportRoundTrip:
    """Tests for export/import round trip."""

    def test_yaml_round_trip(self, db_session) -> None:
        """Test exporting and re-importing YAML."""
        # Create sources
        service = SourceService(db_session)
        source1, _ = service.add_source("Round Trip 1", "rss", tier=SourceTier.T0, config={"feed_url": "https://example.com/1.xml"})
        source2, _ = service.add_source("Round Trip 2", "api", tier=SourceTier.T1, config={"url": "https://api.example.com"})

        # Export
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            output_path = f.name

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "-o", output_path])
            assert result.exit_code == 0

        # Clear sources (simulate new database)
        for s in db_session.query(Source).all():
            db_session.delete(s)
        db_session.commit()

        # Import
        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", output_path])

        assert result.exit_code == 0
        assert "Imported:" in result.stdout


class TestOPMLConstraints:
    """Tests for OPML-specific constraints."""

    def test_opml_only_exports_rss(self, db_session) -> None:
        """Test that OPML only exports RSS sources."""
        service = SourceService(db_session)
        service.add_source("RSS Source", "rss", tier=SourceTier.T0, config={"feed_url": "https://example.com/feed.xml"})
        service.add_source("API Source", "api", tier=SourceTier.T1, config={"url": "https://api.example.com"})

        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            output_path = f.name

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "export", "-o", output_path, "--format", "opml"])

        assert result.exit_code == 0
        assert "non-RSS sources will be excluded" in result.stdout

        # Verify only RSS exported
        content = Path(output_path).read_text()
        assert "RSS Source" in content
        assert "API Source" not in content

    def test_opml_import_creates_rss_only(self, db_session) -> None:
        """Test that OPML import creates RSS sources only."""
        with tempfile.NamedTemporaryFile(suffix=".opml", delete=False) as f:
            f.write(OPML_SAMPLE.encode())
            f.flush()

        with patch("cyberpulse.cli.commands.source.SessionLocal") as mock_session:
            mock_session.return_value = db_session
            result = runner.invoke(app, ["source", "import", f.name])

        assert result.exit_code == 0

        # Verify all imported sources are RSS type
        sources = db_session.query(Source).all()
        for s in sources:
            assert s.connector_type == "rss"