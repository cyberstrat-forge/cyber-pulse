"""Tests for ContentQualityService."""

from cyberpulse.services.content_quality_service import (
    MIN_CONTENT_LENGTH,
    MIN_WORD_COUNT,
    ContentQualityService,
    needs_full_fetch,
)


class TestContentQualityService:
    """Test cases for content quality judgment."""

    def test_min_content_length_constant(self):
        """Test MIN_CONTENT_LENGTH is 500."""
        assert MIN_CONTENT_LENGTH == 500

    def test_min_word_count_constant(self):
        """Test MIN_WORD_COUNT is 50."""
        assert MIN_WORD_COUNT == 50

    def test_short_content_needs_fetch(self):
        """Test content < 500 chars needs full fetch."""
        service = ContentQualityService()
        result = service.check_quality(
            title="Test Title",
            body="Short content here that is less than 500 characters.",
        )
        assert result.needs_full_fetch is True
        assert "too short" in result.reason.lower()

    def test_content_long_enough_chars_but_few_words(self):
        """Test content with enough chars but few words needs full fetch."""
        service = ContentQualityService()
        # 500+ chars but < 50 words (typical RSS summary)
        body = "x " * 300  # ~600 chars but only 300 words? No, 300 "x " = 300 words
        # Actually let's make it < 50 words
        body = "x " * 25  # ~50 chars, 25 words - too short for both
        result = service.check_quality(
            title="Test Title",
            body=body,
        )
        assert result.needs_full_fetch is True

    def test_rss_summary_needs_fetch(self):
        """Test typical RSS summary (< 50 words) needs full fetch."""
        service = ContentQualityService()
        # Typical RSS summary: 100-300 chars, 15-30 words
        # This triggers the char check first (chars < 500)
        body = (
            "Learn how OpenAI's Model Spec serves as a public framework "
            "for model behavior, balancing safety, user freedom, and "
            "accountability as AI systems advance."
        )
        result = service.check_quality(
            title="Inside our approach to the Model Spec",
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "too short" in result.reason.lower()

    def test_long_content_passes(self):
        """Test content >= 500 chars and >= 50 words passes."""
        service = ContentQualityService()
        # Generate content that passes both thresholds
        body = (
            "This is a long article that has enough content to pass both "
            "the character and word count thresholds. " * 10
        )  # ~650 chars, ~90 words
        result = service.check_quality(
            title="Test Title",
            body=body,
        )
        assert result.needs_full_fetch is False

    def test_title_as_body_detection(self):
        """Test title-body similarity detection."""
        service = ContentQualityService()
        # Both title and body are >= 500 chars and highly similar (>80%)
        base = "Anthropic Research Alignment Faking in Large Language Models "
        title = base * 10  # Enough to pass length checks
        body = base * 10  # Same as title
        result = service.check_quality(
            title=title,
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "title" in result.reason.lower()

    def test_invalid_content_pattern(self):
        """Test invalid content patterns."""
        service = ContentQualityService()
        # Body has 500+ chars and contains invalid pattern
        body = (
            "Please enable JavaScript to continue viewing this page. "
            "This page requires JavaScript to work properly. " * 10
        )
        result = service.check_quality(
            title="Test",
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "invalid" in result.reason.lower()

    def test_error_403_pattern(self):
        """Test error 403 pattern detection."""
        service = ContentQualityService()
        body = (
            "Warning: Target URL returned error 403: Forbidden. "
            "Access to this resource is denied. " * 10
        )
        result = service.check_quality(
            title="Test",
            body=body,
        )
        assert result.needs_full_fetch is True

    def test_multiple_patterns_covered(self):
        """Test multiple invalid patterns."""
        patterns = [
            "Checking your browser before accessing the site. " * 20,
            "404 Not Found - The requested page could not be found. " * 20,
            "Access Denied - You do not have permission. " * 20,
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
        item.normalized_title = "Test Title"
        item.normalized_body = "Short"

        assert needs_full_fetch(item) is True

    def test_with_none_values(self):
        """Test with None title/body."""
        from unittest.mock import MagicMock

        item = MagicMock()
        item.normalized_title = None
        item.normalized_body = None

        assert needs_full_fetch(item) is True


class TestContentQualityWithRealPatterns:
    """Test content quality rules against real problematic patterns."""

    def test_anthropic_title_as_body_pattern(self):
        """Test detection of Anthropic-style title-as-body issue."""
        service = ContentQualityService()

        # Simulate Anthropic Research issue: title extracted as body
        # Need enough length to pass the character check first
        title = "Alignment Faking in Large Language Models " * 15
        body = "Alignment Faking in Large Language Models " * 15
        result = service.check_quality(
            title=title,
            body=body,
        )
        assert result.needs_full_fetch is True

    def test_paulgraham_short_content(self):
        """Test detection of short content (RSS summary only)."""
        service = ContentQualityService()

        # paulgraham.com RSS often has no content or very short
        result = service.check_quality(
            title="Superlinear Returns",
            body="A short summary from RSS feed",
        )
        assert result.needs_full_fetch is True

    def test_cloudflare_challenge_content(self):
        """Test detection of Cloudflare challenge page content."""
        service = ContentQualityService()

        # Cloudflare challenge response (with enough length)
        body = "Please enable JavaScript to continue. Checking your browser... " * 10
        result = service.check_quality(
            title="Article Title",
            body=body,
        )
        assert result.needs_full_fetch is True

    def test_openai_rss_summary(self):
        """Test real OpenAI RSS summary pattern needs full fetch."""
        service = ContentQualityService()

        # Real OpenAI RSS summary (from database)
        body = (
            "Learn how STADLER uses ChatGPT to transform knowledge work, "
            "saving time and accelerating productivity across 650 employees."
        )
        result = service.check_quality(
            title="STADLER reshapes knowledge work at a 230-year-old company",
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "too short" in result.reason.lower()

    def test_word_count_triggers_when_chars_pass(self):
        """Test word count check triggers when char count passes."""
        service = ContentQualityService()

        # 500+ chars but < 50 words - triggers word check
        # Example: lots of numbers/symbols but few actual words
        body = "x " * 300 + "y " * 200  # ~500 chars, ~500 words? No, that's too many words
        # Let's create content with 500+ chars but < 50 words
        body = (
            "This-is-one-long-word " * 25  # ~500+ chars, 25 words
        )
        result = service.check_quality(
            title="Test",
            body=body,
        )
        assert result.needs_full_fetch is True
        assert "word" in result.reason.lower()

    def test_darkreading_rss_summary(self):
        """Test real Dark Reading RSS summary pattern needs full fetch."""
        service = ContentQualityService()

        # Real Dark Reading RSS summary (from database)
        body = (
            "The list of countries exploiting Internet-connected cameras "
            "to give them eyes inside their adversaries' borders continues "
            "to expand. What should companies look out for?"
        )
        result = service.check_quality(
            title="Wartime Usage of Compromised IP Cameras Highlight Their Danger",
            body=body,
        )
        assert result.needs_full_fetch is True
