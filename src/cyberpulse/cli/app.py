"""
Main CLI application for cyber-pulse.

This module provides the main entry point for the cyber-pulse CLI,
registering all command modules and providing core commands.
"""
import typer

from .commands import source, source_io, job, content, client, config, log, diagnose

app = typer.Typer(
    name="cyber-pulse",
    help="Security Intelligence Collection System",
)


# Register command modules
app.add_typer(source.app, name="source")
app.add_typer(source_io.app, name="source-io")
app.add_typer(job.app, name="job")
app.add_typer(content.app, name="content")
app.add_typer(client.app, name="client")
app.add_typer(config.app, name="config")
app.add_typer(log.app, name="log")
app.add_typer(diagnose.app, name="diagnose")


@app.command()
def shell() -> None:
    """Start interactive TUI."""
    from .tui import run_tui

    run_tui()


@app.command()
def version() -> None:
    """Show version."""
    from .. import __version__

    typer.echo(f"cyber-pulse version {__version__}")


@app.command()
def server(
    action: str = typer.Argument(..., help="start|stop|restart|status"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Server host"),
) -> None:
    """
    Manage API server.

    Actions:
    - start: Start the API server
    - stop: Stop the API server
    - restart: Restart the API server
    - status: Check server status
    """
    import subprocess
    import sys

    valid_actions = {"start", "stop", "restart", "status"}

    if action not in valid_actions:
        typer.secho(
            f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    if action == "start":
        typer.secho(f"Starting API server on {host}:{port}...", fg=typer.colors.GREEN)
        # Use uvicorn to run the FastAPI app
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cyberpulse.api.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ]
        )
    elif action == "stop":
        typer.secho("Stop action not yet implemented", fg=typer.colors.YELLOW)
    elif action == "restart":
        typer.secho("Restart action not yet implemented", fg=typer.colors.YELLOW)
    elif action == "status":
        typer.secho("Status action not yet implemented", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()