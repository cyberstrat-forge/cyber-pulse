"""Tests for version resolution in cyberpulse.__init__."""

import pytest


class TestGetVersion:
    """Tests for _get_version() function."""

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch):
        """APP_VERSION env var should override everything."""
        monkeypatch.setenv("APP_VERSION", "v2.0.0")

        # Import fresh module to pick up env var
        import importlib

        import cyberpulse

        importlib.reload(cyberpulse)
        from cyberpulse import _get_version

        assert _get_version() == "v2.0.0"

        # Cleanup
        monkeypatch.delenv("APP_VERSION")

    def test_fallback_to_default_when_no_file(self, monkeypatch: pytest.MonkeyPatch):
        """When no env var and path resolution fails, return default."""
        monkeypatch.delenv("APP_VERSION", raising=False)

        # Test by calling _get_version directly with mocked path
        from pathlib import Path
        from unittest.mock import patch

        with patch.object(Path, "exists", return_value=False):
            # Reimport to apply mock
            import importlib

            import cyberpulse

            importlib.reload(cyberpulse)

            # Get fresh function reference
            import cyberpulse as fresh_module

            result = fresh_module._get_version()
            assert result == "1.6.0"


class TestVersionExport:
    """Tests for __version__ export."""

    def test_version_is_string(self):
        """__version__ should be a string."""
        from cyberpulse import __version__

        assert isinstance(__version__, str)

    def test_version_not_empty(self):
        """__version__ should not be empty."""
        from cyberpulse import __version__

        assert len(__version__) > 0

    def test_version_format(self):
        """__version__ should match expected format."""
        from cyberpulse import __version__

        # Valid formats: v1.5.0, 1.5.0, v1.5.0-25-gb596d0b
        # Should contain at least major.minor
        assert "." in __version__

    def test_version_matches_project(self):
        """__version__ should match project version."""
        from cyberpulse import __version__

        # Should be 1.6.0 or v1.6.0 or git describe format
        assert "1.6.0" in __version__ or __version__ == "1.6.0"


class TestVersionLogic:
    """Unit tests for version resolution logic."""

    def test_version_resolution_priority(self, monkeypatch: pytest.MonkeyPatch):
        """Test that env var takes priority over file."""
        # Set env var
        monkeypatch.setenv("APP_VERSION", "v3.0.0")

        # Import and reload
        import importlib

        import cyberpulse

        importlib.reload(cyberpulse)

        # Env var should win
        from cyberpulse import _get_version

        assert _get_version() == "v3.0.0"

        # Cleanup
        monkeypatch.delenv("APP_VERSION")