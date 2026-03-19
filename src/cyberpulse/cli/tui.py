"""
Interactive TUI module for cyber-pulse CLI.

This module provides an interactive terminal user interface with:
- Command history (up/down arrows)
- Tab completion for commands
- Rich output formatting (tables, colors)
- Real-time status bar

Layout:
+-----------------------------------------+
|  cyber-pulse CLI                        |
|  Type '/help' for commands              |
+-----------------------------------------+
|  [Output Area]                          |
|                                         |
+-----------------------------------------+
|  cyber-pulse> [Input]                   |
+-----------------------------------------+
|  Status: Running | DB: Connected        |
+-----------------------------------------+
"""
import logging
import shlex
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Box, Label
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

# Define styles
STYLE = Style.from_dict(
    {
        "header": "bold cyan",
        "status": "bold green",
        "input": "bold white",
        "output": "white",
        "error": "bold red",
        "success": "bold green",
        "warning": "bold yellow",
    }
)

# Command definitions
COMMANDS = {
    "/help": "Show available commands",
    "/exit": "Exit TUI mode",
    "/quit": "Exit TUI mode (alias)",
    "/clear": "Clear output area",
    "source": "Manage intelligence sources (use 'source --help')",
    "job": "Manage collection jobs (use 'job --help')",
    "content": "Manage collected content (use 'content --help')",
    "client": "Manage API clients (use 'client --help')",
    "config": "Manage configuration (use 'config --help')",
    "log": "View and manage logs (use 'log --help')",
    "diagnose": "System diagnostics (use 'diagnose --help')",
    "version": "Show version",
}


def get_status_text(db_connected: bool = True) -> str:
    """Get status bar text."""
    db_status = "Connected" if db_connected else "Disconnected"
    return f"Status: Running | DB: {db_status}"


def get_help_text() -> str:
    """Get help text for TUI."""
    lines = ["Available commands:"]
    for cmd, desc in COMMANDS.items():
        lines.append(f"  {cmd:<15} - {desc}")
    lines.append("\nTip: Use Tab for auto-completion, Up/Down for command history")
    return "\n".join(lines)


class TUIState:
    """State for the TUI application."""

    def __init__(self) -> None:
        self.output_lines: list[str] = []
        self.command_history: list[str] = []
        self.history_index: int = 0
        self.db_connected: bool = True

    def add_output(self, text: str, style: str = "output") -> None:
        """Add text to output area."""
        self.output_lines.append(text)
        # Keep only last 100 lines
        if len(self.output_lines) > 100:
            self.output_lines = self.output_lines[-100:]

    def clear_output(self) -> None:
        """Clear output area."""
        self.output_lines = []

    def add_to_history(self, command: str) -> None:
        """Add command to history."""
        if command and (not self.command_history or self.command_history[-1] != command):
            self.command_history.append(command)
            # Keep only last 50 commands
            if len(self.command_history) > 50:
                self.command_history = self.command_history[-50:]
        self.history_index = len(self.command_history)


class CyberPulseTUI:
    """Interactive TUI application for cyber-pulse."""

    def __init__(self) -> None:
        self.state = TUIState()
        self.running = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        # Create buffers
        self.output_buffer = Buffer()
        self.input_buffer = Buffer()

        # Create key bindings
        self.key_bindings = KeyBindings()

        @self.key_bindings.add("enter")
        def _(event: Any) -> None:
            """Handle Enter key - execute command."""
            command = self.input_buffer.text.strip()
            if command:
                self.state.add_to_history(command)
                self._execute_command(command)
                self.input_buffer.text = ""

        @self.key_bindings.add("up")
        def _(event: Any) -> None:
            """Handle Up arrow - navigate command history."""
            if self.state.command_history and self.state.history_index > 0:
                self.state.history_index -= 1
                self.input_buffer.text = self.state.command_history[self.state.history_index]
                self.input_buffer.cursor_position = len(self.input_buffer.text)

        @self.key_bindings.add("down")
        def _(event: Any) -> None:
            """Handle Down arrow - navigate command history."""
            if self.state.history_index < len(self.state.command_history) - 1:
                self.state.history_index += 1
                self.input_buffer.text = self.state.command_history[self.state.history_index]
                self.input_buffer.cursor_position = len(self.input_buffer.text)
            elif self.state.history_index == len(self.state.command_history) - 1:
                self.state.history_index = len(self.state.command_history)
                self.input_buffer.text = ""

        @self.key_bindings.add("c-c")
        def _(event: Any) -> None:
            """Handle Ctrl+C - clear input or exit."""
            if self.input_buffer.text:
                self.input_buffer.text = ""
            else:
                self.state.add_output("Use /exit or /quit to exit")

        @self.key_bindings.add("tab")
        def _(event: Any) -> None:
            """Handle Tab - auto-completion."""
            text = self.input_buffer.text
            if text.startswith("/"):
                # Complete slash commands
                matches = [cmd for cmd in COMMANDS if cmd.startswith(text)]
                if len(matches) == 1:
                    self.input_buffer.text = matches[0] + " "
                    self.input_buffer.cursor_position = len(self.input_buffer.text)
                elif len(matches) > 1:
                    self.state.add_output("  ".join(matches))
            else:
                # Complete CLI commands
                matches = [cmd for cmd in ["source", "job", "content", "client", "config", "log", "diagnose", "version"] if cmd.startswith(text)]
                if len(matches) == 1:
                    self.input_buffer.text = matches[0] + " "
                    self.input_buffer.cursor_position = len(self.input_buffer.text)
                elif len(matches) > 1:
                    self.state.add_output("  ".join(matches))

        # Build layout
        self._build_layout()

    def _build_layout(self) -> None:
        """Build the TUI layout."""
        # Header
        header = Window(
            content=FormattedTextControl(
                lambda: [
                    ("class:header", " cyber-pulse CLI\n"),
                    ("class:output", " Type '/help' for commands\n"),
                    ("class:output", "-" * 50),
                ]
            ),
            height=3,
        )

        # Output area
        self.output_control = FormattedTextControl(
            lambda: [("class:output", "\n".join(self.state.output_lines[-20:]))]
        )
        output_area = Window(
            content=self.output_control,
            height=15,
        )

        # Input area
        input_area = Box(
            Window(
                content=BufferControl(buffer=self.input_buffer),
                height=1,
            ),
            padding=1,
        )

        # Status bar
        self.status_control = FormattedTextControl(
            lambda: [("class:status", " " + get_status_text(self.state.db_connected))]
        )
        status_bar = Window(
            content=self.status_control,
            height=1,
        )

        # Main layout
        self.layout = Layout(
            HSplit(
                [
                    header,
                    Window(height=1),  # Spacer
                    output_area,
                    Window(height=1),  # Spacer
                    Label("cyber-pulse>", style="class:input"),
                    input_area,
                    status_bar,
                ]
            )
        )

    def _execute_command(self, command: str) -> None:
        """Execute a command."""
        self.state.add_output(f"> {command}")

        # Handle built-in commands
        if command in ("/exit", "/quit"):
            self.state.add_output("Exiting TUI mode...")
            self.running = False
            return

        if command == "/help":
            self.state.add_output(get_help_text())
            return

        if command == "/clear":
            self.state.clear_output()
            self.state.add_output("Output cleared.")
            return

        # Handle version
        if command == "version":
            from .. import __version__
            self.state.add_output(f"cyber-pulse version {__version__}")
            return

        # For other commands, use the CLI app
        try:
            import subprocess
            import sys

            result = subprocess.run(
                [sys.executable, "-m", "cyberpulse.cli.app"] + shlex.split(command),
                capture_output=True,
                text=True,
            )
            if result.stdout:
                self.state.add_output(result.stdout.strip())
            if result.stderr:
                self.state.add_output(result.stderr.strip(), style="error")
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            self.state.add_output(f"Error: {e}", style="error")

    def run(self) -> None:
        """Run the TUI application."""
        # Initial welcome message
        self.state.add_output("Welcome to cyber-pulse TUI!")
        self.state.add_output("Type /help for available commands.\n")

        # Create application
        application: Application[Any] = Application(
            layout=self.layout,
            key_bindings=self.key_bindings,
            full_screen=False,
            style=STYLE,
        )

        # Run until exit
        while self.running:
            try:
                application.run()
                if not self.running:
                    break
            except KeyboardInterrupt:
                if self.input_buffer.text:
                    self.input_buffer.text = ""
                else:
                    self.state.add_output("Use /exit or /quit to exit")


def run_tui() -> None:
    """
    Start interactive TUI mode.

    This function creates and runs the interactive terminal user interface
    for cyber-pulse, providing a shell-like experience with command history,
    auto-completion, and rich output formatting.
    """
    try:
        tui = CyberPulseTUI()
        tui.run()
    except Exception as e:
        logging.error(f"TUI error: {e}")
        console.print(f"[red]Error starting TUI: {e}[/red]")
        console.print("[yellow]Falling back to standard CLI mode.[/yellow]")
        console.print("Run 'cyber-pulse --help' for available commands.")


if __name__ == "__main__":
    run_tui()