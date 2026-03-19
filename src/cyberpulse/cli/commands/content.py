"""Content command module for managing collected content."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...database import SessionLocal
from ...services import ContentService

logger = logging.getLogger(__name__)
app = typer.Typer(
    name="content",
    help="Manage collected content",
)

console = Console()


def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse datetime string in various formats.

    Supports:
    - ISO format: 2026-03-19T14:30:00
    - Date only: 2026-03-19
    - Relative: -1d, -2h, -30m

    Args:
        date_str: Date string to parse

    Returns:
        Parsed datetime or None
    """
    if not date_str:
        return None

    # Relative time
    if date_str.startswith("-"):
        try:
            value = int(date_str[1:-1])
            unit = date_str[-1].lower()
            now = datetime.now(timezone.utc)

            if unit == "d":
                return now - __import__("datetime").timedelta(days=value)
            elif unit == "h":
                return now - __import__("datetime").timedelta(hours=value)
            elif unit == "m":
                return now - __import__("datetime").timedelta(minutes=value)
        except (ValueError, IndexError):
            console.print(f"[red]Invalid relative time format: {date_str}[/red]")
            raise typer.Exit(1)

    # ISO format with time
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    # Date only
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    console.print(f"[red]Invalid date format: {date_str}[/red]")
    console.print("Use ISO format (2026-03-19T14:30:00), date (2026-03-19), or relative (-1d, -2h, -30m)")
    raise typer.Exit(1)


@app.command("list")
def list_content(
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Filter content since this time (ISO date, or -Nd/-Nh/-Nm)"
    ),
    tier: Optional[str] = typer.Option(
        None, "--tier", "-t", help="Filter by source tier (T0, T1, T2, T3)"
    ),
    limit: int = typer.Option(
        100, "--limit", "-l", help="Maximum number of results"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json)"
    ),
) -> None:
    """List collected content.

    Examples:
        cyber-pulse content list
        cyber-pulse content list --since 2026-03-19
        cyber-pulse content list --since -7d --limit 50
        cyber-pulse content list --format json
    """
    since_dt = parse_datetime(since)

    # Note: tier filtering is not yet implemented in ContentService
    # This is a placeholder for future implementation
    if tier:
        console.print("[yellow]Warning: --tier filtering is not yet implemented[/yellow]")

    db = SessionLocal()
    try:
        service = ContentService(db)
        contents = service.get_contents(since=since_dt, limit=limit)

        if not contents:
            console.print("[yellow]No content found[/yellow]")
            return

        if format == "json":
            output = []
            for content in contents:
                output.append({
                    "content_id": content.content_id,
                    "normalized_title": content.normalized_title,
                    "source_count": content.source_count,
                    "first_seen_at": content.first_seen_at.isoformat() if content.first_seen_at else None,
                    "last_seen_at": content.last_seen_at.isoformat() if content.last_seen_at else None,
                    "status": content.status.value if content.status else None,
                })
            console.print(json.dumps(output, indent=2))
        else:
            table = Table(title=f"Content ({len(contents)} results)")
            table.add_column("Content ID", style="cyan", no_wrap=True)
            table.add_column("Title", style="green")
            table.add_column("Sources", justify="right")
            table.add_column("First Seen", style="dim")
            table.add_column("Status", style="magenta")

            for content in contents:
                # Truncate title for display
                title = content.normalized_title[:50] + "..." if len(content.normalized_title) > 50 else content.normalized_title
                first_seen = content.first_seen_at.strftime("%Y-%m-%d %H:%M") if content.first_seen_at else "N/A"
                status = content.status.value if content.status else "unknown"

                table.add_row(
                    content.content_id,
                    title,
                    str(content.source_count),
                    first_seen,
                    status,
                )

            console.print(table)

    except Exception as e:
        logger.error(f"Error listing content: {e}")
        console.print(f"[red]Error listing content: {e}[/red]")
        raise typer.Exit(1)
    finally:
        db.close()


@app.command("get")
def get_content(
    content_id: Optional[str] = typer.Argument(
        None, help="Content ID to retrieve"
    ),
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Filter content since this time (when no ID)"
    ),
    tier: Optional[str] = typer.Option(
        None, "--tier", "-t", help="Filter by source tier (when no ID)"
    ),
    format: str = typer.Option(
        "json", "--format", "-f", help="Output format (json, text)"
    ),
    limit: int = typer.Option(
        1, "--limit", "-l", help="Maximum number of results (when no ID)"
    ),
) -> None:
    """Get content by ID or filter.

    If content_id is provided, retrieve that specific content.
    Otherwise, list content matching filters.

    Examples:
        cyber-pulse content get cnt_20260319143052_a1b2c3d4
        cyber-pulse content get --since -1d --limit 10
        cyber-pulse content get cnt_123... --format text
    """
    db = SessionLocal()
    try:
        service = ContentService(db)

        if content_id:
            # Get specific content by ID
            content = service.get_content_by_id(content_id)

            if not content:
                console.print(f"[red]Content not found: {content_id}[/red]")
                raise typer.Exit(1)

            if format == "text":
                console.print(Panel(str(content.normalized_title), title=str(content.content_id), border_style="cyan"))
                console.print()
                console.print(content.normalized_body)
                console.print()
                console.print(f"[dim]First seen: {content.first_seen_at}[/dim]")
                console.print(f"[dim]Last seen: {content.last_seen_at}[/dim]")
                console.print(f"[dim]Source count: {content.source_count}[/dim]")
                console.print(f"[dim]Status: {content.status.value}[/dim]")
            else:
                output = {
                    "content_id": content.content_id,
                    "canonical_hash": content.canonical_hash,
                    "normalized_title": content.normalized_title,
                    "normalized_body": content.normalized_body,
                    "first_seen_at": content.first_seen_at.isoformat() if content.first_seen_at else None,
                    "last_seen_at": content.last_seen_at.isoformat() if content.last_seen_at else None,
                    "source_count": content.source_count,
                    "status": content.status.value if content.status else None,
                }
                console.print(json.dumps(output, indent=2))
        else:
            # List content matching filters
            since_dt = parse_datetime(since)

            if tier:
                console.print("[yellow]Warning: --tier filtering is not yet implemented[/yellow]")

            contents = service.get_contents(since=since_dt, limit=limit)

            if not contents:
                console.print("[yellow]No content found matching filters[/yellow]")
                return

            if format == "text":
                for content in contents:
                    console.print(Panel(str(content.normalized_title), title=str(content.content_id), border_style="cyan"))
                    console.print()
                    console.print(content.normalized_body[:500] + "..." if len(content.normalized_body) > 500 else content.normalized_body)
                    console.print()
                    console.print(f"[dim]{'─' * 60}[/dim]")
            else:
                output_list = [
                    {
                        "content_id": content.content_id,
                        "normalized_title": content.normalized_title,
                        "normalized_body": content.normalized_body,
                        "source_count": content.source_count,
                        "first_seen_at": content.first_seen_at.isoformat() if content.first_seen_at else None,
                        "status": content.status.value if content.status else None,
                    }
                    for content in contents
                ]
                console.print(json.dumps(output_list, indent=2))

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Error getting content: {e}")
        console.print(f"[red]Error getting content: {e}[/red]")
        raise typer.Exit(1)
    finally:
        db.close()


@app.command("stats")
def content_stats(
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format (table, json)"
    ),
) -> None:
    """Show content statistics.

    Displays:
    - Total number of unique content items
    - Total source references (sum of all source_count)

    Examples:
        cyber-pulse content stats
        cyber-pulse content stats --format json
    """
    db = SessionLocal()
    try:
        service = ContentService(db)
        stats = service.get_content_statistics()

        if format == "json":
            console.print(json.dumps(stats, indent=2))
        else:
            table = Table(title="Content Statistics", show_header=False)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green", justify="right")

            table.add_row("Total Contents", f"{stats['total_contents']:,}")
            table.add_row("Total Source References", f"{stats['total_source_references']:,}")

            if stats['total_contents'] > 0:
                avg_sources = stats['total_source_references'] / stats['total_contents']
                table.add_row("Avg Sources per Content", f"{avg_sources:.2f}")

            console.print(table)

    except Exception as e:
        logger.error(f"Error getting content statistics: {e}")
        console.print(f"[red]Error getting content statistics: {e}[/red]")
        raise typer.Exit(1)
    finally:
        db.close()