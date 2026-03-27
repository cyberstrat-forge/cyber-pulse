"""Tests for Settings model."""

import pytest
from sqlalchemy.exc import IntegrityError

from cyberpulse.models.settings import Settings


class TestSettingsModel:
    """Test cases for Settings model."""

    def test_settings_creation(self, db_session):
        """Test creating a settings record."""
        setting = Settings(
            key="default_fetch_interval",
            value="3600",
        )
        db_session.add(setting)
        db_session.commit()

        db_session.refresh(setting)
        assert setting.key == "default_fetch_interval"
        assert setting.value == "3600"

    @pytest.mark.filterwarnings("ignore::sqlalchemy.exc.SAWarning")
    def test_settings_upsert(self, db_session):
        """Test upsert behavior for settings."""
        # Create initial
        setting = Settings(key="test_key", value="value1")
        db_session.add(setting)
        db_session.commit()

        # Try to create duplicate - should fail
        # Use nested transaction (savepoint) to isolate the error
        nested = db_session.begin_nested()
        duplicate = Settings(key="test_key", value="value2")
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.commit()
        nested.rollback()  # Rollback the savepoint, outer transaction remains valid

    def test_settings_with_null_value(self, db_session):
        """Test settings with null value."""
        setting = Settings(key="optional_setting", value=None)
        db_session.add(setting)
        db_session.commit()

        db_session.refresh(setting)
        assert setting.key == "optional_setting"
        assert setting.value is None