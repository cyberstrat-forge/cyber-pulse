"""Log command module."""
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...config import settings

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="log",
    help="View and manage logs",
)

console = Console()


def get_log_file_path() -> Path:
    """Get the path to the log file from settings."""
    log_file = settings.log_file
    if log_file is None:
        # Default log location
        log_file = "logs/cyberpulse.log"
    return Path(log_file)


def parse_log_line(line: str) -> Optional[dict]:
    """Parse a log line into structured data.

    Args:
        line: Raw log line

    Returns:
        Dictionary with parsed log data or None if parsing fails
    """
    # Common log format patterns
    # Format: YYYY-MM-DD HH:MM:SS,mmm - name - LEVEL - message
    pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - (\w+) - (.+)$'
    match = re.match(pattern, line.strip())
    if match:
        timestamp_str, logger, level, message = match.groups()
        return {
            'timestamp': timestamp_str,
            'logger': logger,
            'level': level,
            'message': message,
        }
    return None


def read_log_lines(log_path: Path, n: int = 50, from_end: bool = True) -> list[str]:
    """Read lines from log file.

    Args:
        log_path: Path to log file
        n: Number of lines to read
        from_end: If True, read from end of file

    Returns:
        List of log lines
    """
    if not log_path.exists():
        return []

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            if from_end:
                # Read last n lines efficiently
                lines: list[str] = []
                f.seek(0, 2)  # Go to end of file
                file_size = f.tell()

                if file_size == 0:
                    return []

                # Read backwards in chunks
                chunk_size = 8192
                position = file_size
                lines_found = 0

                while position > 0 and lines_found < n:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    chunk_lines = chunk.split('\n')
                    lines = chunk_lines[:-1] + lines
                    lines_found = len([line for line in lines if line.strip()])

                # Get last n non-empty lines
                all_lines = [line for line in lines if line.strip()]
                return all_lines[-n:]
            else:
                # Read from beginning
                lines = []
                for i, line in enumerate(f):
                    if i >= n:
                        break
                    if line.strip():
                        lines.append(line.strip())
                return lines
    except OSError as e:
        logger.warning(f"Failed to read log file {log_path}: {e}")
        return []


@app.command("tail")
def tail_logs(
    n: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log file (like tail -f)"),
) -> None:
    """Tail logs from the cyber-pulse log file.

    Shows the last N lines from the log file. Use --follow to continuously
    display new log entries as they are written.
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        console.print("[dim]Logs will appear here once the application runs.[/dim]")
        raise typer.Exit(0)

    if follow:
        console.print(f"[dim]Following {log_path}... (Press Ctrl+C to stop)[/dim]")
        try:
            # Simple follow implementation
            import time
            last_size = log_path.stat().st_size
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(last_size)
                while True:
                    line = f.readline()
                    if line:
                        parsed = parse_log_line(line)
                        if parsed:
                            level = parsed['level']
                            color = {
                                'DEBUG': 'dim',
                                'INFO': 'green',
                                'WARNING': 'yellow',
                                'ERROR': 'red',
                                'CRITICAL': 'red bold',
                            }.get(level, 'white')
                            console.print(
                                f"[dim]{parsed['timestamp']}[/dim] "
                                f"[{color}]{level:8}[/{color}] "
                                f"[cyan]{parsed['logger']}[/cyan] - "
                                f"{parsed['message']}"
                            )
                        else:
                            console.print(line.rstrip())
                    else:
                        time.sleep(0.1)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following logs.[/dim]")
    else:
        lines = read_log_lines(log_path, n=n, from_end=True)
        if not lines:
            console.print("[dim]No log entries found.[/dim]")
            raise typer.Exit(0)

        console.print(Panel(f"Last {len(lines)} log entries from {log_path}", style="bold"))

        for line in lines:
            parsed = parse_log_line(line)
            if parsed:
                level = parsed['level']
                color = {
                    'DEBUG': 'dim',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red bold',
                }.get(level, 'white')
                console.print(
                    f"[dim]{parsed['timestamp']}[/dim] "
                    f"[{color}]{level:8}[/{color}] "
                    f"[cyan]{parsed['logger']}[/cyan] - "
                    f"{parsed['message']}"
                )
            else:
                console.print(line)


@app.command("errors")
def error_logs(
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Show errors since time (e.g., '1h', '24h', '7d')"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", help="Filter by source/logger name"
    ),
    n: int = typer.Option(50, "--lines", "-n", help="Maximum number of errors to show"),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
) -> None:
    """Show error logs from the cyber-pulse log file.

    Displays ERROR and CRITICAL level log entries, optionally filtered by
    time window and source.

    Examples:
        cyber-pulse log errors
        cyber-pulse log errors --since 1h
        cyber-pulse log errors --since 24h --source cyberpulse.tasks
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        raise typer.Exit(0)

    # Parse since parameter
    since_dt = None
    if since:
        since_dt = parse_time_delta(since)
        if since_dt is None:
            console.print(f"[red]Invalid time format: {since}[/red]")
            console.print("[dim]Use format like '1h', '24h', '7d', '30m'[/dim]")
            raise typer.Exit(1)

    lines = read_log_lines(log_path, n=1000, from_end=True)  # Read more to filter

    errors = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed and parsed['level'] in ('ERROR', 'CRITICAL'):
            # Apply filters
            if since_dt:
                try:
                    log_dt = datetime.strptime(parsed['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
                    if log_dt < since_dt:
                        continue
                except ValueError:
                    logger.debug(f"Could not parse timestamp: {parsed['timestamp']}")

            if source and source not in parsed['logger']:
                continue

            errors.append(parsed)

            if len(errors) >= n:
                break

    if not errors:
        console.print("[dim]No error logs found.[/dim]")
        raise typer.Exit(0)

    # JSON output
    if format == "json":
        print(json.dumps(errors, indent=2))
        raise typer.Exit(0)

    console.print(Panel(f"Found {len(errors)} error entries", style="red bold"))

    for entry in errors:
        level = entry['level']
        color = 'red bold' if level == 'CRITICAL' else 'red'
        console.print(
            f"[dim]{entry['timestamp']}[/dim] "
            f"[{color}]{level:8}[/{color}] "
            f"[cyan]{entry['logger']}[/cyan]"
        )
        console.print(f"  {entry['message']}")
        console.print()


@app.command("search")
def search_logs(
    text: str = typer.Argument(..., help="Text pattern to search for"),
    n: int = typer.Option(50, "--lines", "-n", help="Maximum number of results"),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    ),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
) -> None:
    """Search logs for a specific text pattern.

    Searches through all log entries for the given text pattern.
    Pattern matching is case-insensitive by default.

    Examples:
        cyber-pulse log search "connection failed"
        cyber-pulse log search "error" --level ERROR
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        raise typer.Exit(0)

    lines = read_log_lines(log_path, n=5000, from_end=True)  # Read more for search

    matches = []
    search_lower = text.lower()

    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            if search_lower in parsed['message'].lower() or search_lower in parsed['logger'].lower():
                if level and parsed['level'] != level.upper():
                    continue
                matches.append(parsed)

                if len(matches) >= n:
                    break
        elif search_lower in line.lower():
            # Unstructured log line
            matches.append({
                'timestamp': '-',
                'logger': '-',
                'level': '-',
                'message': line,
            })

            if len(matches) >= n:
                break

    if not matches:
        console.print(f"[dim]No matches found for '{text}'.[/dim]")
        raise typer.Exit(0)

    # JSON output
    if format == "json":
        print(json.dumps(matches, indent=2))
        raise typer.Exit(0)

    console.print(Panel(f"Found {len(matches)} matches for '{text}'", style="blue bold"))

    for entry in matches:
        log_level = entry['level']
        if log_level != '-':
            color = {
                'DEBUG': 'dim',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red bold',
            }.get(log_level, 'white')
            console.print(
                f"[dim]{entry['timestamp']}[/dim] "
                f"[{color}]{log_level:8}[/{color}] "
                f"[cyan]{entry['logger']}[/cyan] - "
                f"{entry['message']}"
            )
        else:
            console.print(entry['message'])


@app.command("stats")
def log_stats() -> None:
    """Show log statistics.

    Displays statistics about the log file including:
    - File size
    - Total number of entries
    - Entries by level
    - Top loggers by message count
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[yellow]Log file not found: {log_path}[/yellow]")
        console.print("[dim]Logs will appear here once the application runs.[/dim]")
        raise typer.Exit(0)

    # Get file stats
    file_size = log_path.stat().st_size
    size_str = format_file_size(file_size)

    # Read and analyze logs
    lines = read_log_lines(log_path, n=10000, from_end=True)

    level_counts: dict[str, int] = {}
    logger_counts: dict[str, int] = {}
    total_entries = 0

    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            total_entries += 1
            level = parsed['level']
            level_counts[level] = level_counts.get(level, 0) + 1
            logger_name = parsed['logger']
            logger_counts[logger_name] = logger_counts.get(logger_name, 0) + 1

    # Display stats
    console.print(Panel("Log Statistics", style="bold blue"))

    # File info
    console.print(f"\n[bold]File:[/bold] {log_path}")
    console.print(f"[bold]Size:[/bold] {size_str}")
    console.print(f"[bold]Entries analyzed:[/bold] {total_entries}")

    # Level distribution
    if level_counts:
        console.print("\n[bold]Entries by Level:[/bold]")
        level_table = Table(show_header=True, header_style="bold")
        level_table.add_column("Level")
        level_table.add_column("Count", justify="right")
        level_table.add_column("Percentage", justify="right")

        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            if level in level_counts:
                count = level_counts[level]
                pct = (count / total_entries * 100) if total_entries > 0 else 0
                color = {
                    'DEBUG': 'dim',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red bold',
                }.get(level, 'white')
                level_table.add_row(f"[{color}]{level}[/{color}]", str(count), f"{pct:.1f}%")

        console.print(level_table)

    # Top loggers
    if logger_counts:
        console.print("\n[bold]Top 10 Loggers:[/bold]")
        logger_table = Table(show_header=True, header_style="bold")
        logger_table.add_column("Logger")
        logger_table.add_column("Count", justify="right")

        sorted_loggers = sorted(logger_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for logger_name, count in sorted_loggers:
            logger_table.add_row(logger_name, str(count))

        console.print(logger_table)


def parse_time_delta(time_str: str) -> Optional[datetime]:
    """Parse a time delta string like '1h', '24h', '7d'.

    Args:
        time_str: Time delta string

    Returns:
        Datetime that many units ago, or None if parsing fails
    """
    match = re.match(r'^(\d+)([mhdw])$', time_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    now = datetime.now()

    if unit == 'm':  # minutes
        delta = timedelta(minutes=value)
    elif unit == 'h':  # hours
        delta = timedelta(hours=value)
    elif unit == 'd':  # days
        delta = timedelta(days=value)
    elif unit == 'w':  # weeks
        delta = timedelta(weeks=value)
    else:
        return None

    return now - delta


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@app.command("export")
def export_logs(
    output: str = typer.Option(..., "--output", "-o", help="Output file path"),
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Export logs since time (e.g., '1h', '24h', '7d')"
    ),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Filter by log level (ERROR, WARNING, INFO, DEBUG)"
    ),
) -> None:
    """Export logs to a file.

    Exports log entries to a file, optionally filtered by time and level.

    Examples:
        cyber-pulse log export --output /tmp/cyberpulse.log
        cyber-pulse log export --output /tmp/errors.log --level ERROR --since 24h
    """
    log_path = get_log_file_path()

    if not log_path.exists():
        console.print(f"[red]Log file not found: {log_path}[/red]")
        raise typer.Exit(1)

    # Parse since parameter
    since_dt = None
    if since:
        since_dt = parse_time_delta(since)
        if since_dt is None:
            console.print(f"[red]Invalid time format: {since}[/red]")
            console.print("[dim]Use format like '1h', '24h', '7d', '30m'[/dim]")
            raise typer.Exit(1)

    # Read all lines
    lines = read_log_lines(log_path, n=50000, from_end=True)

    # Filter and export
    exported = []
    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue

        # Apply filters
        if since_dt:
            try:
                log_dt = datetime.strptime(parsed['timestamp'], '%Y-%m-%d %H:%M:%S,%f')
                if log_dt < since_dt:
                    continue
            except ValueError:
                continue

        if level and parsed['level'] != level.upper():
            continue

        exported.append(line)

    if not exported:
        console.print("[dim]No log entries match the criteria.[/dim]")
        raise typer.Exit(0)

    # Write to output file
    try:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for line in exported:
                f.write(line + '\n')

        console.print(f"[green]✓[/green] Exported {len(exported)} log entries to {output}")
        console.print(f"[dim]File size: {format_file_size(output_path.stat().st_size)}[/dim]")
    except OSError as e:
        console.print(f"[red]Failed to write output file: {e}[/red]")
        raise typer.Exit(1)