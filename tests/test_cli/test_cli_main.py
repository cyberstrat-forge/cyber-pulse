"""
Tests for CLI main entry point.
"""
from typer.testing import CliRunner

from cyberpulse.cli.app import app
from cyberpulse import __version__


runner = CliRunner()


class TestCLICommands:
    """Tests for top-level CLI commands."""

    def test_cli_version(self) -> None:
        """Test version command shows correct version."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout
        assert "cyber-pulse version" in result.stdout

    def test_cli_help(self) -> None:
        """Test help flag shows usage information."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "cyber-pulse" in result.stdout
        assert "Security Intelligence Collection System" in result.stdout

    def test_cli_help_shows_commands(self) -> None:
        """Test help shows all registered commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Check command modules are listed
        assert "source" in result.stdout
        assert "job" in result.stdout
        assert "content" in result.stdout
        assert "client" in result.stdout
        assert "config" in result.stdout
        assert "log" in result.stdout
        assert "diagnose" in result.stdout
        # Check standalone commands
        assert "shell" in result.stdout
        assert "version" in result.stdout
        assert "server" in result.stdout


class TestServerCommand:
    """Tests for server command."""

    def test_server_invalid_action(self) -> None:
        """Test server command with invalid action."""
        result = runner.invoke(app, ["server", "invalid"])
        assert result.exit_code == 1
        assert "Invalid action" in result.stdout

    def test_server_start_help(self) -> None:
        """Test server command help."""
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "start|stop|restart|status" in result.stdout
        assert "--port" in result.stdout
        assert "--host" in result.stdout

    def test_server_stop_not_implemented(self) -> None:
        """Test server stop shows not implemented message."""
        result = runner.invoke(app, ["server", "stop"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout

    def test_server_restart_not_implemented(self) -> None:
        """Test server restart shows not implemented message."""
        result = runner.invoke(app, ["server", "restart"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout

    def test_server_status_not_implemented(self) -> None:
        """Test server status shows not implemented message."""
        result = runner.invoke(app, ["server", "status"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.stdout


class TestCommandModules:
    """Tests for command module registration."""

    def test_source_module_help(self) -> None:
        """Test source command module is accessible."""
        result = runner.invoke(app, ["source", "--help"])
        assert result.exit_code == 0
        assert "Manage intelligence sources" in result.stdout

    def test_job_module_help(self) -> None:
        """Test job command module is accessible."""
        result = runner.invoke(app, ["job", "--help"])
        assert result.exit_code == 0
        assert "Manage collection jobs" in result.stdout

    def test_content_module_help(self) -> None:
        """Test content command module is accessible."""
        result = runner.invoke(app, ["content", "--help"])
        assert result.exit_code == 0
        assert "Manage collected content" in result.stdout

    def test_client_module_help(self) -> None:
        """Test client command module is accessible."""
        result = runner.invoke(app, ["client", "--help"])
        assert result.exit_code == 0
        assert "Manage API clients" in result.stdout

    def test_config_module_help(self) -> None:
        """Test config command module is accessible."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "Manage configuration" in result.stdout

    def test_log_module_help(self) -> None:
        """Test log command module is accessible."""
        result = runner.invoke(app, ["log", "--help"])
        assert result.exit_code == 0
        assert "View and manage logs" in result.stdout

    def test_diagnose_module_help(self) -> None:
        """Test diagnose command module is accessible."""
        result = runner.invoke(app, ["diagnose", "--help"])
        assert result.exit_code == 0
        assert "System diagnostics" in result.stdout


class TestTUI:
    """Tests for TUI module."""

    def test_tui_start(self) -> None:
        """Test TUI can be initialized."""
        from cyberpulse.cli.tui import CyberPulseTUI

        # Test TUI state initialization
        tui = CyberPulseTUI()
        assert tui.state is not None
        assert tui.state.output_lines == []
        assert tui.state.command_history == []
        assert tui.running is True

    def test_tui_commands_defined(self) -> None:
        """Test TUI has expected commands defined."""
        from cyberpulse.cli.tui import COMMANDS

        expected_commands = ["/help", "/exit", "/quit", "/clear"]
        for cmd in expected_commands:
            assert cmd in COMMANDS

    def test_tui_help_text(self) -> None:
        """Test TUI help text generation."""
        from cyberpulse.cli.tui import get_help_text

        help_text = get_help_text()
        assert "Available commands" in help_text
        assert "/help" in help_text
        assert "/exit" in help_text

    def test_tui_status_text(self) -> None:
        """Test TUI status text generation."""
        from cyberpulse.cli.tui import get_status_text

        # Test connected status
        status = get_status_text(db_connected=True)
        assert "Running" in status
        assert "Connected" in status

        # Test disconnected status
        status = get_status_text(db_connected=False)
        assert "Running" in status
        assert "Disconnected" in status

    def test_tui_state_operations(self) -> None:
        """Test TUI state operations."""
        from cyberpulse.cli.tui import TUIState

        state = TUIState()

        # Test adding output
        state.add_output("Test output")
        assert "Test output" in state.output_lines

        # Test adding to history
        state.add_to_history("test command")
        assert "test command" in state.command_history

        # Test clearing output
        state.clear_output()
        assert state.output_lines == []

        # Test history limit
        for i in range(60):
            state.add_to_history(f"command {i}")
        assert len(state.command_history) == 50


class TestCLIIntegration:
    """Integration tests for CLI."""

    def test_cli_no_args_shows_help(self) -> None:
        """Test running CLI without args shows help."""
        result = runner.invoke(app, [])
        # Typer returns exit code 2 when no args provided, but shows error message
        assert "Missing command" in result.output or "Usage" in result.output

    def test_cli_version_matches_package(self) -> None:
        """Test CLI version matches package version."""
        result = runner.invoke(app, ["version"])
        assert __version__ in result.stdout