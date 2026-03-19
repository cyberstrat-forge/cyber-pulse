"""Tests for CLI client commands."""
import re
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from cyberpulse.cli.app import app
from cyberpulse.models.api_client import ApiClientStatus

runner = CliRunner()


class TestClientCreate:
    """Tests for client create command."""

    def test_client_create_success(self, db_session) -> None:
        """Test creating a client successfully."""
        from cyberpulse.api.auth import ApiClientService

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "create", "Test Client"])

            assert result.exit_code == 0
            assert "Created client:" in result.stdout
            assert "cli_" in result.stdout
            assert "API Key:" in result.stdout
            assert "cp_live_" in result.stdout
            assert "Warning:" in result.stdout

    def test_client_create_with_description(self, db_session) -> None:
        """Test creating a client with description."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(
                app,
                ["client", "create", "Test Client", "--description", "Test description"],
            )

            assert result.exit_code == 0
            assert "Created client:" in result.stdout

    def test_client_create_shows_key_once(self, db_session) -> None:
        """Test that API key is shown in output."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "create", "Test Client"])

            # API key should appear exactly once in output
            assert result.exit_code == 0
            # Verify the key format
            key_match = re.search(r"cp_live_[a-f0-9]{32}", result.stdout)
            assert key_match is not None


class TestClientList:
    """Tests for client list command."""

    def test_client_list_empty(self, db_session) -> None:
        """Test listing clients when none exist."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "list"])

            assert result.exit_code == 0
            assert "No clients found" in result.stdout

    def test_client_list_with_clients(self, db_session) -> None:
        """Test listing clients when some exist."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        service.create_client(name="Client 1")
        service.create_client(name="Client 2")

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "list"])

            assert result.exit_code == 0
            assert "Client 1" in result.stdout
            assert "Client 2" in result.stdout
            assert "Total:" in result.stdout

    def test_client_list_filter_by_status(self, db_session) -> None:
        """Test listing clients filtered by status."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        active_client, _ = service.create_client(name="Active Client")
        suspended_client, _ = service.create_client(name="Suspended Client")
        service.suspend_client(suspended_client.client_id)

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "list", "--status", "active"])

            assert result.exit_code == 0
            assert "Active Client" in result.stdout
            assert "Suspended Client" not in result.stdout

    def test_client_list_invalid_status(self, db_session) -> None:
        """Test listing clients with invalid status filter."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "list", "--status", "invalid"])

            assert result.exit_code == 1
            assert "Invalid status" in result.stdout


class TestClientDisable:
    """Tests for client disable command."""

    def test_client_disable_success(self, db_session) -> None:
        """Test disabling a client successfully."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "disable", client_id])

            assert result.exit_code == 0
            assert "Disabled client:" in result.stdout
            assert client_id in result.stdout

        # Verify status is suspended (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.SUSPENDED

    def test_client_disable_not_found(self, db_session) -> None:
        """Test disabling a non-existent client."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            # Use a valid client_id format: cli_{16 hex chars}
            result = runner.invoke(app, ["client", "disable", "cli_aaaa0000bbbb1111"])

            assert result.exit_code == 1
            assert "Client not found" in result.stdout

    def test_client_disable_invalid_id_format(self, db_session) -> None:
        """Test disabling with invalid client ID format."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "disable", "invalid_id"])

            assert result.exit_code == 1
            assert "Invalid client_id format" in result.stdout


class TestClientEnable:
    """Tests for client enable command."""

    def test_client_enable_success(self, db_session) -> None:
        """Test enabling a suspended client."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id
        service.suspend_client(client_id)

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "enable", client_id])

            assert result.exit_code == 0
            assert "Enabled client:" in result.stdout
            assert client_id in result.stdout

        # Verify status is active (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.ACTIVE

    def test_client_enable_not_found(self, db_session) -> None:
        """Test enabling a non-existent client."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            # Use a valid client_id format: cli_{16 hex chars}
            result = runner.invoke(app, ["client", "enable", "cli_aaaa0000bbbb1111"])

            assert result.exit_code == 1
            assert "Client not found" in result.stdout

    def test_client_enable_invalid_id_format(self, db_session) -> None:
        """Test enabling with invalid client ID format."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "enable", "invalid_id"])

            assert result.exit_code == 1
            assert "Invalid client_id format" in result.stdout

    def test_client_enable_revoked_client(self, db_session) -> None:
        """Test enabling a revoked client."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id
        service.revoke_client(client_id)

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(app, ["client", "enable", client_id])

            assert result.exit_code == 0
            assert "Enabled client:" in result.stdout

        # Verify status is active (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.ACTIVE


class TestClientDelete:
    """Tests for client delete command."""

    def test_client_delete_with_confirmation(self, db_session) -> None:
        """Test deleting a client with confirmation."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(
                app,
                ["client", "delete", client_id],
                input="y\n",
            )

            assert result.exit_code == 0
            assert "Deleted client:" in result.stdout
            assert client_id in result.stdout

        # Verify status is revoked (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.REVOKED

    def test_client_delete_cancel_confirmation(self, db_session) -> None:
        """Test cancelling delete with confirmation."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(
                app,
                ["client", "delete", client_id],
                input="n\n",
            )

            assert result.exit_code == 0
            assert "Cancelled" in result.stdout

        # Verify status is still active (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.ACTIVE

    def test_client_delete_force(self, db_session) -> None:
        """Test deleting a client with force flag (no confirmation)."""
        from cyberpulse.api.auth import ApiClientService

        service = ApiClientService(db_session)
        client, _ = service.create_client(name="Test Client")
        client_id = client.client_id

        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(
                app,
                ["client", "delete", client_id, "--force"],
            )

            assert result.exit_code == 0
            assert "Deleted client:" in result.stdout

        # Verify status is revoked (need fresh query)
        updated_client = service.get_client(client_id)
        assert updated_client is not None
        assert updated_client.status == ApiClientStatus.REVOKED

    def test_client_delete_not_found(self, db_session) -> None:
        """Test deleting a non-existent client."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            # Use a valid client_id format: cli_{16 hex chars}
            result = runner.invoke(
                app,
                ["client", "delete", "cli_aaaa0000bbbb1111", "--force"],
            )

            assert result.exit_code == 1
            assert "Client not found" in result.stdout

    def test_client_delete_invalid_id_format(self, db_session) -> None:
        """Test deleting with invalid client ID format."""
        with patch("cyberpulse.cli.commands.client.SessionLocal") as mock_session:
            mock_session.return_value = db_session

            result = runner.invoke(
                app,
                ["client", "delete", "invalid_id", "--force"],
            )

            assert result.exit_code == 1
            assert "Invalid client_id format" in result.stdout


class TestClientCommandsHelp:
    """Tests for client command help."""

    def test_client_help(self) -> None:
        """Test client command help shows all subcommands."""
        result = runner.invoke(app, ["client", "--help"])

        assert result.exit_code == 0
        assert "Manage API clients" in result.stdout
        assert "create" in result.stdout
        assert "list" in result.stdout
        assert "disable" in result.stdout
        assert "enable" in result.stdout
        assert "delete" in result.stdout

    def test_client_create_help(self) -> None:
        """Test client create command help."""
        result = runner.invoke(app, ["client", "create", "--help"])

        assert result.exit_code == 0
        assert "Create a new API client" in result.stdout
        assert "--description" in result.stdout

    def test_client_list_help(self) -> None:
        """Test client list command help."""
        result = runner.invoke(app, ["client", "list", "--help"])

        assert result.exit_code == 0
        assert "List all API clients" in result.stdout
        assert "--status" in result.stdout

    def test_client_delete_help(self) -> None:
        """Test client delete command help."""
        result = runner.invoke(app, ["client", "delete", "--help"])

        assert result.exit_code == 0
        assert "Delete" in result.stdout
        assert "--force" in result.stdout