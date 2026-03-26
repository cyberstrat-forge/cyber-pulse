"""Tests for API startup initialization."""

from unittest.mock import MagicMock, patch, call
import pytest

from cyberpulse.models import ApiClient, ApiClientStatus
from cyberpulse.api.startup import ensure_admin_client


class TestEnsureAdminClient:
    """Tests for ensure_admin_client function."""

    def test_creates_admin_when_none_exists(self, capsys):
        """Should create admin client if none exists."""
        # Mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('cyberpulse.api.startup.SessionLocal', return_value=mock_db):
            ensure_admin_client()

        # Check admin was added
        assert mock_db.add.called
        assert mock_db.commit.called

        # Get the admin that was added
        added_admin = mock_db.add.call_args[0][0]
        assert added_admin.name == "Administrator"
        assert "admin" in added_admin.permissions
        assert added_admin.status == ApiClientStatus.ACTIVE

        # Check key was printed to stdout
        captured = capsys.readouterr()
        assert "Admin API Key:" in captured.out
        assert "cp_live_" in captured.out

    def test_does_not_create_if_admin_exists(self, capsys):
        """Should not create new admin if one already exists."""
        # Create existing admin mock
        existing_admin = MagicMock()
        existing_admin.client_id = "cli_existing01"
        existing_admin.name = "Existing Admin"
        existing_admin.permissions = ["admin", "read"]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_admin

        with patch('cyberpulse.api.startup.SessionLocal', return_value=mock_db):
            ensure_admin_client()

        # Should not add new admin
        assert not mock_db.add.called
        assert not mock_db.commit.called

        # Key should not be printed
        captured = capsys.readouterr()
        assert "Admin API Key:" not in captured.out

    def test_generated_key_format(self, capsys):
        """Generated key should have correct format."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('cyberpulse.api.startup.SessionLocal', return_value=mock_db):
            ensure_admin_client()

        captured = capsys.readouterr()
        # Extract key from output
        for line in captured.out.split('\n'):
            if 'cp_live_' in line:
                # Key should be cp_live_ followed by 32 hex chars
                key = line.split('cp_live_')[-1].strip()
                assert len(key) == 32
                assert all(c in '0123456789abcdef' for c in key)
                break