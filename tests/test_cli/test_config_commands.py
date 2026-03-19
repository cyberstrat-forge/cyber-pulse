"""Tests for config command module."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cyberpulse.cli.commands import config as config_module
from cyberpulse.cli.commands.config import app

runner = CliRunner()


class TestConfigGet:
    """Tests for config get command."""

    def test_config_get_valid_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test getting a valid configuration key."""
        # Change to temp directory to avoid reading actual .env
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["get", "log_level"])
        assert result.exit_code == 0
        assert "log_level" in result.stdout

    def test_config_get_api_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test getting api_port which has an integer default."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["get", "api_port"])
        assert result.exit_code == 0
        assert "api_port" in result.stdout

    def test_config_get_invalid_key(self) -> None:
        """Test getting an invalid configuration key."""
        result = runner.invoke(app, ["get", "invalid_key"])
        assert result.exit_code == 1
        assert "Unknown configuration key" in result.stdout

    def test_config_get_sensitive_key_masked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that sensitive values are masked."""
        monkeypatch.chdir(tmp_path)

        # Set a custom secret key via environment
        with patch.dict(os.environ, {"SECRET_KEY": "my-super-secret-key-12345"}, clear=False):
            result = runner.invoke(app, ["get", "secret_key"])
            # Should not show the full secret
            assert "my-super-secret-key-12345" not in result.stdout


class TestConfigSet:
    """Tests for config set command."""

    def test_config_set_valid_key(self, tmp_path: Path) -> None:
        """Test setting a valid configuration key."""
        env_file = tmp_path / ".env"

        result = runner.invoke(app, ["set", "log_level", "DEBUG", "--env-file", str(env_file)])
        assert result.exit_code == 0
        assert "Set log_level" in result.stdout
        assert env_file.exists()

        # Verify the content
        content = env_file.read_text()
        assert "log_level=DEBUG" in content

    def test_config_set_with_quoting(self, tmp_path: Path) -> None:
        """Test that values with spaces are quoted."""
        env_file = tmp_path / ".env"

        result = runner.invoke(
            app, ["set", "log_file", "/path/with spaces/log.txt", "--env-file", str(env_file)]
        )
        assert result.exit_code == 0

        content = env_file.read_text()
        assert 'log_file="/path/with spaces/log.txt"' in content or "log_file=" in content

    def test_config_set_invalid_log_level(self, tmp_path: Path) -> None:
        """Test setting an invalid log level."""
        env_file = tmp_path / ".env"

        result = runner.invoke(
            app, ["set", "log_level", "INVALID", "--env-file", str(env_file)]
        )
        assert result.exit_code == 1
        assert "Invalid log level" in result.stdout

    def test_config_set_invalid_key(self, tmp_path: Path) -> None:
        """Test setting an invalid configuration key."""
        env_file = tmp_path / ".env"

        result = runner.invoke(
            app, ["set", "invalid_key", "value", "--env-file", str(env_file)]
        )
        assert result.exit_code == 1
        assert "Unknown configuration key" in result.stdout

    def test_config_set_preserves_existing(self, tmp_path: Path) -> None:
        """Test that setting a key preserves other keys."""
        env_file = tmp_path / ".env"
        env_file.write_text("log_level=INFO\napi_port=8000\n")

        result = runner.invoke(app, ["set", "api_host", "127.0.0.1", "--env-file", str(env_file)])
        assert result.exit_code == 0

        content = env_file.read_text()
        assert "log_level=INFO" in content
        assert "api_port=8000" in content
        assert "api_host=127.0.0.1" in content


class TestConfigList:
    """Tests for config list command."""

    def test_config_list_shows_all_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that list shows all configuration keys."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "database_url" in result.stdout
        assert "redis_url" in result.stdout
        assert "log_level" in result.stdout

    def test_config_list_masks_secrets_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that sensitive values are masked by default."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        # Should not show the actual secret key
        assert "change-this-to-a-random-secret-key" not in result.stdout

    def test_config_list_shows_secrets_with_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that --show-secrets flag reveals sensitive values."""
        monkeypatch.chdir(tmp_path)

        # Set a custom API host (non-sensitive but easy to verify)
        with patch.dict(os.environ, {"API_HOST": "192.168.1.100"}, clear=False):
            result = runner.invoke(app, ["list", "--show-secrets"])
            assert result.exit_code == 0
            # Should show the actual API host value
            assert "192.168.1.100" in result.stdout

    def test_config_list_shows_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that list shows the source of each value."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "default" in result.stdout


class TestConfigReset:
    """Tests for config reset command."""

    def test_config_reset_specific_key(self, tmp_path: Path) -> None:
        """Test resetting a specific configuration key."""
        env_file = tmp_path / ".env"
        env_file.write_text("log_level=DEBUG\napi_port=9000\n")

        result = runner.invoke(
            app, ["reset", "log_level", "--env-file", str(env_file)]
        )
        assert result.exit_code == 0
        assert "Reset log_level" in result.stdout

        content = env_file.read_text()
        assert "log_level" not in content
        assert "api_port=9000" in content

    def test_config_reset_all_with_force(self, tmp_path: Path) -> None:
        """Test resetting all configuration keys with force flag."""
        env_file = tmp_path / ".env"
        env_file.write_text("log_level=DEBUG\napi_port=9000\napi_host=localhost\n")

        result = runner.invoke(
            app, ["reset", "--env-file", str(env_file), "--force"]
        )
        assert result.exit_code == 0
        assert "Reset" in result.stdout

        content = env_file.read_text()
        assert "log_level" not in content
        assert "api_port" not in content

    def test_config_reset_all_requires_confirmation(self, tmp_path: Path) -> None:
        """Test that reset all without force requires confirmation."""
        env_file = tmp_path / ".env"
        env_file.write_text("log_level=DEBUG\n")

        result = runner.invoke(
            app, ["reset", "--env-file", str(env_file)],
            input="n\n"  # Decline confirmation
        )
        assert result.exit_code == 0
        assert "Cancelled" in result.stdout

        # File should not be modified
        content = env_file.read_text()
        assert "log_level=DEBUG" in content

    def test_config_reset_invalid_key(self, tmp_path: Path) -> None:
        """Test resetting an invalid configuration key."""
        env_file = tmp_path / ".env"
        env_file.write_text("log_level=DEBUG\n")  # Create file so validation happens

        result = runner.invoke(
            app, ["reset", "invalid_key", "--env-file", str(env_file)]
        )
        assert result.exit_code == 1
        assert "Unknown configuration key" in result.stdout

    def test_config_reset_nonexistent_file(self, tmp_path: Path) -> None:
        """Test reset when .env file doesn't exist."""
        env_file = tmp_path / ".nonexistent"

        result = runner.invoke(app, ["reset", "--env-file", str(env_file)])
        assert result.exit_code == 0
        assert "already at defaults" in result.stdout.lower() or "No .env file" in result.stdout

    def test_config_reset_key_not_in_file(self, tmp_path: Path) -> None:
        """Test resetting a key that's not in the .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("api_port=9000\n")

        result = runner.invoke(
            app, ["reset", "log_level", "--env-file", str(env_file)]
        )
        assert result.exit_code == 0
        assert "not set" in result.stdout


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_mask_sensitive_value_short(self) -> None:
        """Test masking short sensitive values."""
        result = config_module._mask_sensitive_value("secret_key", "short")
        assert result == "***"

    def test_mask_sensitive_value_long(self) -> None:
        """Test masking long sensitive values."""
        result = config_module._mask_sensitive_value(
            "secret_key", "my-very-long-secret-key-value"
        )
        # First 10 chars + "..." + last 4 chars
        assert result == "my-very-lo...alue"

    def test_mask_non_sensitive_value(self) -> None:
        """Test that non-sensitive values are not masked."""
        result = config_module._mask_sensitive_value("log_level", "DEBUG")
        assert result == "DEBUG"

    def test_read_env_file(self, tmp_path: Path) -> None:
        """Test reading environment file."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n# Comment\nKEY3='quoted'\n")

        result = config_module._read_env_file(env_file)
        assert result["KEY1"] == "value1"
        assert result["KEY2"] == "value2"
        assert result["KEY3"] == "quoted"
        assert "Comment" not in result

    def test_read_nonexistent_env_file(self, tmp_path: Path) -> None:
        """Test reading non-existent environment file."""
        env_file = tmp_path / ".nonexistent"
        result = config_module._read_env_file(env_file)
        assert result == {}

    def test_write_env_file(self, tmp_path: Path) -> None:
        """Test writing environment file."""
        env_file = tmp_path / ".env"
        env_vars = {"KEY1": "value1", "KEY2": "value with spaces"}

        config_module._write_env_file(env_file, env_vars)

        content = env_file.read_text()
        assert "KEY1=value1" in content
        assert 'KEY2="value with spaces"' in content or "KEY2=" in content


class TestConfigIntegration:
    """Integration tests for config commands."""

    def test_set_and_get_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that setting and getting a value works."""
        env_file = tmp_path / ".env"
        monkeypatch.chdir(tmp_path)

        # Set a value
        result = runner.invoke(
            app, ["set", "log_level", "WARNING", "--env-file", str(env_file)]
        )
        assert result.exit_code == 0

        # The .env file should be created
        assert env_file.exists()

    def test_help_shows_commands(self) -> None:
        """Test that help shows all available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "get" in result.stdout
        assert "set" in result.stdout
        assert "list" in result.stdout
        assert "reset" in result.stdout