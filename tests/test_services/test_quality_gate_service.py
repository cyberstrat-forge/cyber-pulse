"""Tests for QualityGateService."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cyberpulse.services.quality_gate_service import (
    QualityDecision,
    QualityGateService,
    QualityResult,
)
from cyberpulse.services.normalization_service import NormalizationResult


@pytest.fixture
def quality_gate_service():
    """Create a QualityGateService instance."""
    return QualityGateService()


@pytest.fixture
def valid_item():
    """Create a valid Item mock."""
    item = MagicMock()
    item.title = "This is a valid title"
    item.url = "https://example.com/article/123"
    item.published_at = datetime.now() - timedelta(days=1)
    item.raw_metadata = {"author": "John Doe", "tags": ["tech", "news"]}
    item.raw_content = "<p>This is the raw content of the article.</p>"
    return item


@pytest.fixture
def valid_normalization_result():
    """Create a valid NormalizationResult."""
    return NormalizationResult(
        normalized_title="This is a valid title",
        normalized_body="This is the normalized body content with enough text to be meaningful.",
        canonical_hash="abc123def456",
        language="en",
        word_count=10,
        extraction_method="trafilatura",
    )


class TestCheck:
    """Tests for check method."""

    def test_check_pass(self, quality_gate_service, valid_item, valid_normalization_result):
        """Test quality check passes for valid item."""
        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.PASS
        assert result.rejection_reason is None
        assert isinstance(result.warnings, list)
        assert isinstance(result.metrics, dict)

    def test_check_reject_missing_title(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test quality check rejects item with missing or too short title."""
        valid_item.title = "Ab"  # Too short (< 5 chars)

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason is not None
        assert "title" in result.rejection_reason.lower()

    def test_check_reject_empty_body(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test quality check rejects item with empty body."""
        valid_normalization_result.normalized_body = ""

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason is not None
        assert "body" in result.rejection_reason.lower()

    def test_check_reject_invalid_url(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test quality check rejects item with invalid URL."""
        valid_item.url = "not-a-valid-url"

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason is not None
        assert "url" in result.rejection_reason.lower()

    def test_check_reject_invalid_date(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test quality check rejects item with invalid date."""
        valid_item.published_at = None

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason is not None
        assert "date" in result.rejection_reason.lower()

    def test_check_warnings_missing_author(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test quality check warns about missing author."""
        valid_item.raw_metadata = {}  # No author

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.PASS
        assert any("author" in w.lower() for w in result.warnings)

    def test_check_pass_with_missing_optional_author(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test that missing author only produces warning, not rejection."""
        valid_item.raw_metadata = {}  # No author

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        # Should still pass, just with a warning
        assert result.decision == QualityDecision.PASS


class TestValidateRequiredFields:
    """Tests for _validate_required_fields method."""

    def test_validate_all_fields_valid(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation passes with all valid fields."""
        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert errors == []

    def test_validate_short_title(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for short title."""
        valid_item.title = "AB"

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "title" in errors[0].lower()

    def test_validate_empty_body(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for empty body."""
        valid_normalization_result.normalized_body = ""

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "body" in errors[0].lower()

    def test_validate_whitespace_body(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for whitespace-only body."""
        valid_normalization_result.normalized_body = "   \n\t  "

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "body" in errors[0].lower()

    def test_validate_invalid_url(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for invalid URL."""
        valid_item.url = "not-a-url"

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "url" in errors[0].lower()

    def test_validate_missing_date(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for missing date."""
        valid_item.published_at = None

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "date" in errors[0].lower()

    def test_validate_future_date(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for date too far in the future."""
        valid_item.published_at = datetime.now() + timedelta(days=10)

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "date" in errors[0].lower()

    def test_validate_date_too_old(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation fails for date too old (before year 2000)."""
        valid_item.published_at = datetime(1990, 1, 1)

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 1
        assert "date" in errors[0].lower()

    def test_validate_multiple_errors(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test validation catches multiple errors."""
        valid_item.title = "AB"  # Too short
        valid_item.url = "invalid"  # Invalid URL

        errors = quality_gate_service._validate_required_fields(
            valid_item, valid_normalization_result
        )

        assert len(errors) == 2


class TestCheckOptionalFields:
    """Tests for _check_optional_fields method."""

    def test_check_optional_all_present(self, quality_gate_service, valid_item):
        """Test no warnings when all optional fields present."""
        valid_item.raw_metadata = {"author": "John Doe", "tags": ["tag1"]}

        warnings = quality_gate_service._check_optional_fields(valid_item)

        assert warnings == []

    def test_check_optional_missing_author(self, quality_gate_service, valid_item):
        """Test warning for missing author."""
        valid_item.raw_metadata = {}

        warnings = quality_gate_service._check_optional_fields(valid_item)

        assert len(warnings) == 1
        assert "author" in warnings[0].lower()

    def test_check_optional_none_metadata(self, quality_gate_service, valid_item):
        """Test warning when raw_metadata is None."""
        valid_item.raw_metadata = None

        warnings = quality_gate_service._check_optional_fields(valid_item)

        # Should handle None gracefully
        assert "author" in warnings[0].lower() if warnings else True


class TestCalculateMetrics:
    """Tests for _calculate_metrics method."""

    def test_calculate_metrics(self, quality_gate_service, valid_item, valid_normalization_result):
        """Test metrics calculation."""
        valid_item.raw_content = "<p>This is test content.</p>"
        valid_normalization_result.normalized_body = "This is the normalized body content."
        valid_normalization_result.normalized_title = "Test Title Here"
        valid_item.raw_metadata = {"author": "John", "tags": ["tag1", "tag2"]}

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        assert "title_length" in metrics
        assert "body_length" in metrics
        assert "word_count" in metrics
        assert "meta_completeness" in metrics
        assert "content_completeness" in metrics
        assert "noise_ratio" in metrics

        # Check specific values
        assert metrics["title_length"] == len("Test Title Here")
        assert metrics["body_length"] == len("This is the normalized body content.")
        assert 0.0 <= metrics["meta_completeness"] <= 1.0
        assert 0.0 <= metrics["content_completeness"] <= 1.0
        assert 0.0 <= metrics["noise_ratio"] <= 1.0

    def test_calculate_metrics_meta_completeness_full(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test meta_completeness = 1.0 when all metadata present."""
        valid_item.raw_metadata = {"author": "John", "tags": ["tag1"]}
        valid_item.published_at = datetime.now()

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # author + tags + published_at = 3 present out of 3 expected
        assert metrics["meta_completeness"] == 1.0

    def test_calculate_metrics_meta_completeness_partial(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test meta_completeness partial when some metadata missing."""
        valid_item.raw_metadata = {"author": "John"}  # No tags
        valid_item.published_at = datetime.now()

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # author + published_at = 2 present out of 3 expected (tags missing)
        assert 0.5 < metrics["meta_completeness"] < 1.0

    def test_calculate_metrics_content_completeness_high(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test content_completeness = 1.0 for long content."""
        valid_normalization_result.normalized_body = "x" * 600

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        assert metrics["content_completeness"] == 1.0

    def test_calculate_metrics_content_completeness_medium(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test content_completeness = 0.7 for medium content."""
        valid_normalization_result.normalized_body = "x" * 300

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        assert metrics["content_completeness"] == 0.7

    def test_calculate_metrics_content_completeness_low(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test content_completeness = 0.4 for short content."""
        valid_normalization_result.normalized_body = "x" * 100

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        assert metrics["content_completeness"] == 0.4

    def test_calculate_metrics_content_completeness_very_low(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test content_completeness = 0.2 for very short content."""
        valid_normalization_result.normalized_body = "x" * 30

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        assert metrics["content_completeness"] == 0.2

    def test_calculate_metrics_noise_ratio_clean(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio low for clean content."""
        valid_item.raw_content = "This is clean text content without HTML or ads."

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # Clean text should have low noise ratio
        assert metrics["noise_ratio"] < 0.1

    def test_calculate_metrics_noise_ratio_html(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio higher for HTML with ad markers."""
        valid_item.raw_content = """
        <html><body>
        <div class="ad">广告</div>
        <p>推荐阅读 other articles</p>
        <p>推广 content</p>
        <div>AD placement</div>
        <p>Actual content here.</p>
        </body></html>
        """

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # HTML with ad markers should have higher noise ratio
        assert metrics["noise_ratio"] > 0

    def test_calculate_metrics_empty_raw_content(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio handles empty raw_content."""
        valid_item.raw_content = None

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # Should handle None gracefully
        assert metrics["noise_ratio"] == 0.0


class TestQualityResult:
    """Tests for QualityResult dataclass."""

    def test_result_creation_pass(self):
        """Test creating a PASS QualityResult."""
        result = QualityResult(
            decision=QualityDecision.PASS,
            warnings=["Missing author"],
            metrics={"title_length": 10},
        )

        assert result.decision == QualityDecision.PASS
        assert result.rejection_reason is None
        assert result.warnings == ["Missing author"]
        assert result.metrics == {"title_length": 10}

    def test_result_creation_reject(self):
        """Test creating a REJECT QualityResult."""
        result = QualityResult(
            decision=QualityDecision.REJECT,
            warnings=[],
            metrics={},
            rejection_reason="Title too short",
        )

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason == "Title too short"


class TestQualityDecision:
    """Tests for QualityDecision enum."""

    def test_decision_values(self):
        """Test QualityDecision enum values."""
        assert QualityDecision.PASS == "pass"
        assert QualityDecision.REJECT == "reject"


class TestIntegration:
    """Integration tests for quality gate."""

    def test_full_quality_check_valid_item(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test full quality check for valid item passes."""
        valid_item.raw_content = """
        <html><body>
        <p>This is a good article with substantial content that should pass
        all quality checks and be accepted into the system.</p>
        <p>It has multiple paragraphs and good metadata.</p>
        </body></html>
        """
        # Body needs to be >= 200 chars for content_completeness >= 0.7
        valid_normalization_result.normalized_body = (
            "This is a good article with substantial content that should pass "
            "all quality checks and be accepted into the system. "
            "It has multiple paragraphs and good metadata. "
            "The article provides comprehensive analysis and detailed information "
            "about the subject matter, making it valuable for readers."
        )
        valid_item.raw_metadata = {
            "author": "Jane Doe",
            "tags": ["technology", "news", "analysis"],
        }

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.PASS
        assert result.warnings == []
        assert result.metrics["content_completeness"] >= 0.7
        assert result.metrics["meta_completeness"] == 1.0

    def test_full_quality_check_low_quality_item(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test full quality check for low quality item still passes (warnings only)."""
        valid_normalization_result.normalized_body = "Short"
        valid_item.raw_metadata = {}
        valid_item.raw_content = ""

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        # Should pass (quality gate does structural validation, not semantic)
        assert result.decision == QualityDecision.PASS
        assert len(result.warnings) > 0  # Has warnings
        assert result.metrics["content_completeness"] < 1.0

    def test_full_quality_check_invalid_item(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test full quality check for invalid item rejects."""
        valid_item.title = "AB"  # Too short
        valid_item.url = "not-a-url"
        valid_normalization_result.normalized_body = ""
        valid_item.published_at = None

        result = quality_gate_service.check(valid_item, valid_normalization_result)

        assert result.decision == QualityDecision.REJECT
        assert result.rejection_reason is not None