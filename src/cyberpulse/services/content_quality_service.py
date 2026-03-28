"""Content quality judgment service.

Determines if item content needs full fetch based on:
1. Content length threshold (< 100 chars)
2. Title-body similarity (Anthropic Research issue)
3. Invalid content patterns (JS challenge, 404, etc.)
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

MIN_CONTENT_LENGTH = 100
TITLE_SIMILARITY_THRESHOLD = 0.8

INVALID_CONTENT_PATTERNS = [
    "Please enable JavaScript",
    "Checking your browser",
    "404 Not Found",
    "Access Denied",
]


@dataclass
class QualityCheckResult:
    """Result of content quality check."""

    needs_full_fetch: bool
    reason: str


class ContentQualityService:
    """Service for checking content quality.

    Used in quality_check stage to determine if full fetch is needed.
    """

    def check_quality(
        self,
        title: str | None,
        body: str | None,
    ) -> QualityCheckResult:
        """Check if content needs full fetch.

        Args:
            title: Item title.
            body: Item body content.

        Returns:
            QualityCheckResult with needs_full_fetch flag and reason.
        """
        # Rule 1: Content length
        body_len = len(body or "")
        if body_len < MIN_CONTENT_LENGTH:
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=(
                    f"Content too short: {body_len} chars "
                    f"(min: {MIN_CONTENT_LENGTH})"
                ),
            )

        # Rule 2: Title-body similarity
        if self._is_title_as_body(title, body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=(
                    "Title-body similarity exceeds threshold "
                    "(possible extraction error)"
                ),
            )

        # Rule 3: Invalid content patterns
        if self._has_invalid_pattern(body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason="Content contains invalid pattern (JS challenge/error page)",
            )

        return QualityCheckResult(
            needs_full_fetch=False,
            reason="Content quality check passed",
        )

    def _is_title_as_body(self, title: str | None, body: str | None) -> bool:
        """Check if title was incorrectly extracted as body."""
        if not title or not body:
            return False

        similarity = SequenceMatcher(
            None,
            title.strip().lower(),
            body.strip().lower(),
        ).ratio()

        return similarity > TITLE_SIMILARITY_THRESHOLD

    def _has_invalid_pattern(self, body: str | None) -> bool:
        """Check if body contains invalid content pattern."""
        if not body:
            return False

        body_lower = body.lower()
        return any(
            pattern.lower() in body_lower for pattern in INVALID_CONTENT_PATTERNS
        )


def needs_full_fetch(item) -> bool:
    """Convenience function to check if item needs full fetch.

    Args:
        item: Item object with normalized_title and normalized_body attributes.

    Returns:
        True if item needs full fetch.
    """
    service = ContentQualityService()
    # Use normalized content if available, fallback to raw content
    title = getattr(item, "normalized_title", None) or getattr(
        item, "title", None
    )
    body = getattr(item, "normalized_body", None) or getattr(
        item, "raw_content", None
    )
    result = service.check_quality(
        title=title,
        body=body,
    )
    return result.needs_full_fetch
