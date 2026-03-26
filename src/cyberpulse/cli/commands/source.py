"""Source command module for managing intelligence sources."""

import asyncio
import json
import logging
import typer
from pathlib import Path
from typing import Optional, List, Dict, Any
from xml.etree import ElementTree

import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...database import SessionLocal
from ...services import (
    SourceService,
    SourceScoreService,
    get_connector,
    ConnectorError,
    CONNECTOR_REGISTRY,
)
from ...models import Source, SourceTier, SourceStatus

logger = logging.getLogger(__name__)
app = typer.Typer(name="source", help="Manage intelligence sources")
console = Console()


def _looks_like_feed_url(url: str) -> bool:
    """Check if URL looks like an RSS feed URL.

    Args:
        url: URL to check

    Returns:
        True if URL appears to be a feed URL
    """
    feed_patterns = ["/feed", "/rss", ".xml", ".rss", "/atom"]
    return any(p in url.lower() for p in feed_patterns)


async def _discover_rss_for_cli(site_url: str) -> Optional[str]:
    """Discover RSS URL for a site (CLI helper).

    Args:
        site_url: Site URL to discover RSS from

    Returns:
        Discovered RSS URL or None
    """
    from ...services.rss_discovery import RSSDiscoveryService
    discovery = RSSDiscoveryService()
    return await discovery.discover(site_url)


def _get_tier_color(tier: str) -> str:
    """Get color for tier display."""
    colors = {
        "T0": "red",
        "T1": "yellow",
        "T2": "green",
        "T3": "dim",
    }
    return colors.get(tier, "white")


def _get_status_color(status: str) -> str:
    """Get color for status display."""
    colors = {
        "ACTIVE": "green",
        "FROZEN": "yellow",
        "REMOVED": "red",
    }
    return colors.get(status, "white")


def _validate_source_id(source_id: str) -> bool:
    """Validate source ID format."""
    import re
    return bool(re.match(r"^src_[a-f0-9]{8}$", source_id))


@app.command("list")
def list_sources(
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Filter by tier (T0, T1, T2, T3)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (ACTIVE, FROZEN, REMOVED)"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of results"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, yaml, json)"),
) -> None:
    """List all sources with optional filtering.

    Use --format yaml or --format json for machine-readable output.
    """
    # Validate and convert filters
    tier_filter = None
    if tier:
        try:
            tier_filter = SourceTier(tier.upper())
        except ValueError:
            console.print(f"[red]Invalid tier: {tier}. Must be one of: T0, T1, T2, T3[/red]")
            raise typer.Exit(1)

    status_filter = None
    if status:
        try:
            status_filter = SourceStatus(status.upper())
        except ValueError:
            console.print(f"[red]Invalid status: {status}. Must be one of: ACTIVE, FROZEN, REMOVED[/red]")
            raise typer.Exit(1)

    db = SessionLocal()
    try:
        service = SourceService(db)
        sources = service.list_sources(tier=tier_filter, status=status_filter, limit=limit)

        if not sources:
            console.print("[yellow]No sources found.[/yellow]")
            return

        # Output based on format
        if format == "yaml":
            sources_data = [
                {
                    "id": s.source_id,
                    "name": s.name,
                    "type": s.connector_type,
                    "tier": s.tier.value,
                    "score": s.score,
                    "status": s.status.value,
                    "config": s.config,
                }
                for s in sources
            ]
            console.print(yaml.dump({"sources": sources_data}, default_flow_style=False, sort_keys=False))

        elif format == "json":
            sources_data = [
                {
                    "id": s.source_id,
                    "name": s.name,
                    "type": s.connector_type,
                    "tier": s.tier.value,
                    "score": s.score,
                    "status": s.status.value,
                    "config": s.config,
                }
                for s in sources
            ]
            console.print(json.dumps({"sources": sources_data}, indent=2, ensure_ascii=False))

        else:
            # Table format (default)
            table = Table(title=f"Sources ({len(sources)} found)")
            table.add_column("ID", style="dim", width=12)
            table.add_column("Name", style="cyan")
            table.add_column("Type", width=10)
            table.add_column("Tier", width=6)
            table.add_column("Score", width=6)
            table.add_column("Status", width=8)
            table.add_column("Items", width=6)
            table.add_column("Observation", width=10)

            for source in sources:
                tier_color = _get_tier_color(source.tier.value)
                status_color = _get_status_color(source.status.value)

                observation_status = "Yes" if source.is_in_observation is True else "No"
                if source.is_in_observation is True and source.observation_until is not None:
                    observation_status = f"Until {source.observation_until.strftime('%Y-%m-%d')}"

                table.add_row(
                    source.source_id,  # type: ignore[arg-type]
                    source.name,  # type: ignore[arg-type]
                    source.connector_type,  # type: ignore[arg-type]
                    f"[{tier_color}]{source.tier.value}[/{tier_color}]",
                    f"{source.score:.1f}",
                    f"[{status_color}]{source.status.value}[/{status_color}]",
                    str(source.total_items),
                    observation_status,
                )

            console.print(table)

    finally:
        db.close()


@app.command("add")
def add_source(
    name: str = typer.Argument(..., help="Source name"),
    connector: str = typer.Argument(..., help="Connector type (rss, api, web, media)"),
    url: str = typer.Argument(..., help="Source URL or feed URL"),
    tier: str = typer.Option("T2", "--tier", "-t", help="Initial tier (T0, T1, T2, T3)"),
    test: bool = typer.Option(True, "--test/--no-test", help="Run onboarding flow"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """
    Add a new source with full onboarding flow.

    Onboarding Flow (per Spec 4.1.2):
    1. [Duplicate Check] - Check if name or URL already exists
    2. [Connection Test] - Can we reach the source?
    3. [First Collection] - Fetch 5-10 sample items
    4. [Quality Assessment] - Evaluate samples
    5. [Auto-tiering] - Set tier based on quality
    6. [Schedule] - Add to APScheduler for periodic collection
    """
    # Validate connector type
    if connector not in CONNECTOR_REGISTRY:
        console.print(f"[red]Invalid connector type: {connector}[/red]")
        console.print(f"[yellow]Available types: {', '.join(CONNECTOR_REGISTRY.keys())}[/yellow]")
        raise typer.Exit(1)

    # Validate tier
    try:
        source_tier = SourceTier(tier.upper())
    except ValueError:
        console.print(f"[red]Invalid tier: {tier}. Must be one of: T0, T1, T2, T3[/red]")
        raise typer.Exit(1)

    db = SessionLocal()
    try:
        service = SourceService(db)

        # Step 1: Duplicate Check
        console.print("\n[bold]Step 1: Checking for duplicates...[/bold]")
        existing = db.query(Source).filter(Source.name == name).first()
        if existing:
            console.print(f"[red]Source with name '{name}' already exists (ID: {existing.source_id})[/red]")
            raise typer.Exit(1)

        # Check for duplicate URL in config
        existing_url = db.query(Source).filter(Source.config["url"].as_string() == url).first()
        if existing_url:
            console.print(f"[yellow]Warning: Source with URL '{url}' already exists (ID: {existing_url.source_id})[/yellow]")
            if not (yes or typer.confirm("Continue anyway?")):
                raise typer.Exit(0)

        console.print("[green]No duplicates found.[/green]")

        # Prepare config based on connector type
        config: dict = {}
        if connector == "rss":
            # Check if URL looks like a feed URL or site URL
            if _looks_like_feed_url(url):
                config = {"feed_url": url}
            else:
                # Try to discover RSS from site URL
                console.print(f"[cyan]Discovering RSS feed from {url}...[/cyan]")
                feed_url = asyncio.run(_discover_rss_for_cli(url))
                if feed_url:
                    config = {"feed_url": feed_url}
                    console.print(f"[green]Found RSS: {feed_url}[/green]")
                else:
                    console.print("[yellow]Could not discover RSS, using URL as feed_url[/yellow]")
                    config = {"feed_url": url}
        elif connector == "api":
            config = {"url": url}
        elif connector == "web":
            config = {"url": url}
        elif connector == "media":
            config = {"url": url}

        if test:
            # Step 2: Connection Test
            console.print("\n[bold]Step 2: Testing connection...[/bold]")
            try:
                connector_instance = get_connector(connector, config)
                connector_instance.validate_config()

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    progress.add_task("Fetching sample items...", total=None)
                    items = asyncio.run(connector_instance.fetch())

                if items:
                    console.print(f"[green]Connection successful! Found {len(items)} items.[/green]")

                    # Step 3: First Collection Summary
                    console.print(f"\n[bold]Step 3: Sample Items ({min(5, len(items))} of {len(items)}):[/bold]")
                    for i, item in enumerate(items[:5]):
                        title = item.get("title", "No title")[:50]
                        console.print(f"  {i + 1}. {title}")

                    # Step 4: Quality Assessment
                    console.print("\n[bold]Step 4: Quality Assessment...[/bold]")
                    quality_score = _assess_sample_quality(items)
                    console.print(f"  Sample quality score: {quality_score:.1f}/100")

                    # Step 5: Auto-tiering suggestion
                    suggested_tier = _get_tier_for_score(quality_score)
                    console.print(f"  Suggested tier: {suggested_tier.value}")

                    if suggested_tier != source_tier:
                        console.print(f"[yellow]Note: Selected tier ({source_tier.value}) differs from suggested ({suggested_tier.value})[/yellow]")
                        if yes or typer.confirm(f"Use suggested tier {suggested_tier.value} instead?"):
                            source_tier = suggested_tier

                else:
                    console.print("[yellow]Warning: No items found at source URL.[/yellow]")
                    if not (yes or typer.confirm("Add source anyway?")):
                        raise typer.Exit(0)

            except ConnectorError as e:
                console.print(f"[red]Connection failed: {e}[/red]")
                if not (yes or typer.confirm("Add source anyway (will need manual fix)?")):
                    raise typer.Exit(0)
            except ValueError as e:
                console.print(f"[red]Configuration error: {e}[/red]")
                raise typer.Exit(1)

        # Create the source
        console.print("\n[bold]Creating source...[/bold]")
        source, message = service.add_source(
            name=name,
            connector_type=connector,
            tier=source_tier,
            config=config,
        )

        if source:
            console.print(f"[green]{message}[/green]")

            # Display source info
            info_panel = Panel(
                f"[bold]ID:[/bold] {source.source_id}\n"
                f"[bold]Name:[/bold] {source.name}\n"
                f"[bold]Type:[/bold] {source.connector_type}\n"
                f"[bold]Tier:[/bold] {source.tier.value}\n"
                f"[bold]Score:[/bold] {source.score:.1f}\n"
                f"[bold]Status:[/bold] {source.status.value}\n"
                f"[bold]Observation:[/bold] {source.observation_until.strftime('%Y-%m-%d') if source.observation_until is not None else 'N/A'}",
                title="Source Created",
                border_style="green",
            )
            console.print(info_panel)

            # Step 6: Schedule (placeholder for APScheduler integration)
            console.print("\n[bold]Step 6: Scheduling...[/bold]")
            console.print("[yellow]Note: Automatic scheduling requires APScheduler integration (Phase 2D)[/yellow]")

        else:
            console.print(f"[red]Failed to create source: {message}[/red]")
            raise typer.Exit(1)

    finally:
        db.close()


def _assess_sample_quality(items: List[dict]) -> float:
    """Assess quality of sample items."""
    if not items:
        return 0.0

    total_score = 0.0

    for item in items:
        item_score = 0.0

        # Title presence (25 points)
        title = item.get("title", "")
        if title:
            item_score += 25

        # Content presence (35 points)
        content = item.get("content", "")
        if content:
            # Full points for content > 100 chars, partial for shorter
            content_score = min(35, len(content) / 100 * 35)
            item_score += content_score

        # URL presence (15 points)
        url = item.get("url", "")
        if url:
            item_score += 15

        # Published date (15 points)
        published_at = item.get("published_at")
        if published_at:
            item_score += 15

        # Author/tags (10 points bonus)
        if item.get("author") or item.get("tags"):
            item_score += 10

        total_score += item_score

    return total_score / len(items)


def _get_tier_for_score(score: float) -> SourceTier:
    """Determine tier based on score."""
    if score >= 80:
        return SourceTier.T0
    elif score >= 60:
        return SourceTier.T1
    elif score >= 40:
        return SourceTier.T2
    else:
        return SourceTier.T3


@app.command("update")
def update_source(
    source_id: str = typer.Argument(..., help="Source ID to update"),
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="New tier (T0, T1, T2, T3)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status (ACTIVE, FROZEN)"),
    full_fetch: Optional[bool] = typer.Option(None, "--full-fetch", help="Enable/disable full content fetch"),
    fetch_threshold: Optional[float] = typer.Option(None, "--fetch-threshold", help="Content quality threshold for full fetch (0.0-1.0)"),
) -> None:
    """Update a source's tier, status, or full content fetch settings."""
    # Validate source ID format
    if not _validate_source_id(source_id):
        console.print(f"[red]Invalid source ID format: {source_id}[/red]")
        console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
        raise typer.Exit(1)

    if not tier and not status and full_fetch is None and fetch_threshold is None:
        console.print("[yellow]No updates specified. Use --tier, --status, --full-fetch, or --fetch-threshold options.[/yellow]")
        raise typer.Exit(0)

    db = SessionLocal()
    try:
        service = SourceService(db)

        # Build update kwargs
        kwargs = {}
        if tier:
            try:
                kwargs["tier"] = tier.upper()
            except ValueError:
                console.print(f"[red]Invalid tier: {tier}[/red]")
                raise typer.Exit(1)
        if status:
            try:
                kwargs["status"] = status.upper()
            except ValueError:
                console.print(f"[red]Invalid status: {status}[/red]")
                raise typer.Exit(1)

        # Handle full fetch settings
        if full_fetch is not None or fetch_threshold is not None:
            # Get current source to update config
            source = db.query(Source).filter(Source.source_id == source_id).first()
            if not source:
                console.print(f"[red]Source not found: {source_id}[/red]")
                raise typer.Exit(1)

            config = source.config or {}
            if full_fetch is not None:
                config["needs_full_fetch"] = full_fetch
            if fetch_threshold is not None:
                if not 0.0 <= fetch_threshold <= 1.0:
                    console.print(f"[red]Fetch threshold must be between 0.0 and 1.0[/red]")
                    raise typer.Exit(1)
                config["full_fetch_threshold"] = fetch_threshold
            kwargs["config"] = config

        source, message = service.update_source(source_id, **kwargs)

        if source:
            console.print(f"[green]{message}[/green]")
            console.print(f"  Tier: {source.tier.value}")
            console.print(f"  Score: {source.score:.1f}")
            console.print(f"  Status: {source.status.value}")
            if source.config:
                if source.config.get("needs_full_fetch"):
                    console.print(f"  Full fetch: enabled (threshold: {source.config.get('full_fetch_threshold', 0.7)})")
                else:
                    console.print(f"  Full fetch: disabled")
        else:
            console.print(f"[red]{message}[/red]")
            raise typer.Exit(1)

    finally:
        db.close()


@app.command("remove")
def remove_source(
    source_id: str = typer.Argument(..., help="Source ID to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove a source (soft delete)."""
    # Validate source ID format
    if not _validate_source_id(source_id):
        console.print(f"[red]Invalid source ID format: {source_id}[/red]")
        console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
        raise typer.Exit(1)

    db = SessionLocal()
    try:
        service = SourceService(db)

        # Get source info first
        stats = service.get_source_statistics(source_id)
        if not stats:
            console.print(f"[red]Source not found: {source_id}[/red]")
            raise typer.Exit(1)

        if stats["status"] == "REMOVED":
            console.print(f"[yellow]Source '{stats['name']}' is already removed.[/yellow]")
            return

        # Confirm removal
        if not force:
            console.print("[yellow]About to remove source:[/yellow]")
            console.print(f"  Name: {stats['name']}")
            console.print(f"  Tier: {stats['tier']}")
            console.print(f"  Items: {stats['total_items']}")
            if not typer.confirm("Continue?"):
                raise typer.Exit(0)

        success, message = service.remove_source(source_id)

        if success:
            console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[red]{message}[/red]")
            raise typer.Exit(1)

    finally:
        db.close()


@app.command("test")
def test_source(
    source_id: str = typer.Argument(..., help="Source ID to test"),
) -> None:
    """Test source connectivity and quality."""
    # Validate source ID format
    if not _validate_source_id(source_id):
        console.print(f"[red]Invalid source ID format: {source_id}[/red]")
        console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
        raise typer.Exit(1)

    db = SessionLocal()
    try:
        score_service = SourceScoreService(db)

        # Get source
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            console.print(f"[red]Source not found: {source_id}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Testing source: {source.name}[/bold]")
        console.print(f"  ID: {source.source_id}")
        console.print(f"  Type: {source.connector_type}")
        console.print(f"  Current tier: {source.tier.value}")
        console.print(f"  Current score: {source.score:.1f}")

        # Test 1: Connection
        console.print("\n[bold]1. Connection Test...[/bold]")
        try:
            # SQLAlchemy Column attributes resolve to actual types at runtime
            connector = get_connector(source.connector_type, source.config)  # type: ignore[arg-type]
            connector.validate_config()
            console.print("   [green]Configuration valid[/green]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("   Fetching items...", total=None)
                items = asyncio.run(connector.fetch())

            console.print(f"   [green]Connection successful! Found {len(items)} items.[/green]")

        except ConnectorError as e:
            console.print(f"   [red]Connection failed: {e}[/red]")
            raise typer.Exit(1)
        except ValueError as e:
            console.print(f"   [red]Configuration error: {e}[/red]")
            raise typer.Exit(1)

        # Test 2: Quality Assessment
        console.print("\n[bold]2. Quality Assessment...[/bold]")
        try:
            components = score_service.get_score_components(source_id)
            console.print(f"   Stability: {components.stability:.2f}")
            console.print(f"   Activity: {components.activity:.2f}")
            console.print(f"   Quality: {components.quality:.2f}")
            console.print(f"   Strategic Value: {components.strategic_value:.2f}")

            # Calculate score
            score = score_service.calculate_score(source_id)
            console.print(f"   [bold]Calculated Score: {score:.1f}[/bold]")

            # Check tier evolution
            evolution = score_service.check_tier_evolution(source_id)
            if evolution["action"] == "promote":
                console.print(f"   [green]Recommendation: Promote to {evolution['recommended_tier']}[/green]")
            elif evolution["action"] == "demote":
                console.print(f"   [yellow]Recommendation: Demote to {evolution['recommended_tier']}[/yellow]")
            else:
                console.print("   [green]Tier is consistent with score[/green]")

        except ValueError as e:
            logger.debug(f"Quality assessment error: {e}")
            console.print(f"   [yellow]Quality assessment skipped: {e}[/yellow]")

        # Test 3: Sample Items
        if items:
            console.print(f"\n[bold]3. Sample Items ({min(3, len(items))} of {len(items)}):[/bold]")
            for i, item in enumerate(items[:3]):
                title = item.get("title", "No title")[:60]
                console.print(f"   {i + 1}. {title}")

        console.print("\n[green]Test completed successfully.[/green]")

    finally:
        db.close()


@app.command("stats")
def source_stats(
    source_id: Optional[str] = typer.Argument(None, help="Source ID (optional, shows all if omitted)"),
) -> None:
    """Show source statistics."""
    db = SessionLocal()
    try:
        service = SourceService(db)
        score_service = SourceScoreService(db)

        if source_id:
            # Validate source ID format
            if not _validate_source_id(source_id):
                console.print(f"[red]Invalid source ID format: {source_id}[/red]")
                console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
                raise typer.Exit(1)

            stats = service.get_source_statistics(source_id)
            if not stats:
                console.print(f"[red]Source not found: {source_id}[/red]")
                raise typer.Exit(1)

            # Get score components
            try:
                components = score_service.get_score_components(source_id)
            except ValueError as e:
                logger.debug(f"Could not get score components: {e}")
                components = None

            tier_color = _get_tier_color(stats["tier"])
            status_color = _get_status_color(stats["status"])

            # Create info panel
            info_text = (
                f"[bold]Name:[/bold] {stats['name']}\n"
                f"[bold]ID:[/bold] {stats['source_id']}\n"
                f"[bold]Type:[/bold] {stats['tier']}\n"
                f"[bold]Tier:[/bold] [{tier_color}]{stats['tier']}[/{tier_color}]\n"
                f"[bold]Score:[/bold] {stats['score']:.1f}\n"
                f"[bold]Status:[/bold] [{status_color}]{stats['status']}[/{status_color}]\n"
                f"[bold]Items:[/bold] {stats['total_items']}\n"
                f"[bold]Contents:[/bold] {stats['total_contents']}\n"
            )

            if stats["is_in_observation"]:
                info_text += f"[bold]Observation:[/bold] Until {stats['observation_until'][:10]}\n"

            if components:
                info_text += (
                    f"\n[bold]Score Components:[/bold]\n"
                    f"  Stability: {components.stability:.2f}\n"
                    f"  Activity: {components.activity:.2f}\n"
                    f"  Quality: {components.quality:.2f}\n"
                )

            console.print(Panel(info_text, title=f"Source: {stats['name']}", border_style="cyan"))

        else:
            # Show aggregate statistics
            sources = service.list_sources(limit=1000)

            if not sources:
                console.print("[yellow]No sources found.[/yellow]")
                return

            # Count by tier
            tier_counts = {"T0": 0, "T1": 0, "T2": 0, "T3": 0}
            status_counts = {"ACTIVE": 0, "FROZEN": 0, "REMOVED": 0}
            total_items = 0
            total_contents = 0
            observation_count = 0

            for source in sources:
                tier_counts[source.tier.value] += 1
                status_counts[source.status.value] += 1
                # SQLAlchemy Column attributes resolve to actual types at runtime
                total_items += source.total_items  # type: ignore[assignment]
                total_contents += source.total_contents  # type: ignore[assignment]
                if source.is_in_observation is True:
                    observation_count += 1

            # Summary table
            table = Table(title="Source Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Sources", str(len(sources)))
            table.add_row("Active", str(status_counts["ACTIVE"]))
            table.add_row("Frozen", str(status_counts["FROZEN"]))
            table.add_row("Removed", str(status_counts["REMOVED"]))
            table.add_row("In Observation", str(observation_count))
            table.add_row("Total Items", str(total_items))
            table.add_row("Total Contents", str(total_contents))

            console.print(table)

            # Tier distribution
            tier_table = Table(title="Tier Distribution")
            tier_table.add_column("Tier", style="cyan")
            tier_table.add_column("Count", style="green")
            tier_table.add_column("Percentage", style="yellow")

            for tier in ["T0", "T1", "T2", "T3"]:
                count = tier_counts[tier]
                pct = count / len(sources) * 100 if sources else 0
                tier_color = _get_tier_color(tier)
                tier_table.add_row(
                    f"[{tier_color}]{tier}[/{tier_color}]",
                    str(count),
                    f"{pct:.1f}%"
                )

            console.print(tier_table)

    finally:
        db.close()


# =============================================================================
# Import/Export Commands
# =============================================================================


def _detect_format(file_path: Path) -> str:
    """Detect file format from extension or content.

    Args:
        file_path: Path to the file

    Returns:
        Format string: 'opml', 'yaml', or 'unknown'
    """
    # Check extension first
    suffix = file_path.suffix.lower()
    if suffix == ".opml":
        return "opml"
    elif suffix in (".yaml", ".yml"):
        return "yaml"

    # Try to detect from content
    try:
        content = file_path.read_text(encoding="utf-8")
        content_stripped = content.strip()

        if content_stripped.startswith("<?xml") or content_stripped.startswith("<opml"):
            return "opml"
        elif content_stripped.startswith("---") or content_stripped.startswith("sources:"):
            return "yaml"

        # Try parsing as YAML
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "sources" in data:
                return "yaml"
        except yaml.YAMLError:
            pass

        # Try parsing as OPML
        try:
            root = ElementTree.fromstring(content)
            if root.tag == "opml" or root.find(".//outline") is not None:
                return "opml"
        except ElementTree.ParseError:
            pass

    except Exception as e:
        logger.debug(f"Error detecting format: {e}")

    return "unknown"


def _parse_opml(file_path: Path) -> List[Dict[str, Any]]:
    """Parse OPML file and extract RSS sources.

    Args:
        file_path: Path to OPML file

    Returns:
        List of source dictionaries

    Raises:
        ValueError: If file cannot be parsed
    """
    sources = []

    try:
        tree = ElementTree.parse(file_path)
        root = tree.getroot()

        # Find all outline elements
        outlines = root.findall(".//outline")

        for outline in outlines:
            # Get attributes
            title = outline.get("title") or outline.get("text", "")
            feed_url = outline.get("xmlUrl") or outline.get("htmlUrl", "")

            # Skip category outlines (no feed URL)
            if not feed_url:
                continue

            # Create source dict
            source: Dict[str, Any] = {
                "name": title,
                "connector_type": "rss",
                "config": {"feed_url": feed_url},
                "tier": outline.get("cyberpulse_tier", "T2"),
            }

            # Optional fields
            score_value = outline.get("cyberpulse_score")
            if score_value:
                try:
                    source["score"] = float(score_value)
                except ValueError:
                    pass

            sources.append(source)

    except ElementTree.ParseError as e:
        raise ValueError(f"Failed to parse OPML file: {e}") from e

    return sources


def _parse_yaml(file_path: Path) -> List[Dict[str, Any]]:
    """Parse YAML file and extract sources.

    Args:
        file_path: Path to YAML file

    Returns:
        List of source dictionaries

    Raises:
        ValueError: If file cannot be parsed
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise ValueError("YAML file must contain a dictionary")

        if "sources" not in data:
            raise ValueError("YAML file must have 'sources' key")

        sources = data.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("'sources' must be a list")

        return sources

    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML file: {e}") from e


def _export_to_opml(sources: List[Source], output_path: Path) -> None:
    """Export sources to OPML format.

    Note: OPML only supports RSS sources with basic information.

    Args:
        sources: List of Source objects
        output_path: Output file path
    """
    # Create OPML structure
    opml = ElementTree.Element("opml", version="2.0")
    head = ElementTree.SubElement(opml, "head")
    title = ElementTree.SubElement(head, "title")
    title.text = "CyberPulse Sources Export"

    body = ElementTree.SubElement(opml, "body")

    # Group by tier
    tier_groups: Dict[str, List[Source]] = {"T0": [], "T1": [], "T2": [], "T3": []}
    for source in sources:
        if source.connector_type == "rss" and source.status != SourceStatus.REMOVED:  # type: ignore[comparison-overlap]
            tier_groups[source.tier.value].append(source)  # type: ignore[union-attr]

    # Create outline for each tier
    for tier, tier_sources in tier_groups.items():
        if not tier_sources:
            continue

        tier_outline = ElementTree.SubElement(body, "outline", text=f"Tier {tier}")

        for source in tier_sources:
            attrs = {
                "text": source.name,
                "title": source.name,
                "type": "rss",
                "xmlUrl": source.config.get("feed_url", ""),
            }

            # Add custom attributes for CyberPulse
            attrs["cyberpulse_tier"] = source.tier.value
            attrs["cyberpulse_score"] = str(source.score)

            ElementTree.SubElement(tier_outline, "outline", **attrs)

    # Write to file
    tree = ElementTree.ElementTree(opml)
    ElementTree.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _export_to_yaml(sources: List[Source], output_path: Path) -> None:
    """Export sources to YAML format.

    Supports all source types with complete configuration.

    Args:
        sources: List of Source objects
        output_path: Output file path
    """
    sources_data = []

    for source in sources:
        if source.status == SourceStatus.REMOVED:  # type: ignore[comparison-overlap]
            continue

        source_dict = {
            "name": source.name,
            "connector_type": source.connector_type,
            "tier": source.tier.value,
            "score": source.score,
            "config": source.config,
        }

        # Add optional fields if they differ from defaults
        if source.fetch_interval is not None and source.fetch_interval > 0:  # type: ignore[operator]
            source_dict["fetch_interval"] = source.fetch_interval

        sources_data.append(source_dict)

    output = {
        "sources": sources_data,
        "_meta": {
            "exported_by": "cyber-pulse",
            "format_version": "1.0",
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


@app.command("import")
def import_sources(
    file_path: Path = typer.Argument(..., help="Path to import file (OPML or YAML)"),
    format: Optional[str] = typer.Option(None, "--format", "-f", help="Force format (opml, yaml)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview import without making changes"),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip-existing", help="Skip existing sources"),
) -> None:
    """
    Import sources from OPML or YAML file.

    Supports automatic format detection or explicit --format option.
    Use --dry-run to preview the import without making changes.
    """
    # Check file exists
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    # Detect or use specified format
    if format:
        file_format = format.lower()
        if file_format not in ("opml", "yaml"):
            console.print(f"[red]Invalid format: {format}. Must be 'opml' or 'yaml'[/red]")
            raise typer.Exit(1)
    else:
        file_format = _detect_format(file_path)
        if file_format == "unknown":
            console.print("[red]Could not detect file format. Please specify with --format[/red]")
            raise typer.Exit(1)

    console.print(f"[cyan]Detected format: {file_format.upper()}[/cyan]")

    # Parse file
    try:
        if file_format == "opml":
            sources_to_import = _parse_opml(file_path)
        else:
            sources_to_import = _parse_yaml(file_path)
    except ValueError as e:
        console.print(f"[red]Error parsing file: {e}[/red]")
        raise typer.Exit(1)

    if not sources_to_import:
        console.print("[yellow]No sources found in file.[/yellow]")
        return

    console.print(f"[green]Found {len(sources_to_import)} source(s) to import[/green]")

    # Preview table
    table = Table(title="Sources to Import" if not dry_run else "Sources (Dry Run)")
    table.add_column("Name", style="cyan")
    table.add_column("Type", width=10)
    table.add_column("Tier", width=6)
    table.add_column("Config", width=40)

    for src in sources_to_import:
        config_str = str(src.get("config", {}))[:40]
        table.add_row(
            src.get("name", "Unknown"),
            src.get("connector_type", "unknown"),
            src.get("tier", "T2"),
            config_str,
        )

    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run complete. No changes made.[/yellow]")
        return

    # Import sources
    db = SessionLocal()
    try:
        service = SourceService(db)
        imported = 0
        skipped = 0
        errors = []

        for src in sources_to_import:
            name = src.get("name", "")
            if not name:
                errors.append("Source missing name")
                continue

            # Check for existing
            existing = db.query(Source).filter(Source.name == name).first()
            if existing:
                if skip_existing:
                    skipped += 1
                    console.print(f"  [dim]Skipping existing: {name}[/dim]")
                    continue
                else:
                    errors.append(f"Source '{name}' already exists")
                    continue

            # Validate tier
            tier_str = src.get("tier", "T2")
            try:
                tier = SourceTier(tier_str.upper())
            except ValueError:
                tier = SourceTier.T2

            # Create source
            source, message = service.add_source(
                name=name,
                connector_type=src.get("connector_type", "rss"),
                tier=tier,
                config=src.get("config", {}),
                score=src.get("score"),
            )

            if source:
                imported += 1
                console.print(f"  [green]Imported: {name} ({source.source_id})[/green]")
            else:
                errors.append(message)

        # Summary
        console.print("\n[bold]Import Summary:[/bold]")
        console.print(f"  Imported: [green]{imported}[/green]")
        console.print(f"  Skipped: [yellow]{skipped}[/yellow]")

        if errors:
            console.print(f"  Errors: [red]{len(errors)}[/red]")
            for error in errors[:5]:  # Show first 5 errors
                console.print(f"    - {error}")

    finally:
        db.close()


@app.command("export")
def export_sources(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("yaml", "--format", "-f", help="Export format (opml, yaml)"),
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Filter by tier (T0, T1, T2, T3)"),
    include_removed: bool = typer.Option(False, "--include-removed", help="Include removed sources"),
) -> None:
    """
    Export sources to OPML or YAML format.

    OPML format only exports RSS sources with basic information.
    YAML format exports all source types with complete configuration.
    """
    # Validate format
    if format.lower() not in ("opml", "yaml"):
        console.print(f"[red]Invalid format: {format}. Must be 'opml' or 'yaml'[/red]")
        raise typer.Exit(1)

    file_format = format.lower()

    # Validate tier
    tier_filter = None
    if tier:
        try:
            tier_filter = SourceTier(tier.upper())
        except ValueError:
            console.print(f"[red]Invalid tier: {tier}. Must be one of: T0, T1, T2, T3[/red]")
            raise typer.Exit(1)

    # Get sources
    db = SessionLocal()
    try:
        service = SourceService(db)
        sources = service.list_sources(tier=tier_filter, limit=10000)

        if not include_removed:
            sources = [s for s in sources if s.status != SourceStatus.REMOVED]  # type: ignore[comparison-overlap]

        if not sources:
            console.print("[yellow]No sources to export.[/yellow]")
            return

        # Determine output path
        if output:
            output_path = output
        else:
            suffix = ".opml" if file_format == "opml" else ".yaml"
            output_path = Path(f"sources-export{suffix}")

        # Export
        console.print(f"[cyan]Exporting {len(sources)} source(s) to {file_format.upper()}...[/cyan]")

        if file_format == "opml":
            # OPML only supports RSS
            rss_sources = [s for s in sources if s.connector_type == "rss"]  # type: ignore[comparison-overlap]
            if len(rss_sources) < len(sources):
                console.print(f"[yellow]Note: OPML only supports RSS sources. {len(sources) - len(rss_sources)} non-RSS sources will be excluded.[/yellow]")
            _export_to_opml(rss_sources, output_path)
        else:
            _export_to_yaml(sources, output_path)

        console.print(f"[green]Exported to: {output_path}[/green]")

        # Preview
        table = Table(title="Exported Sources")
        table.add_column("Name", style="cyan")
        table.add_column("Type", width=10)
        table.add_column("Tier", width=6)

        for source in sources[:10]:  # Show first 10
            tier_color = _get_tier_color(source.tier.value)  # type: ignore[union-attr]
            table.add_row(
                source.name,  # type: ignore[arg-type]
                source.connector_type,  # type: ignore[arg-type]
                f"[{tier_color}]{source.tier.value}[/{tier_color}]",  # type: ignore[union-attr]
            )

        if len(sources) > 10:
            table.add_row("...", f"({len(sources) - 10} more)", "")

        console.print(table)

    finally:
        db.close()


@app.command("fetch-content")
def fetch_content(
    source_id: str = typer.Argument(..., help="Source ID to fetch content for"),
    item_limit: int = typer.Option(10, "--limit", "-l", help="Maximum items to fetch content for"),
) -> None:
    """Trigger full content fetch for items from a source.

    This command fetches full article content from original URLs for
    items that have summary-only or low-quality content.
    """
    if not _validate_source_id(source_id):
        console.print(f"[red]Invalid source ID format: {source_id}[/red]")
        console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
        raise typer.Exit(1)

    db = SessionLocal()
    try:
        from ...models import Item, ItemStatus

        # Get source
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            console.print(f"[red]Source not found: {source_id}[/red]")
            raise typer.Exit(1)

        # Find items that need full content fetch
        items = (
            db.query(Item)
            .filter(Item.source_id == source_id)
            .filter(Item.url.isnot(None))
            .filter(Item.full_fetch_attempted == False)  # noqa: E712
            .filter(Item.status == ItemStatus.MAPPED)
            .limit(item_limit)
            .all()
        )

        if not items:
            console.print("[yellow]No items found that need full content fetch.[/yellow]")
            return

        console.print(f"[cyan]Found {len(items)} item(s) to fetch full content for...[/cyan]")

        # Queue fetch tasks
        from ...tasks.quality_tasks import fetch_full_content

        queued = 0
        for item in items:
            fetch_full_content.send(item.item_id)  # type: ignore[union-attr]
            queued += 1

        console.print(f"[green]Queued {queued} full content fetch task(s)[/green]")
        console.print("[dim]Items will be re-normalized after content is fetched.[/dim]")

    finally:
        db.close()