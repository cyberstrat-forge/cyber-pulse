"""Tests for API auth module - reset_admin_key functionality."""

from unittest.mock import MagicMock

from cyberpulse.api.auth import (
    ApiClientService,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)
from cyberpulse.models import ApiClientStatus


class TestResetAdminKey:
    """Tests for reset_admin_key functionality."""

    def test_reset_admin_key_success(self):
        """Should reset admin key and return new plain key."""
        # Create mock admin
        admin = MagicMock()
        admin.client_id = "cli_admin01"
        admin.name = "Admin"
        admin.api_key = hash_api_key(generate_api_key())
        admin.status = ApiClientStatus.ACTIVE
        admin.permissions = ["admin", "read"]

        # Mock database session
        mock_db = MagicMock()

        # Mock get_by_permission to return admin
        service = ApiClientService(mock_db)
        service.get_by_permission = MagicMock(return_value=admin)

        result = service.reset_admin_key()

        assert result is not None
        client, new_key = result
        assert client.client_id == "cli_admin01"
        assert new_key.startswith("cp_live_")

        # Verify new key works
        assert verify_api_key(new_key, admin.api_key)

        # Verify commit was called
        assert mock_db.commit.called

    def test_reset_admin_key_no_admin_exists(self):
        """Should return None if no admin client exists."""
        mock_db = MagicMock()

        service = ApiClientService(mock_db)
        service.get_by_permission = MagicMock(return_value=None)

        result = service.reset_admin_key()
        assert result is None

    def test_old_key_invalid_after_reset(self):
        """Old key should be invalid after reset."""
        old_key = generate_api_key()

        # Create mock admin with old key
        admin = MagicMock()
        admin.client_id = "cli_admin02"
        admin.name = "Admin"
        admin.api_key = hash_api_key(old_key)
        admin.status = ApiClientStatus.ACTIVE
        admin.permissions = ["admin"]

        mock_db = MagicMock()

        service = ApiClientService(mock_db)
        service.get_by_permission = MagicMock(return_value=admin)

        result = service.reset_admin_key()

        # Old key should no longer verify against new hash
        assert result is not None
        _, new_key = result
        assert new_key != old_key
        # Verify new key works with the updated hash
        assert verify_api_key(new_key, admin.api_key)
        # Old key should not work
        assert not verify_api_key(old_key, admin.api_key)
