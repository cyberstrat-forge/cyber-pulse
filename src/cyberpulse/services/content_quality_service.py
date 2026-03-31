"""Content quality judgment service.

Determines if item content needs full fetch based on:
1. Content length threshold (< 500 chars or < 50 words)
2. Title-body similarity (Anthropic Research issue)
3. Invalid content patterns (JS challenge, 404, etc.)

Note: RSS feeds typically provide 100-300 character summaries.
Real article content is usually > 500 characters and > 50 words.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

# Minimum content thresholds
# RSS summaries are typically 100-300 chars, 10-30 words
# Real articles are typically > 500 chars, > 50 words
MIN_CONTENT_LENGTH = 500  # characters
MIN_WORD_COUNT = 50  # words

TITLE_SIMILARITY_THRESHOLD = 0.8

INVALID_CONTENT_PATTERNS = [
    "Please enable JavaScript",
    "Checking your browser",
    "404 Not Found",
    "Access Denied",
    "error 403: Forbidden",
    "Warning: Target URL returned error",
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
        # Rule 1: Content length (characters)
        body_len = len(body or "")
        if body_len < MIN_CONTENT_LENGTH:
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=(
                    f"Content too short: {body_len} chars "
                    f"(min: {MIN_CONTENT_LENGTH})"
                ),
            )

        # Rule 2: Word count (more reliable for RSS summaries)
        word_count = self._count_words(body)
        if word_count < MIN_WORD_COUNT:
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=(
                    f"Content too short: {word_count} words "
                    f"(min: {MIN_WORD_COUNT}) - likely RSS summary"
                ),
            )

        # Rule 3: Title-body similarity
        if self._is_title_as_body(title, body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason=(
                    "Title-body similarity exceeds threshold "
                    "(possible extraction error)"
                ),
            )

        # Rule 4: Invalid content patterns
        if self._has_invalid_pattern(body):
            return QualityCheckResult(
                needs_full_fetch=True,
                reason="Content contains invalid pattern (JS challenge/error page)",
            )

        return QualityCheckResult(
            needs_full_fetch=False,
            reason="Content quality check passed",
        )

    def _count_words(self, text: str | None) -> int:
        """Count words in text.

        Args:
            text: Text to count words in.

        Returns:
            Number of words.
        """
        if not text:
            return 0
        # Split on whitespace and filter empty strings
        return len([w for w in text.split() if w])

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
