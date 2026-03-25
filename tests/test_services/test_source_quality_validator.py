"""Tests for SourceQualityValidator."""

import pytest
from unittest.mock import AsyncMock, patch
from cyberpulse.services.source_quality_validator import (
    SourceQualityValidator,
    SourceValidationResult,
)


class TestSourceQualityValidator:
    """Test cases for SourceQualityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SourceQualityValidator()

    def test_source_validation_result_dataclass(self):
        """Test SourceValidationResult dataclass."""
        result = SourceValidationResult(
            is_valid=True,
            content_type="article",
            sample_completeness=0.8,
            avg_content_length=500,
        )
        assert result.is_valid is True
        assert result.content_type == "article"

    def test_quality_constants(self):
        """Test quality threshold constants."""
        assert self.validator.MIN_SAMPLE_ITEMS == 3
        assert self.validator.MIN_AVG_COMPLETENESS == 0.4
        assert self.validator.MIN_AVG_CONTENT_LENGTH == 50

    @pytest.mark.asyncio
    async def test_validate_source_high_quality(self):
        """Test validation of high-quality source."""
        config = {"feed_url": "https://example.com/feed.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": "x" * 600} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is True
        assert result.sample_completeness >= 0.4

    @pytest.mark.asyncio
    async def test_validate_source_low_quality(self):
        """Test validation of low-quality source (empty content)."""
        config = {"feed_url": "https://example.com/empty.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": ""} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is False
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_validate_source_with_force(self):
        """Test validation with force option."""
        config = {"feed_url": "https://example.com/bad.xml"}

        result = await self.validator.validate_source_with_force(
            config,
            force=True,
        )

        assert result.is_valid is True