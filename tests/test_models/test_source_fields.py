# tests/test_models/test_source_fields.py
"""Tests for Source model fields."""

from datetime import UTC

from cyberpulse.models import Source, SourceStatus


class TestSourceFailureTracking:
    """Test Source failure tracking fields."""

    def test_source_has_consecutive_failures_field(self, db_session):
        """Test that Source has consecutive_failures field with default 0."""
        source = Source(
            source_id="src_test01",
            name="Test Source",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        db_session.refresh(source)
        assert source.consecutive_failures == 0

    def test_source_has_last_error_at_field(self, db_session):
        """Test that Source has last_error_at field."""
        from datetime import datetime

        source = Source(
            source_id="src_test02",
            name="Test Source 2",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(source)
        db_session.commit()

        # Set last_error_at
        now = datetime.now(UTC).replace(tzinfo=None)
        source.last_error_at = now
        db_session.commit()

        db_session.refresh(source)
        assert source.last_error_at is not None
