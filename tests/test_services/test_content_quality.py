"""Tests for ContentQualityService."""


from cyberpulse.services.content_quality_service import (
    MIN_CONTENT_LENGTH,
    ContentQualityService,
    needs_full_fetch,
)


class TestContentQualityService:
    """Test cases for content quality judgment."""

    def test_min_content_length_constant(self):
        """Test MIN_CONTENT_LENGTH is 100."""
        assert MIN_CONTENT_LENGTH == 100

    def test_short_content_needs_fetch(self):
        """Test content < 100 chars needs full fetch."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Test Title",
            body="Short content here",
        )
        assert result.needs_full_fetch is True
        assert "too short" in result.reason.lower()

    def test_long_content_passes(self):
        """Test content >= 100 chars passes."""
        service = ContentQualityService()
        body = (
            "This is a long enough content that should pass the "
            "minimum length check of one hundred characters exactly!"
        )
        result = service.check_quality(
            title="Test Title",
            body=body,
        )
        assert result.needs_full_fetch is False

    def test_title_as_body_detection(self):
        """Test title-body similarity detection."""
        service = ContentQualityService()
        # Both title and body are >= 100 chars and highly similar (>80%)
        # This simulates the real case where title was incorrectly extracted
        title = (
            "Anthropic Research Alignment Faking in Large Language Models "
            "Summary Report Detailed Analysis Complete"
        )
        body = (
            "Anthropic Research Alignment Faking in Large Language Models "
            "Summary Report Detailed Analysis Complete"
        )
        result = service.check_quality(
            title=title,
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "title" in result.reason.lower()

    def test_invalid_content_pattern(self):
        """Test invalid content patterns."""
        service = ContentQualityService()
        # Body has 100+ chars and contains invalid pattern
        body = (
            "Please enable JavaScript to continue viewing this page. "
            "This page requires JavaScript to work properly."
        )
        result = service.check_quality(
            title="Test",
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "invalid" in result.reason.lower()

    def test_multiple_patterns_covered(self):
        """Test multiple invalid patterns."""
        patterns = [
            (
                "Checking your browser before accessing the site. "
                "This is a security check that verifies your connection."
            ),
            (
                "404 Not Found - The requested page could not be found "
                "on this server. Please check the URL and try again."
            ),
            (
                "Access Denied - You do not have permission to access "
                "this resource. Contact administrator for help."
            ),
        ]
        service = ContentQualityService()
        for pattern in patterns:
            result = service.check_quality(
                title="Test",
                body=pattern,
            )
            assert result.needs_full_fetch is True


class TestNeedsFullFetchFunction:
    """Test cases for needs_full_fetch convenience function."""

    def test_with_item_mock(self):
        """Test with Item-like object."""
        from unittest.mock import MagicMock

        item = MagicMock()
        item.raw_title = "Test Title"
        item.raw_body = "Short"

        assert needs_full_fetch(item) is True

    def test_with_none_values(self):
        """Test with None title/body."""
        from unittest.mock import MagicMock

        item = MagicMock()
        item.raw_title = None
        item.raw_body = None

        assert needs_full_fetch(item) is True


class TestContentQualityWithRealPatterns:
    """Test content quality rules against real problematic patterns."""

    def test_anthropic_title_as_body_pattern(self):
        """Test detection of Anthropic-style title-as-body issue."""
        service = ContentQualityService()

        # Simulate Anthropic Research issue: title extracted as body
        result = service.check_quality(
            title="Alignment Faking in Large Language Models",
            body="Alignment Faking in Large Language Models",  # Same as title
        )
        assert result.needs_full_fetch is True

    def test_paulgraham_short_content(self):
        """Test detection of short content (RSS summary only)."""
        service = ContentQualityService()

        # paulgraham.com RSS often has no content
        result = service.check_quality(
            title="Superlinear Returns",
            body="A short summary from RSS feed",  # < 100 chars
        )
        assert result.needs_full_fetch is True

    def test_cloudflare_challenge_content(self):
        """Test detection of Cloudflare challenge page content."""
        service = ContentQualityService()

        # Cloudflare challenge response
        result = service.check_quality(
            title="Article Title",
            body="Please enable JavaScript to continue. Checking your browser...",
        )
        assert result.needs_full_fetch is True
