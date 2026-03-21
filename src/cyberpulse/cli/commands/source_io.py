"""Source import/export commands for CLI.

This module provides commands for importing and exporting sources
in OPML and YAML formats.

OPML format: Only supports RSS sources with basic information (name, feed_url).
YAML format: Supports all source types with complete configuration.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from xml.etree import ElementTree

import typer
import yaml
from rich.console import Console
from rich.table import Table

from ...database import SessionLocal
from ...services import SourceService
from ...models import Source, SourceTier, SourceStatus

logger = logging.getLogger(__name__)
app = typer.Typer(name="source-io", help="Source import/export operations")
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
        if source.connector_type == "rss" and source.status != SourceStatus.REMOVED:
            tier_groups[source.tier.value].append(source)

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
        if source.status == SourceStatus.REMOVED:
            continue

        source_dict = {
            "name": source.name,
            "connector_type": source.connector_type,
            "tier": source.tier.value,
            "score": source.score,
            "config": source.config,
        }

        # Add optional fields if they differ from defaults
        if source.fetch_interval:
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
            sources = [s for s in sources if s.status != SourceStatus.REMOVED]

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
            rss_sources = [s for s in sources if s.connector_type == "rss"]
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
            tier_color = _get_tier_color(source.tier.value)
            table.add_row(
                source.name,
                source.connector_type,
                f"[{tier_color}]{source.tier.value}[/{tier_color}]",
            )

        if len(sources) > 10:
            table.add_row("...", f"({len(sources) - 10} more)", "")

        console.print(table)

    finally:
        db.close()


@app.command("list")
def list_sources(
    tier: Optional[str] = typer.Option(None, "--tier", "-t", help="Filter by tier (T0, T1, T2, T3)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    format: str = typer.Option("table", "--format", "-f", help="Output format (table, yaml, json)"),
) -> None:
    """
    List all sources with optional filtering.

    Use --format yaml or --format json for machine-readable output.
    """
    # Validate tier
    tier_filter = None
    if tier:
        try:
            tier_filter = SourceTier(tier.upper())
        except ValueError:
            console.print(f"[red]Invalid tier: {tier}. Must be one of: T0, T1, T2, T3[/red]")
            raise typer.Exit(1)

    # Validate status
    status_filter = None
    if status:
        try:
            status_filter = SourceStatus(status.upper())
        except ValueError:
            console.print(f"[red]Invalid status: {status}. Must be one of: ACTIVE, FROZEN, REMOVED[/red]")
            raise typer.Exit(1)

    # Get sources
    db = SessionLocal()
    try:
        service = SourceService(db)
        sources = service.list_sources(tier=tier_filter, status=status_filter, limit=10000)

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
            import json
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
            console.print(json.dumps({"sources": sources_data}, indent=2))

        else:
            # Table format
            table = Table(title=f"Sources ({len(sources)} found)")
            table.add_column("ID", style="dim", width=14)
            table.add_column("Name", style="cyan")
            table.add_column("Type", width=10)
            table.add_column("Tier", width=6)
            table.add_column("Score", width=6)
            table.add_column("Status", width=8)

            for source in sources:
                tier_color = _get_tier_color(source.tier.value)
                status_color = "green" if source.status == SourceStatus.ACTIVE else "yellow" if source.status == SourceStatus.FROZEN else "red"

                table.add_row(
                    source.source_id,
                    source.name,
                    source.connector_type,
                    f"[{tier_color}]{source.tier.value}[/{tier_color}]",
                    f"{source.score:.1f}",
                    f"[{status_color}]{source.status.value}[/{status_color}]",
                )

            console.print(table)

    finally:
        db.close()