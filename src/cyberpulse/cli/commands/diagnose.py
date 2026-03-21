"""Diagnose command module."""
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...database import SessionLocal
from ...config import settings
from ...models import Source, SourceStatus, Item, ItemStatus

logger = logging.getLogger(__name__)
app = typer.Typer(
    name="diagnose",
    help="System diagnostics and health checks",
)

console = Console()


@app.command("system")
def diagnose_system() -> None:
    """Check system health.

    Performs comprehensive health checks on:
    - Database connectivity
    - Redis connectivity (for task queue)
    - API service health
    - Dramatiq task queue status
    - Configuration status
    """
    console.print(Panel("System Health Check", style="bold blue"))

    all_healthy = True

    # Check database
    console.print("\n[bold]Database:[/bold]")
    try:
        db = SessionLocal()
        db.execute(__import__('sqlalchemy').text("SELECT 1"))
        db.close()
        console.print("  [green]✓[/green] Database connection: [green]healthy[/green]")
        console.print(f"  [dim]URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}[/dim]")
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        console.print("  [red]✗[/red] Database connection: [red]unhealthy[/red]")
        console.print(f"  [dim]Error: {e}[/dim]")
        all_healthy = False

    # Check Redis
    console.print("\n[bold]Redis:[/bold]")
    try:
        import redis
        redis_url = settings.redis_url
        r = redis.from_url(redis_url)
        r.ping()
        console.print("  [green]✓[/green] Redis connection: [green]healthy[/green]")
        console.print(f"  [dim]URL: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}[/dim]")

        # Check Dramatiq broker Redis
        dramatiq_url = settings.dramatiq_broker_url
        if dramatiq_url != redis_url:
            r2 = redis.from_url(dramatiq_url)
            r2.ping()
            console.print("  [green]✓[/green] Dramatiq Redis: [green]healthy[/green]")
    except ImportError:
        console.print("  [yellow]![/yellow] Redis client not installed (pip install redis)")
    except Exception as e:
        console.print("  [red]✗[/red] Redis connection: [red]unhealthy[/red]")
        console.print(f"  [dim]Error: {e}[/dim]")
        all_healthy = False

    # Check configuration
    console.print("\n[bold]Configuration:[/bold]")
    console.print(f"  Log level: {settings.log_level}")
    console.print(f"  Log file: {settings.log_file or 'console only'}")
    console.print(f"  Scheduler enabled: {settings.scheduler_enabled}")

    # Check log file
    if settings.log_file:
        from pathlib import Path
        log_path = Path(settings.log_file)
        if log_path.exists():
            size = log_path.stat().st_size
            console.print(f"  Log file size: {format_size(size)}")
        else:
            console.print("  [yellow]Log file not yet created[/yellow]")

    # Check API service
    console.print("\n[bold]API Service:[/bold]")
    try:
        url = f"http://{settings.api_host}:{settings.api_port}/health"
        # Handle 0.0.0.0 binding
        if '0.0.0.0' in url:
            url = url.replace('0.0.0.0', '127.0.0.1')

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'healthy':
                console.print("  [green]✓[/green] API service: [green]healthy[/green]")
                console.print(f"  [dim]URL: {url}[/dim]")
            else:
                console.print("  [yellow]![/yellow] API service: [yellow]degraded[/yellow]")
                console.print(f"  [dim]Status: {data.get('status')}[/dim]")
    except urllib.error.URLError:
        console.print("  [yellow]![/yellow] API service: [yellow]not reachable[/yellow]")
        console.print("  [dim]This is normal if API is not running locally[/dim]")
    except json.JSONDecodeError as e:
        logger.warning(f"API health endpoint returned invalid JSON: {e}")
        console.print("  [yellow]![/yellow] API service: [yellow]invalid response[/yellow]")
        console.print("  [dim]Health endpoint returned invalid JSON[/dim]")
    except Exception as e:
        logger.error(f"API health check failed: {e}")
        console.print("  [yellow]![/yellow] API service: [yellow]not reachable[/yellow]")
        console.print(f"  [dim]{str(e)[:50]}[/dim]")

    # Check Dramatiq queue status
    console.print("\n[bold]Task Queue:[/bold]")
    try:
        import redis
        r = redis.from_url(settings.dramatiq_broker_url)
        # Check for pending messages in default queue
        queue_len = r.llen("dramatiq:default")  # type: ignore[attr-defined]
        console.print("  [green]✓[/green] Dramatiq Redis: [green]connected[/green]")
        console.print(f"  [dim]Pending tasks in default queue: {queue_len}[/dim]")
    except ImportError:
        console.print("  [yellow]![/yellow] Redis client not installed (pip install redis)")
    except Exception as e:
        logger.warning(f"Could not check queue status: {e}")
        console.print("  [yellow]![/yellow] Could not check queue status")

    # Summary
    console.print()
    if all_healthy:
        console.print(Panel("[green]All systems healthy[/green]", style="green"))
    else:
        console.print(Panel("[red]Some systems unhealthy[/red]", style="red"))
        raise typer.Exit(1)


@app.command("sources")
def diagnose_sources(
    pending: bool = typer.Option(
        False, "--pending", "-p", help="Only show sources pending review"
    ),
    tier: Optional[str] = typer.Option(
        None, "--tier", "-t", help="Filter by tier (T0, T1, T2, T3)"
    ),
) -> None:
    """Diagnose sources.

    Shows information about sources including:
    - Sources in observation period
    - Sources pending review
    - Inactive or frozen sources
    - Last fetch times
    """
    console.print(Panel("Source Diagnostics", style="bold blue"))

    db = SessionLocal()
    try:
        # Build query
        query = db.query(Source)

        if pending:
            query = query.filter(Source.pending_review.is_(True))
            console.print("\n[dim]Showing only sources pending review[/dim]")

        if tier:
            from ...models import SourceTier
            try:
                tier_enum = SourceTier(tier.upper())
                query = query.filter(Source.tier == tier_enum)
            except ValueError:
                console.print(f"[red]Invalid tier: {tier}. Must be T0, T1, T2, or T3.[/red]")
                raise typer.Exit(1)

        sources = query.all()

        if not sources:
            console.print("\n[dim]No sources found matching criteria.[/dim]")
            return

        # Summary statistics
        now = datetime.now(timezone.utc)
        total = len(sources)
        active = sum(1 for s in sources if s.status == SourceStatus.ACTIVE)
        frozen = sum(1 for s in sources if s.status == SourceStatus.FROZEN)
        removed = sum(1 for s in sources if s.status == SourceStatus.REMOVED)
        in_observation = sum(1 for s in sources if s.is_in_observation)
        pending_review = sum(1 for s in sources if s.pending_review)

        # Count stale sources (not fetched in 24 hours for active sources)
        stale_threshold = now - timedelta(hours=24)
        stale = sum(
            1 for s in sources
            if s.status == SourceStatus.ACTIVE
            and s.last_fetched_at
            and (
                s.last_fetched_at.replace(tzinfo=timezone.utc) if s.last_fetched_at.tzinfo is None else s.last_fetched_at
            ) < stale_threshold
        )
        never_fetched = sum(
            1 for s in sources
            if s.status == SourceStatus.ACTIVE and not s.last_fetched_at
        )

        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Total sources: {total}")
        console.print(f"  Active: [green]{active}[/green] | Frozen: [yellow]{frozen}[/yellow] | Removed: [dim]{removed}[/dim]")
        console.print(f"  In observation: {in_observation}")
        console.print(f"  Pending review: [yellow]{pending_review}[/yellow]")

        if stale > 0:
            console.print(f"  [yellow]Stale (24h+): {stale}[/yellow]")
        if never_fetched > 0:
            console.print(f"  [yellow]Never fetched: {never_fetched}[/yellow]")

        # Sources needing attention
        attention_sources = [
            s for s in sources
            if s.pending_review or s.status == SourceStatus.FROZEN
        ]

        if attention_sources:
            console.print(f"\n[bold yellow]Sources Needing Attention ({len(attention_sources)}):[/bold yellow]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("ID", style="dim")
            table.add_column("Name")
            table.add_column("Tier")
            table.add_column("Score")
            table.add_column("Status")
            table.add_column("Reason")

            for s in attention_sources[:20]:  # Limit to 20
                reason = s.review_reason or ("Frozen" if s.status == SourceStatus.FROZEN else "Pending review")
                table.add_row(
                    s.source_id,
                    s.name[:30],
                    s.tier.value,
                    f"{s.score:.1f}",
                    f"[yellow]{s.status.value}[/yellow]",
                    reason[:40] if reason else "-"
                )

            console.print(table)
            if len(attention_sources) > 20:
                console.print(f"[dim]... and {len(attention_sources) - 20} more[/dim]")

        # Observation period ending soon
        ending_soon = [
            s for s in sources
            if s.is_in_observation
            and s.observation_until
            and (
                s.observation_until.replace(tzinfo=timezone.utc) if s.observation_until.tzinfo is None else s.observation_until
            ) < now + timedelta(days=7)
        ]

        if ending_soon:
            console.print(f"\n[bold]Observation Period Ending Soon ({len(ending_soon)}):[/bold]")
            obs_table = Table(show_header=True, header_style="bold")
            obs_table.add_column("Name")
            obs_table.add_column("Ends At")
            obs_table.add_column("Items")
            obs_table.add_column("Score")

            for s in sorted(ending_soon, key=lambda x: x.observation_until or now)[:10]:
                ends = s.observation_until.strftime("%Y-%m-%d") if s.observation_until else "-"
                obs_table.add_row(
                    s.name[:30],
                    ends,
                    str(s.total_items),
                    f"{s.score:.1f}"
                )

            console.print(obs_table)

        # Recent collection activity
        active_sources = [
            s for s in sources
            if s.status == SourceStatus.ACTIVE
        ]

        if active_sources:
            console.print("\n[bold]Recent Collection Activity:[/bold]")
            collection_table = Table(show_header=True, header_style="bold")
            collection_table.add_column("Source")
            collection_table.add_column("Last Collected")
            collection_table.add_column("Items")
            collection_table.add_column("Status")

            # Sort by last_fetched_at, most recent first
            def get_sort_key(x):
                if x.last_fetched_at is None:
                    return datetime.min.replace(tzinfo=timezone.utc)
                if x.last_fetched_at.tzinfo is None:
                    return x.last_fetched_at.replace(tzinfo=timezone.utc)
                return x.last_fetched_at

            sorted_sources = sorted(
                active_sources,
                key=get_sort_key,
                reverse=True
            )

            for s in sorted_sources[:15]:  # Show top 15
                if s.last_fetched_at:
                    # Ensure timezone-aware comparison
                    fetched_at = s.last_fetched_at.replace(tzinfo=timezone.utc) if s.last_fetched_at.tzinfo is None else s.last_fetched_at
                    age = now - fetched_at
                    if age < timedelta(hours=1):
                        status = "[green]Fresh[/green]"
                    elif age < timedelta(hours=24):
                        status = "[yellow]Recent[/yellow]"
                    else:
                        status = "[red]Stale[/red]"
                    collected = s.last_fetched_at.strftime("%Y-%m-%d %H:%M")
                else:
                    status = "[dim]Never[/dim]"
                    collected = "-"

                collection_table.add_row(
                    s.name[:25],
                    collected,
                    str(s.total_items or 0),
                    status
                )

            console.print(collection_table)

    finally:
        db.close()


@app.command("errors")
def diagnose_errors(
    since: Optional[str] = typer.Option(
        None, "--since", "-s", help="Analyze errors since time (e.g., '1h', '24h', '7d')"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", help="Filter by source ID"
    ),
) -> None:
    """Analyze errors from logs and database.

    Shows:
    - Items in rejected state (with rejection reason from raw_metadata)
    - Recent errors from the log file
    """
    console.print(Panel("Error Analysis", style="bold blue"))

    # Parse since parameter
    since_dt = None
    if since:
        since_dt = parse_time_delta(since)
        if since_dt is None:
            console.print(f"[red]Invalid time format: {since}[/red]")
            console.print("[dim]Use format like '1h', '24h', '7d', '30m'[/dim]")
            raise typer.Exit(1)

    # Check rejected items
    console.print("\n[bold]Rejected Items:[/bold]")
    db = SessionLocal()
    try:
        query = db.query(Item).filter(Item.status == ItemStatus.REJECTED)

        if source:
            query = query.filter(Item.source_id == source)

        if since_dt:
            query = query.filter(Item.fetched_at >= since_dt)

        rejected_items = query.order_by(Item.fetched_at.desc()).limit(20).all()

        if rejected_items:
            console.print(f"  Found {query.count()} rejected items")

            table = Table(show_header=True, header_style="bold")
            table.add_column("Item ID", style="dim")
            table.add_column("Source")
            table.add_column("Title")
            table.add_column("Rejection Reason")
            table.add_column("Fetched")

            for item in rejected_items[:10]:
                # Extract rejection reason from raw_metadata
                raw_meta = item.raw_metadata or {}  # type: ignore[var-annotated]
                reason_raw = raw_meta.get("rejection_reason", "-")
                # Ensure reason is a string (handle non-string types safely)
                reason = str(reason_raw) if reason_raw is not None else "-"
                if len(reason) > 40:
                    reason = reason[:37] + "..."

                table.add_row(
                    item.item_id,
                    item.source_id,
                    (item.title or "")[:30],
                    reason,
                    item.fetched_at.strftime("%Y-%m-%d %H:%M") if item.fetched_at else "-"
                )

            console.print(table)
        else:
            console.print("  [green]No rejected items found[/green]")
    finally:
        db.close()

    # Check for errors in log file
    console.print("\n[bold]Recent Errors from Logs:[/bold]")
    from pathlib import Path

    log_path = Path(settings.log_file) if settings.log_file else Path("logs/cyberpulse.log")

    if log_path.exists():
        try:
            import re
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Find ERROR and CRITICAL lines
            error_pattern = r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - (ERROR|CRITICAL) - (.+)$'
            errors = []
            for match in re.finditer(error_pattern, content, re.MULTILINE):
                timestamp_str, logger_name, level, message = match.groups()
                try:
                    log_dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    if since_dt and log_dt < since_dt:
                        continue
                except ValueError:
                    pass  # Skip entries with invalid timestamps
                errors.append({
                    'timestamp': timestamp_str,
                    'logger': logger_name,
                    'level': level,
                    'message': message
                })

            if errors:
                # Show last 10 errors
                console.print(f"  Found {len(errors)} error entries")
                for err in errors[-10:]:
                    color = 'red bold' if err['level'] == 'CRITICAL' else 'red'
                    console.print(f"  [{color}]{err['level']}[/{color}] [dim]{err['timestamp']}[/dim] {err['message'][:80]}")
            else:
                console.print("  [green]No errors found in logs[/green]")
        except OSError as e:
            logger.warning(f"Could not read log file: {e}")
            console.print(f"  [yellow]Could not read log file: {e}[/yellow]")
    else:
        console.print("  [dim]Log file not found[/dim]")

    # Summary
    console.print("\n[bold]Recommendations:[/bold]")
    console.print("  • Check rejected items for quality issues")
    console.print("  • Review sources with pending_review=True")
    console.print("  • Use 'cyber-pulse log errors' for detailed error logs")


def parse_time_delta(time_str: str) -> Optional[datetime]:
    """Parse a time delta string like '1h', '24h', '7d'.

    Args:
        time_str: Time delta string

    Returns:
        Datetime that many units ago, or None if parsing fails
    """
    import re
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


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"