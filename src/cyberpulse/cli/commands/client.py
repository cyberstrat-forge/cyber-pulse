"""Client command module for managing API clients."""
import re
import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from ...database import SessionLocal
from ...api.auth import ApiClientService
from ...models.api_client import ApiClientStatus

app = typer.Typer(
    name="client",
    help="Manage API clients",
)

console = Console()

# client_id format: cli_{16 hex chars}
CLIENT_ID_PATTERN = re.compile(r"^cli_[a-f0-9]{16}$")


def validate_client_id(client_id: str) -> bool:
    """Validate client_id format."""
    return bool(CLIENT_ID_PATTERN.match(client_id))


@app.command("create")
def create_client(
    name: str = typer.Argument(..., help="Client name"),
    description: str = typer.Option(None, "--description", "-d", help="Client description"),
) -> None:
    """Create a new API client.

    The API key will be displayed ONCE. Store it securely.
    """
    try:
        db = SessionLocal()
        try:
            service = ApiClientService(db)
            client, plain_key = service.create_client(
                name=name,
                description=description,
            )

            console.print(f"[green]Created client:[/] {client.client_id}")
            console.print(f"[bold yellow]API Key:[/] {plain_key}")
            console.print()
            console.print(
                "Warning: This API key will only be shown once. "
                "Store it securely - it cannot be retrieved again.",
                style="yellow",
            )
        finally:
            db.close()
    except SQLAlchemyError as e:
        console.print(f"[red]Error creating client: {e}[/]")
        raise typer.Exit(1)


@app.command("list")
def list_clients(
    status: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (ACTIVE, SUSPENDED, REVOKED)",
    ),
) -> None:
    """List all API clients."""
    try:
        db = SessionLocal()
        try:
            service = ApiClientService(db)

            # Convert status string to enum if provided
            status_enum = None
            if status:
                try:
                    status_enum = ApiClientStatus(status.upper())
                except ValueError:
                    valid_statuses = [s.value for s in ApiClientStatus]
                    console.print(
                        f"[red]Invalid status '{status}'. "
                        f"Must be one of: {', '.join(valid_statuses)}[/]"
                    )
                    raise typer.Exit(1)

            clients = service.list_clients(status_filter=status_enum)

            if not clients:
                console.print("[yellow]No clients found.[/]")
                return

            table = Table(title="API Clients")
            table.add_column("Client ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Status", style="magenta")
            table.add_column("Description")
            table.add_column("Created At")

            for client in clients:
                # Truncate description for display
                raw_desc = getattr(client, "description", None)
                desc = raw_desc[:27] + "..." if raw_desc and len(raw_desc) > 30 else (raw_desc or "")

                # Color code status
                status_str = client.status.value
                if client.status == ApiClientStatus.ACTIVE:
                    status_display = f"[green]{status_str}[/]"
                elif client.status == ApiClientStatus.SUSPENDED:
                    status_display = f"[yellow]{status_str}[/]"
                else:
                    status_display = f"[red]{status_str}[/]"

                table.add_row(
                    client.client_id,
                    client.name,
                    status_display,
                    desc,
                    str(client.created_at.strftime("%Y-%m-%d %H:%M")) if client.created_at else "",
                )

            console.print(table)
            console.print(f"\n[dim]Total: {len(clients)} client(s)[/]")
        finally:
            db.close()
    except SQLAlchemyError as e:
        console.print(f"[red]Error listing clients: {e}[/]")
        raise typer.Exit(1)


@app.command("disable")
def disable_client(
    client_id: str = typer.Argument(..., help="Client ID to disable"),
) -> None:
    """Disable (suspend) an API client.

    Suspended clients cannot authenticate but can be re-enabled later.
    """
    if not validate_client_id(client_id):
        console.print(
            f"[red]Invalid client_id format: {client_id}[/]\n"
            "Expected format: cli_xxxxxxxxxxxxxxxx"
        )
        raise typer.Exit(1)

    try:
        db = SessionLocal()
        try:
            service = ApiClientService(db)
            success = service.suspend_client(client_id)

            if not success:
                console.print(f"[red]Client not found: {client_id}[/]")
                raise typer.Exit(1)

            console.print(f"[green]Disabled client:[/] {client_id}")
            console.print("Client status set to suspended. Use enable to reactivate.", style="dim")
        finally:
            db.close()
    except SQLAlchemyError as e:
        console.print(f"[red]Error disabling client: {e}[/]")
        raise typer.Exit(1)


@app.command("enable")
def enable_client(
    client_id: str = typer.Argument(..., help="Client ID to enable"),
) -> None:
    """Enable (reactivate) a suspended or revoked API client."""
    if not validate_client_id(client_id):
        console.print(
            f"[red]Invalid client_id format: {client_id}[/]\n"
            "Expected format: cli_xxxxxxxxxxxxxxxx"
        )
        raise typer.Exit(1)

    try:
        db = SessionLocal()
        try:
            service = ApiClientService(db)
            success = service.activate_client(client_id)

            if not success:
                console.print(f"[red]Client not found: {client_id}[/]")
                raise typer.Exit(1)

            console.print(f"[green]Enabled client:[/] {client_id}")
            console.print("Client status set to active.", style="dim")
        finally:
            db.close()
    except SQLAlchemyError as e:
        console.print(f"[red]Error enabling client: {e}[/]")
        raise typer.Exit(1)


@app.command("delete")
def delete_client(
    client_id: str = typer.Argument(..., help="Client ID to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Delete (revoke) an API client.

    This is a soft delete - the client record remains for audit purposes.
    The client will no longer be able to authenticate.
    """
    if not validate_client_id(client_id):
        console.print(
            f"[red]Invalid client_id format: {client_id}[/]\n"
            "Expected format: cli_xxxxxxxxxxxxxxxx"
        )
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(
            f"Are you sure you want to delete client {client_id}?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)

    try:
        db = SessionLocal()
        try:
            service = ApiClientService(db)
            success = service.revoke_client(client_id)

            if not success:
                console.print(f"[red]Client not found: {client_id}[/]")
                raise typer.Exit(1)

            console.print(f"[green]Deleted client:[/] {client_id}")
            console.print("Client status set to revoked. This is a soft delete.", style="dim")
        finally:
            db.close()
    except SQLAlchemyError as e:
        console.print(f"[red]Error deleting client: {e}[/]")
        raise typer.Exit(1)