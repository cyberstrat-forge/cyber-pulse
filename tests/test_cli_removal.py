"""Tests for CLI module removal verification."""

import subprocess
import sys


class TestCLIRemoval:
    """Verify CLI module has been completely removed."""

    def test_cli_module_not_importable(self):
        """CLI module should not be importable."""
        result = subprocess.run(
            [sys.executable, "-c", "import cyberpulse.cli"],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "CLI module should not be importable"
        assert "No module named" in result.stderr or "cannot import" in result.stderr

    def test_cyber_pulse_command_not_exists(self):
        """cyber-pulse CLI command should not exist."""
        try:
            result = subprocess.run(
                ["cyber-pulse", "--help"],
                capture_output=True,
                text=True
            )
            # If we get here, command exists - should fail
            assert result.returncode != 0, "cyber-pulse command should not work"
        except FileNotFoundError:
            # Command not found - this is expected
            pass

    def test_cli_directory_not_exists(self):
        """CLI directory should not exist."""
        import pathlib
        cli_dir = pathlib.Path("src/cyberpulse/cli")
        assert not cli_dir.exists(), "CLI directory should be removed"
