"""Source command module for managing intelligence sources."""

import asyncio
import typer
from typing import Optional, List

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

app = typer.Typer(name="source", help="Manage intelligence sources")
console = Console()


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
        "active": "green",
        "frozen": "yellow",
        "removed": "red",
    }
    return colors.get(status, "white")


def _validate_source_id(source_id: str) -> bool:
    """Validate source ID format."""
    import re
    return bool(re.match(r"^src_[a-f0-9]{8}$", source_id))


@app.command("list")
def list_sources(
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Filter by tier (T0, T1, T2, T3)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (active, frozen, removed)"),
    limit: int = typer.Option(100, "--limit", "-l", help="Maximum number of results"),
) -> None:
    """List all sources with optional filtering."""
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
            status_filter = SourceStatus(status.lower())
        except ValueError:
            console.print(f"[red]Invalid status: {status}. Must be one of: active, frozen, removed[/red]")
            raise typer.Exit(1)

    db = SessionLocal()
    try:
        service = SourceService(db)
        sources = service.list_sources(tier=tier_filter, status=status_filter, limit=limit)

        if not sources:
            console.print("[yellow]No sources found.[/yellow]")
            return

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

            observation_status = "Yes" if source.is_in_observation else "No"
            if source.is_in_observation and source.observation_until:
                observation_status = f"Until {source.observation_until.strftime('%Y-%m-%d')}"

            table.add_row(
                source.source_id,
                source.name,
                source.connector_type,
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
            if not typer.confirm("Continue anyway?"):
                raise typer.Exit(0)

        console.print("[green]No duplicates found.[/green]")

        # Prepare config based on connector type
        config: dict = {}
        if connector == "rss":
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
                        if typer.confirm(f"Use suggested tier {suggested_tier.value} instead?"):
                            source_tier = suggested_tier

                else:
                    console.print("[yellow]Warning: No items found at source URL.[/yellow]")
                    if not typer.confirm("Add source anyway?"):
                        raise typer.Exit(0)

            except ConnectorError as e:
                console.print(f"[red]Connection failed: {e}[/red]")
                if not typer.confirm("Add source anyway (will need manual fix)?"):
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
                f"[bold]Observation:[/bold] {source.observation_until.strftime('%Y-%m-%d') if source.observation_until else 'N/A'}",
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
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status (active, frozen)"),
) -> None:
    """Update a source's tier or status."""
    # Validate source ID format
    if not _validate_source_id(source_id):
        console.print(f"[red]Invalid source ID format: {source_id}[/red]")
        console.print("[yellow]Expected format: src_xxxxxxxx (8 hex characters)[/yellow]")
        raise typer.Exit(1)

    if not tier and not status:
        console.print("[yellow]No updates specified. Use --tier or --status options.[/yellow]")
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
                kwargs["status"] = status.lower()
            except ValueError:
                console.print(f"[red]Invalid status: {status}[/red]")
                raise typer.Exit(1)

        source, message = service.update_source(source_id, **kwargs)

        if source:
            console.print(f"[green]{message}[/green]")
            console.print(f"  Tier: {source.tier.value}")
            console.print(f"  Score: {source.score:.1f}")
            console.print(f"  Status: {source.status.value}")
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

        if stats["status"] == "removed":
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
        service = SourceService(db)
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
            connector = get_connector(source.connector_type, source.config)
            connector.validate_config()
            console.print("   [green]Configuration valid[/green]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("   Fetching items...", total=None)
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

        except Exception as e:
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
            except ValueError:
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
            status_counts = {"active": 0, "frozen": 0, "removed": 0}
            total_items = 0
            total_contents = 0
            observation_count = 0

            for source in sources:
                tier_counts[source.tier.value] += 1
                status_counts[source.status.value] += 1
                total_items += source.total_items
                total_contents += source.total_contents
                if source.is_in_observation:
                    observation_count += 1

            # Summary table
            table = Table(title="Source Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Total Sources", str(len(sources)))
            table.add_row("Active", str(status_counts["active"]))
            table.add_row("Frozen", str(status_counts["frozen"]))
            table.add_row("Removed", str(status_counts["removed"]))
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