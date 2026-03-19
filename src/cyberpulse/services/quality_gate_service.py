"""Quality gate service for content validation."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from cyberpulse.models.item import Item
    from cyberpulse.services.normalization_service import NormalizationResult


class QualityDecision(str, Enum):
    """Quality gate decision."""

    PASS = "pass"
    REJECT = "reject"


@dataclass
class QualityResult:
    """Result of quality check."""

    decision: QualityDecision
    warnings: List[str]
    metrics: Dict[str, float]
    rejection_reason: Optional[str] = None


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

    # Noise ratio ad markers (Chinese and English)
    AD_MARKERS = [
        "广告",
        "推广",
        "推荐阅读",
        "AD",
        "advertisement",
        "sponsored",
        "赞助",
        "合作",
    ]

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
    ) -> List[str]:
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

    def _check_optional_fields(self, item: "Item") -> List[str]:
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
    ) -> Dict[str, float]:
        """Calculate quality metrics.

        Metrics calculated:
        - title_length: Title character count
        - body_length: Body character count
        - word_count: Word count (from NormalizationResult)
        - meta_completeness: Metadata completeness score (0-1)
        - content_completeness: Content quality score (0-1)
        - noise_ratio: Estimated noise in content (0-1)

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

        # Noise ratio (based on raw_content)
        metrics["noise_ratio"] = self._calculate_noise_ratio(item.raw_content)

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

    def _calculate_noise_ratio(self, raw_content: Optional[str]) -> float:
        """Calculate estimated noise ratio in content.

        Formula: (estimated_html_tags + ad_markers) / total_chars

        For clean content after normalization: typically < 0.1

        Args:
            raw_content: Raw HTML content before normalization

        Returns:
            Noise ratio between 0 and 1
        """
        if not raw_content:
            return 0.0

        total_chars = len(raw_content)
        if total_chars == 0:
            return 0.0

        # Count HTML tags using regex
        html_tags = re.findall(r"<[^>]+>", raw_content)
        html_tag_count = len(html_tags)

        # Count ad markers
        ad_marker_count = 0
        content_lower = raw_content.lower()
        for marker in self.AD_MARKERS:
            ad_marker_count += content_lower.count(marker.lower())

        # Calculate noise ratio
        noise_score = html_tag_count + ad_marker_count
        ratio = noise_score / total_chars

        # Cap at 1.0
        return min(ratio, 1.0)