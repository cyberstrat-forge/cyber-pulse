"""Quality gate service for content validation."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyberpulse.models.item import Item
    from cyberpulse.services.normalization_service import NormalizationResult


class QualityDecision(str, Enum):
    """Quality gate decision."""

    PASS = "pass"
    REJECT = "reject"


@dataclass(frozen=True)
class QualityResult:
    """Result of quality check."""

    decision: QualityDecision
    warnings: list[str]
    metrics: dict[str, float]
    rejection_reason: str | None = None


class QualityGateService:
    """Service for quality control.

    This service validates Items after normalization, checking:
    - Required fields: published_at, title, normalized_body, url
    - Optional fields: author (produces warning if missing)

    Quality gate performs structural validation only, not semantic analysis.
    """

    # Core field requirements
    REQUIRED_FIELDS = {
        "published_at": {"check": "valid_date", "message": "Invalid or missing date"},
        "title": {"check": "min_length_5", "message": "Title too short"},
        "normalized_body": {"check": "non_empty", "message": "Empty body"},
        "url": {"check": "valid_url", "message": "Invalid URL"},
    }

    # Optional field warnings
    OPTIONAL_FIELDS = {
        "author": {"message": "Missing author"},
    }

    # Date validation bounds
    MIN_YEAR = 2000
    MAX_FUTURE_DAYS = 2  # Allow some clock skew

    # Content completeness thresholds
    BODY_LENGTH_HIGH = 500  # >= 500 chars: 1.0
    BODY_LENGTH_MEDIUM = 200  # >= 200 chars: 0.7
    BODY_LENGTH_LOW = 50  # >= 50 chars: 0.4
    # < 50 chars: 0.2

    # Content quality thresholds
    TITLE_BODY_SIMILARITY_THRESHOLD = 0.95  # If title-body similarity >= this, content is suspect
    MIN_BODY_LENGTH = 50  # Minimum body length for valid content

    # Title date pattern (e.g., "Dec 18, 2024" or "Jan 15, 2024")
    TITLE_DATE_PATTERN = re.compile(
        r"\b[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4}\b"
    )

    def check(
        self,
        item,
        normalization_result,
    ) -> QualityResult:
        """Check item quality.

        Validates required fields, checks optional fields for warnings,
        and calculates quality metrics.

        Args:
            item: Item model instance with fields: title, url, published_at,
                  raw_metadata, raw_content
            normalization_result: NormalizationResult with normalized_title,
                                 normalized_body, etc.

        Returns:
            QualityResult with decision, warnings, and metrics
        """
        # Validate required fields
        errors = self._validate_required_fields(item, normalization_result)

        # Check optional fields
        warnings = self._check_optional_fields(item)

        # Calculate metrics
        metrics = self._calculate_metrics(item, normalization_result)

        # Make decision
        if errors:
            return QualityResult(
                decision=QualityDecision.REJECT,
                warnings=warnings,
                metrics=metrics,
                rejection_reason="; ".join(errors),
            )

        return QualityResult(
            decision=QualityDecision.PASS,
            warnings=warnings,
            metrics=metrics,
        )

    def _validate_required_fields(
        self, item: "Item", norm: "NormalizationResult"
    ) -> list[str]:
        """Validate required fields, return list of errors.

        Args:
            item: Item model instance
            norm: NormalizationResult instance

        Returns:
            List of error messages for failed validations
        """
        errors = []

        # Validate published_at
        if not self._is_valid_date(item.published_at):
            errors.append(self.REQUIRED_FIELDS["published_at"]["message"])

        # Validate title (from item, check min length 5)
        if not item.title or len(item.title.strip()) < 5:
            errors.append(self.REQUIRED_FIELDS["title"]["message"])

        # Validate normalized_body (from norm result, check non-empty)
        if not norm.normalized_body or not norm.normalized_body.strip():
            errors.append(self.REQUIRED_FIELDS["normalized_body"]["message"])

        # Validate url
        if not self._is_valid_url(item.url):
            errors.append(self.REQUIRED_FIELDS["url"]["message"])

        return errors

    def _check_optional_fields(self, item: "Item") -> list[str]:
        """Check optional fields, return list of warnings.

        Args:
            item: Item model instance

        Returns:
            List of warning messages for missing optional fields
        """
        warnings = []

        # Check author in raw_metadata
        raw_metadata = item.raw_metadata or {}
        if not raw_metadata.get("author"):
            warnings.append(self.OPTIONAL_FIELDS["author"]["message"])

        return warnings

    def _calculate_metrics(
        self, item: "Item", norm: "NormalizationResult"
    ) -> dict[str, float]:
        """Calculate quality metrics.

        Metrics calculated:
        - title_length: Title character count
        - body_length: Body character count
        - word_count: Word count (from NormalizationResult)
        - meta_completeness: Metadata completeness score (0-1)
        - content_completeness: Content quality score (0-1)

        Args:
            item: Item model instance
            norm: NormalizationResult instance

        Returns:
            Dictionary of metric name to value
        """
        metrics = {}

        # Title length
        metrics["title_length"] = float(len(norm.normalized_title or ""))

        # Body length
        body = norm.normalized_body or ""
        metrics["body_length"] = float(len(body))

        # Word count (from normalization result)
        metrics["word_count"] = float(norm.word_count or 0)

        # Meta completeness (author, tags, published_at)
        metrics["meta_completeness"] = self._calculate_meta_completeness(item)

        # Content completeness (based on body length)
        metrics["content_completeness"] = self._calculate_content_completeness(body)

        return metrics

    def _is_valid_date(self, date_value) -> bool:
        """Check if date is valid and within reasonable range.

        Args:
            date_value: Date to validate

        Returns:
            True if date is valid, False otherwise
        """
        if date_value is None:
            return False

        if not isinstance(date_value, datetime):
            return False

        # Check year is not too old
        if date_value.year < self.MIN_YEAR:
            return False

        # Check date is not too far in the future
        max_future = datetime.now().replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) + timedelta(days=self.MAX_FUTURE_DAYS)

        if date_value > max_future:
            return False

        return True

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid.

        Args:
            url: URL string to validate

        Returns:
            True if URL is valid, False otherwise
        """
        if not url:
            return False

        # Basic URL pattern check
        url_pattern = re.compile(
            r"^https?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
            r"localhost|"  # localhost
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        return bool(url_pattern.match(url))

    def _calculate_meta_completeness(self, item) -> float:
        """Calculate metadata completeness score.

        Checks for presence of: author, tags, published_at

        Args:
            item: Item model instance

        Returns:
            Completeness score between 0 and 1
        """
        raw_metadata = item.raw_metadata or {}

        fields_present = 0
        total_fields = 3

        # Check author
        if raw_metadata.get("author"):
            fields_present += 1

        # Check tags
        if raw_metadata.get("tags"):
            fields_present += 1

        # Check published_at (already validated in required fields)
        if item.published_at is not None:
            fields_present += 1

        return fields_present / total_fields

    def _calculate_content_completeness(self, body: str) -> float:
        """Calculate content completeness score based on body length.

        - body_length >= 500 chars: 1.0
        - body_length >= 200 chars: 0.7
        - body_length >= 50 chars: 0.4
        - body_length < 50 chars: 0.2

        Args:
            body: Normalized body text

        Returns:
            Completeness score between 0 and 1
        """
        body_length = len(body or "")

        if body_length >= self.BODY_LENGTH_HIGH:
            return 1.0
        elif body_length >= self.BODY_LENGTH_MEDIUM:
            return 0.7
        elif body_length >= self.BODY_LENGTH_LOW:
            return 0.4
        else:
            return 0.2

    def _validate_content_quality(
        self, title: str, body: str
    ) -> tuple[bool, str | None]:
        """Validate content quality beyond structural checks.

        Checks for:
        - Title-body similarity (if title is same as body, content is suspect)
        - Minimum body length
        - Title containing only a date (common in malformed RSS feeds)

        Args:
            title: Item title
            body: Normalized body text

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        if not body or len(body.strip()) < self.MIN_BODY_LENGTH:
            return False, "Body content below minimum length"

        # Check if title and body are essentially the same
        if self._is_title_body_same(title, body):
            return False, "Title and body are identical or near-identical"

        # Check if title is just a date (malformed RSS)
        if title:
            clean_title = self.TITLE_DATE_PATTERN.sub("", title).strip()
            if not clean_title:
                return False, "Title contains only date information"

        return True, None

    def _is_title_body_same(self, title: str, body: str) -> bool:
        """Check if title and body are essentially the same content.

        Uses a simple similarity check: if one contains the other at high
        percentage, they're considered the same.

        Args:
            title: Item title
            body: Normalized body text

        Returns:
            True if title and body are near-identical
        """
        if not title or not body:
            return False

        # Normalize both for comparison
        title_norm = title.lower().strip()
        body_norm = body.lower().strip()

        # Exact match
        if title_norm == body_norm:
            return True

        # Check if body starts with title (common in malformed feeds)
        if body_norm.startswith(title_norm):
            remaining = body_norm[len(title_norm):].strip()
            # If remaining content is minimal (just a few chars), treat as same
            if len(remaining) < 5:
                return True

        # Calculate Jaccard similarity for word sets
        title_words = set(title_norm.split())
        body_words = set(body_norm.split())

        if not title_words or not body_words:
            return False

        intersection = len(title_words & body_words)
        union = len(title_words | body_words)

        if union == 0:
            return False

        similarity = intersection / union

        return similarity >= self.TITLE_BODY_SIMILARITY_THRESHOLD
