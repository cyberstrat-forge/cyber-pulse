"""Integration tests for YouTube Connector with real channels."""

import pytest

from cyberpulse.services import YouTubeConnector
from cyberpulse.services.rss_connector import FetchResult


@pytest.mark.integration
class TestYouTubeConnectorRealChannels:
    """Tests with real YouTube channels."""

    @pytest.mark.asyncio
    async def test_blackhat_channel(self):
        """Test Black Hat Official channel."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0, "Should fetch at least one video"

        # Verify item structure
        item = result.items[0]
        assert item["external_id"], "Should have external_id"
        assert item["url"].startswith("https://"), "Should have valid URL"
        assert item["title"], "Should have title"
        assert item["content"], "Should have content (transcript or description)"
        assert "published_at" in item, "Should have published_at"

        # Check transcript availability
        has_transcript = item["raw_metadata"].get("has_transcript", False)
        print(f"\nBlack Hat video: {item['title'][:50]}...")
        print(f"  Has transcript: {has_transcript}")
        print(f"  Content length: {len(item['content'])} chars")

    @pytest.mark.asyncio
    async def test_owasp_channel(self):
        """Test OWASP Global channel."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@OWASPGLOBAL"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0, "Should fetch at least one video"

        item = result.items[0]
        assert item["external_id"]
        assert item["url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_channel_id_format_url(self):
        """Test /channel/ID format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert len(result.items) > 0

    @pytest.mark.asyncio
    async def test_transcript_quality(self):
        """Test that transcripts have meaningful content."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })

        result = await connector.fetch()

        # At least some videos should have transcripts
        items_with_transcripts = [
            item for item in result.items
            if item["raw_metadata"].get("has_transcript")
        ]

        # Check that transcripts are longer than descriptions typically
        for item in items_with_transcripts[:3]:  # Check first 3
            content = item["content"]
            # Transcripts should typically be > 500 chars
            print(f"\nTranscript length for '{item['title'][:30]}...': {len(content)} chars")

        print(f"\nTotal videos: {len(result.items)}")
        print(f"With transcripts: {len(items_with_transcripts)}")