"""Tests for TranscriptExtractor."""

import pytest

from cyberpulse.services.transcript_extractor import TranscriptExtractor, TranscriptResult


class TestTranscriptResult:
    """Tests for TranscriptResult dataclass."""

    def test_success_result(self):
        """Test successful result creation."""
        result = TranscriptResult(
            success=True,
            text="This is a transcript.",
            lines=[{"timestamp": "0:00", "text": "This is a transcript."}],
        )

        assert result.success is True
        assert result.text == "This is a transcript."
        assert result.lines is not None
        assert len(result.lines) == 1
        assert result.error is None

    def test_failure_result(self):
        """Test failure result creation."""
        result = TranscriptResult(
            success=False,
            error="No transcript button found",
        )

        assert result.success is False
        assert result.text is None
        assert result.lines is None
        assert result.error == "No transcript button found"


class TestTranscriptExtractor:
    """Tests for TranscriptExtractor initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        extractor = TranscriptExtractor()

        assert extractor.headless is True
        assert extractor.timeout == 60
        assert extractor.user_data_dir == "/tmp/playwright_yt_data"

    def test_custom_initialization(self):
        """Test custom initialization."""
        extractor = TranscriptExtractor(
            headless=False,
            timeout=120,
            user_data_dir="/custom/path",
        )

        assert extractor.headless is False
        assert extractor.timeout == 120
        assert extractor.user_data_dir == "/custom/path"


class TestTranscriptExtractorIntegration:
    """Integration tests for transcript extraction.

    These tests require Playwright to be installed and a network connection.
    Marked with @pytest.mark.integration to allow skipping in CI environments.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_success(self):
        """Test successful transcript extraction from a video with subtitles.

        Uses Rick Astley's "Never Gonna Give You Up" - a stable video with
        subtitles that has been available for many years.
        """
        extractor = TranscriptExtractor(headless=True, timeout=60)

        result = await extractor.extract(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        assert result.success is True
        assert result.text is not None
        assert len(result.text) > 100
        assert result.lines is not None
        assert len(result.lines) > 0
        assert result.error is None

        # Verify transcript content has expected structure
        for line in result.lines:
            assert "timestamp" in line
            assert "text" in line
            assert line["text"].strip() != ""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_no_subtitles(self):
        """Test video without proper subtitles.

        Note: YouTube's transcript availability changes over time.
        This test verifies the extractor handles various scenarios gracefully.
        """
        extractor = TranscriptExtractor(headless=True, timeout=60)

        # Try a video - availability may vary
        result = await extractor.extract(
            "https://www.youtube.com/watch?v=y-CSDxMMXb0"
        )

        # Should either succeed with transcript or fail gracefully
        # Both outcomes are valid - we're testing the API contract
        if result.success:
            # If it succeeded, verify the result structure
            assert result.text is not None
            assert result.lines is not None
        else:
            # If it failed, should have an error message
            assert result.error is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_long_video(self):
        """Test transcript extraction from a longer video.

        Uses a Black Hat conference talk (~50 minutes) to verify
        the extractor handles longer content correctly.
        """
        extractor = TranscriptExtractor(headless=True, timeout=90)

        result = await extractor.extract(
            "https://www.youtube.com/watch?v=KPlP_pio1ms"
        )

        assert result.success is True
        assert result.text is not None
        assert len(result.text) > 10000  # Long video should have substantial transcript
        assert result.lines is not None
        assert len(result.lines) > 100  # Should have many lines

    @pytest.mark.asyncio
    async def test_extract_transcript_invalid_url(self):
        """Test with invalid video URL.

        Should handle gracefully without crashing.
        """
        extractor = TranscriptExtractor(headless=True, timeout=30)

        # Invalid video ID
        result = await extractor.extract(
            "https://www.youtube.com/watch?v=invalidvideo12345"
        )

        # Should handle gracefully - either fail or return no content
        assert result.success is False or result.text is None or result.text == ""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_transcript_with_headless_false(self):
        """Test that headless=False works (for debugging purposes).

        Note: In CI environments, this may fail if no display is available.
        """
        # Skip if no display available (common in CI)
        import os

        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            pytest.skip("No display available for non-headless mode")

        extractor = TranscriptExtractor(headless=False, timeout=60)

        result = await extractor.extract(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        assert result.success is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_extractions(self):
        """Test multiple consecutive extractions.

        Verifies that the extractor can be reused without issues.
        """
        extractor = TranscriptExtractor(headless=True, timeout=60)

        # First extraction
        result1 = await extractor.extract(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert result1.success is True

        # Second extraction
        result2 = await extractor.extract(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        assert result2.success is True

        # Results should be consistent
        assert len(result1.text or "") > 0
        assert len(result2.text or "") > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_short_video_with_transcript(self):
        """Test extraction from a short video with transcript.

        Some very short videos might have different UI behavior.
        """
        extractor = TranscriptExtractor(headless=True, timeout=60)

        # YouTube Shorts or very short videos
        result = await extractor.extract(
            "https://www.youtube.com/watch?v=8voNmYCUXSk"
        )

        # Should either succeed with transcript or fail gracefully
        if result.success:
            assert result.text is not None
            assert len(result.text) > 0
        else:
            assert result.error is not None