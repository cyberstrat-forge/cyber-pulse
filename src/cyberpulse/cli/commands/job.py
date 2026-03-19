"""Job command module for managing collection jobs.

This module provides CLI commands to manage scheduled collection jobs:
- list: List all scheduled jobs
- run: Run a collection job immediately for a source
- cancel: Cancel/remove a scheduled job
- status: Get details of a specific job
"""
import logging
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ...scheduler.scheduler import SchedulerService

logger = logging.getLogger(__name__)
app = typer.Typer(
    name="job",
    help="Manage collection jobs",
)

console = Console()


def _get_scheduler() -> SchedulerService:
    """Get or create scheduler service instance.

    Returns:
        SchedulerService instance.
    """
    return SchedulerService()


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display.

    Args:
        dt: Datetime to format.

    Returns:
        Formatted string or 'N/A' if None.
    """
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.command("list")
def list_jobs(
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by job status (scheduled, paused)"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output in JSON format"
    ),
) -> None:
    """List all scheduled jobs.

    Shows all jobs currently scheduled in the system with their
    next run time and trigger configuration.
    """
    try:
        scheduler = _get_scheduler()
        jobs = scheduler.get_scheduled_jobs()

        # Filter by status if provided (check before early return)
        if status:
            status_lower = status.lower()
            # For now, all jobs in the scheduler are considered "scheduled"
            # Paused jobs would have next_run_time = None
            if status_lower == "paused":
                jobs = [j for j in jobs if j.get("next_run_time") is None]
            elif status_lower == "scheduled":
                jobs = [j for j in jobs if j.get("next_run_time") is not None]
            else:
                console.print(f"[red]Invalid status filter: {status}[/red]")
                console.print("[yellow]Valid options: scheduled, paused[/yellow]")
                raise typer.Exit(1)

        if not jobs:
            console.print("[yellow]No scheduled jobs found.[/yellow]")
            return

        if json_output:
            import json
            # Convert datetime objects to ISO format for JSON serialization
            for job in jobs:
                if job.get("next_run_time"):
                    job["next_run_time"] = job["next_run_time"].isoformat()
            console.print(json.dumps(jobs, indent=2))
            return

        # Create table for display
        table = Table(title="Scheduled Jobs")
        table.add_column("Job ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Next Run", style="yellow")
        table.add_column("Trigger", style="magenta")

        for job in jobs:
            table.add_row(
                job["id"],
                job["name"],
                _format_datetime(job.get("next_run_time")),
                job["trigger"],
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(jobs)} job(s)[/dim]")

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        console.print(f"[red]Error listing jobs: {e}[/red]")
        raise typer.Exit(1)


@app.command("run")
def run_job(
    source_id: str = typer.Argument(..., help="Source ID to run collection for"),
    wait: bool = typer.Option(
        False, "--wait", "-w", help="Wait for job to complete"
    ),
) -> None:
    """Run a collection job immediately for a source.

    Triggers the ingestion pipeline for the specified source.
    The job runs asynchronously unless --wait is specified.

    Examples:
        cyber-pulse job run src_abc123
        cyber-pulse job run src_abc123 --wait
    """
    try:
        # Validate source exists first
        from ...database import SessionLocal
        from ...models import Source

        db = SessionLocal()
        try:
            source = db.query(Source).filter(Source.source_id == source_id).first()
            if not source:
                console.print(f"[red]Source not found: {source_id}[/red]")
                raise typer.Exit(1)

            source_name = source.name
        finally:
            db.close()

        console.print(f"[cyan]Starting collection for source: {source_name} ({source_id})[/cyan]")

        # Check if there's a scheduled job for this source
        scheduler = _get_scheduler()
        job_id = f"collect_source_{source_id}"
        scheduled_job = scheduler.get_job(job_id)

        if scheduled_job:
            # Trigger the scheduled job to run now
            success = scheduler.run_job_now(job_id)
            if success:
                console.print(f"[green]Triggered scheduled job: {job_id}[/green]")
            else:
                console.print("[yellow]Warning: Could not trigger scheduled job[/yellow]")
        else:
            # No scheduled job, run directly via Dramatiq task
            from ...tasks.ingestion_tasks import ingest_source

            console.print("[dim]No scheduled job found, running ingestion task directly...[/dim]")
            ingest_source.send(source_id)
            console.print(f"[green]Queued ingestion task for source: {source_id}[/green]")

        if wait:
            console.print("[yellow]Waiting for job completion is not yet implemented.[/yellow]")
            console.print("[dim]Check logs for job progress.[/dim]")
        else:
            console.print("[dim]Job running in background. Check logs for progress.[/dim]")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Error running job: {e}")
        console.print(f"[red]Error running job: {e}[/red]")
        raise typer.Exit(1)


@app.command("cancel")
def cancel_job(
    job_id: str = typer.Argument(..., help="Job ID to cancel"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force cancel even if job is running"
    ),
) -> None:
    """Cancel a scheduled job.

    Removes the job from the scheduler. The job will no longer run
    automatically unless rescheduled.

    Examples:
        cyber-pulse job cancel collect_source_src_abc123
        cyber-pulse job cancel collect_source_src_abc123 --force
    """
    try:
        scheduler = _get_scheduler()

        # Check if job exists
        job = scheduler.get_job(job_id)
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(1)

        # Remove the job
        scheduler.scheduler.remove_job(job_id)

        console.print(f"[green]Cancelled job: {job_id}[/green]")
        console.print(f"[dim]Name: {job['name']}[/dim]")

        if force:
            console.print("[yellow]Note: --force flag has no effect for scheduled jobs.[/yellow]")
            console.print("[dim]Running instances are not affected by cancellation.[/dim]")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        console.print(f"[red]Error cancelling job: {e}[/red]")
        raise typer.Exit(1)


@app.command("status")
def job_status(
    job_id: str = typer.Argument(..., help="Job ID to check"),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output in JSON format"
    ),
) -> None:
    """Get details of a specific job.

    Shows detailed information about a scheduled job including
    its configuration and next run time.

    Examples:
        cyber-pulse job status collect_source_src_abc123
        cyber-pulse job status collect_source_src_abc123 --json
    """
    try:
        scheduler = _get_scheduler()
        job = scheduler.get_job(job_id)

        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(1)

        if json_output:
            import json
            # Convert datetime objects to ISO format
            if job.get("next_run_time"):
                job["next_run_time"] = job["next_run_time"].isoformat()
            console.print(json.dumps(job, indent=2))
            return

        # Display job details in a formatted way
        console.print(f"[cyan]Job ID:[/cyan] {job['id']}")
        console.print(f"[cyan]Name:[/cyan] {job['name']}")
        console.print(f"[cyan]Next Run:[/cyan] {_format_datetime(job.get('next_run_time'))}")
        console.print(f"[cyan]Trigger:[/cyan] {job['trigger']}")

        if job.get("args"):
            console.print(f"[cyan]Arguments:[/cyan] {job['args']}")
        if job.get("kwargs"):
            console.print(f"[cyan]Keyword Arguments:[/cyan] {job['kwargs']}")

        console.print(f"[cyan]Max Instances:[/cyan] {job.get('max_instances', 'N/A')}")
        console.print(f"[cyan]Misfire Grace Time:[/cyan] {job.get('misfire_grace_time', 'N/A')}s")

        # Determine status
        if job.get("next_run_time"):
            console.print("[green]Status: Scheduled[/green]")
        else:
            console.print("[yellow]Status: Paused[/yellow]")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        console.print(f"[red]Error getting job status: {e}[/red]")
        raise typer.Exit(1)


@app.command("schedule")
def schedule_job(
    source_id: str = typer.Argument(..., help="Source ID to schedule collection for"),
    interval: int = typer.Option(
        3600, "--interval", "-i", help="Collection interval in seconds (default: 3600)"
    ),
) -> None:
    """Schedule periodic collection for a source.

    Creates a scheduled job that will collect from the source
    at the specified interval.

    Examples:
        cyber-pulse job schedule src_abc123
        cyber-pulse job schedule src_abc123 --interval 1800
    """
    try:
        # Validate source exists
        from ...database import SessionLocal
        from ...models import Source

        db = SessionLocal()
        try:
            source = db.query(Source).filter(Source.source_id == source_id).first()
            if not source:
                console.print(f"[red]Source not found: {source_id}[/red]")
                raise typer.Exit(1)

            source_name = source.name
        finally:
            db.close()

        # Validate interval
        if interval < 60:
            console.print("[red]Interval must be at least 60 seconds.[/red]")
            raise typer.Exit(1)

        scheduler = _get_scheduler()
        job_id = scheduler.schedule_source_collection(source_id, interval=interval)

        console.print(f"[green]Scheduled collection for source: {source_name}[/green]")
        console.print(f"[cyan]Job ID:[/cyan] {job_id}")
        console.print(f"[cyan]Interval:[/cyan] {interval} seconds ({interval // 60} minutes)")

    except typer.Exit:
        raise
    except ValueError as e:
        console.print(f"[red]Validation error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"Error scheduling job: {e}")
        console.print(f"[red]Error scheduling job: {e}[/red]")
        raise typer.Exit(1)


@app.command("unschedule")
def unschedule_job(
    source_id: str = typer.Argument(..., help="Source ID to unschedule collection for"),
) -> None:
    """Remove scheduled collection for a source.

    Removes the scheduled job that collects from the specified source.

    Examples:
        cyber-pulse job unschedule src_abc123
    """
    try:
        scheduler = _get_scheduler()
        removed = scheduler.unschedule_source_collection(source_id)

        if removed:
            console.print(f"[green]Unscheduled collection for source: {source_id}[/green]")
        else:
            console.print(f"[yellow]No scheduled collection found for source: {source_id}[/yellow]")

    except Exception as e:
        logger.error(f"Error unscheduling job: {e}")
        console.print(f"[red]Error unscheduling job: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()