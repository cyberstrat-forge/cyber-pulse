"""Tests for YouTube Connector."""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from cyberpulse.services import ConnectorError, YouTubeConnector
from cyberpulse.services.rss_connector import FetchResult


class MockFeedEntry(dict):
    """Mock feed entry that supports both dict and attribute access."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class TestYouTubeConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid_handle_url(self):
        """Test validation passes with @Handle format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@BlackHatOfficialYT"
        })
        assert connector.validate_config() is True

    def test_validate_config_valid_channel_id_url(self):
        """Test validation passes with /channel/ID format URL."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })
        assert connector.validate_config() is True

    def test_validate_config_missing_channel_url(self):
        """Test validation fails when channel_url is missing."""
        connector = YouTubeConnector({})
        with pytest.raises(ValueError, match="requires 'channel_url'"):
            connector.validate_config()

    def test_validate_config_empty_channel_url(self):
        """Test validation fails when channel_url is empty."""
        connector = YouTubeConnector({"channel_url": ""})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_non_youtube_domain(self):
        """Test validation fails for non-YouTube domain."""
        connector = YouTubeConnector({
            "channel_url": "https://vimeo.com/somechannel"
        })
        with pytest.raises(ValueError, match="domain must be youtube.com"):
            connector.validate_config()

    def test_validate_config_mobile_youtube_domain(self):
        """Test validation passes for m.youtube.com domain."""
        connector = YouTubeConnector({
            "channel_url": "https://m.youtube.com/@SomeChannel"
        })
        assert connector.validate_config() is True


class TestYouTubeConnectorResolveChannelUrl:
    """Tests for _resolve_channel_url method."""

    @pytest.mark.asyncio
    async def test_resolve_channel_id_format(self):
        """Test /channel/ID format resolves directly."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        rss_url = await connector._resolve_channel_url(
            "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        )

        assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCJ6q9Ie29ajGqKApbLqfBOg"

    @pytest.mark.asyncio
    async def test_resolve_handle_format(self):
        """Test /@Handle format resolves via _fetch_channel_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch.object(connector, "_fetch_channel_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "UCXXXXXX"

            rss_url = await connector._resolve_channel_url(
                "https://www.youtube.com/@TestChannel"
            )

            assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCXXXXXX"
            mock_fetch.assert_called_once_with("https://www.youtube.com/@TestChannel")

    @pytest.mark.asyncio
    async def test_resolve_user_format(self):
        """Test /user/Username format resolves via _fetch_channel_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/user/TestUser"
        })

        with patch.object(connector, "_fetch_channel_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "UCYYYYYY"

            rss_url = await connector._resolve_channel_url(
                "https://www.youtube.com/user/TestUser"
            )

            assert rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCYYYYYY"


class TestYouTubeConnectorFetchChannelId:
    """Tests for _fetch_channel_id method."""

    @pytest.mark.asyncio
    async def test_fetch_channel_id_from_cache(self):
        """Test cached channel_id is returned without HTTP request."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel",
            "resolved_channel_id": "UCCACHED"
        })

        channel_id = await connector._fetch_channel_id(
            "https://www.youtube.com/@TestChannel"
        )

        assert channel_id == "UCCACHED"

    @pytest.mark.asyncio
    async def test_fetch_channel_id_from_html(self):
        """Test channel_id extracted from HTML page."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        mock_html = '<script>"channelId":"UCFROMHTML123"</script>'
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            channel_id = await connector._fetch_channel_id(
                "https://www.youtube.com/@TestChannel"
            )

        assert channel_id == "UCFROMHTML123"

    @pytest.mark.asyncio
    async def test_fetch_channel_id_not_found(self):
        """Test ConnectorError when channel_id cannot be extracted."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@InvalidChannel"
        })

        mock_response = MagicMock()
        mock_response.text = "<html>No channel ID here</html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with pytest.raises(ConnectorError, match="Could not extract channel_id"):
                await connector._fetch_channel_id(
                    "https://www.youtube.com/@InvalidChannel"
                )


class TestYouTubeConnectorParseVideoEntry:
    """Tests for _parse_video_entry method."""

    def test_parse_video_entry_basic(self):
        """Test basic video entry parsing."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            yt_videoid="video123",
            link="https://www.youtube.com/watch?v=video123",
            title="Test Video",
            summary="Video description",
            published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
            author="Test Channel",
        )

        result = connector._parse_video_entry(entry)

        assert result is not None
        assert result["video_id"] == "video123"
        assert result["url"] == "https://www.youtube.com/watch?v=video123"
        assert result["title"] == "Test Video"
        assert result["description"] == "Video description"
        assert result["author"] == "Test Channel"

    def test_parse_video_entry_without_link(self):
        """Test entry without link generates URL from video_id."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            yt_videoid="video456",
            link=None,
            title="Video Without Link",
            summary="Description",
            published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
        )

        result = connector._parse_video_entry(entry)

        assert result is not None
        assert result["url"] == "https://www.youtube.com/watch?v=video456"

    def test_parse_video_entry_without_video_id(self):
        """Test entry without video_id returns None."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            title="No Video ID",
            summary="Description",
        )

        result = connector._parse_video_entry(entry)

        assert result is None


class TestYouTubeConnectorParseDate:
    """Tests for _parse_date method."""

    def test_parse_date_from_published_parsed(self):
        """Test parsing date from published_parsed field."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry(
            published_parsed=time.struct_time((2024, 3, 15, 14, 30, 0, 0, 75, 0))
        )

        result = connector._parse_date(entry)

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.tzinfo == UTC

    def test_parse_date_fallback_to_current_time(self):
        """Test missing date falls back to current UTC time."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        entry = MockFeedEntry()

        before = datetime.now(UTC)
        result = connector._parse_date(entry)
        after = datetime.now(UTC)

        assert before <= result <= after
        assert result.tzinfo == UTC


class TestYouTubeConnectorFetchVideoList:
    """Tests for _fetch_video_list method."""

    def _create_mock_response(self, content: bytes = b"", url: str = "https://www.youtube.com/feeds/videos.xml?channel_id=test"):
        """Create a mock httpx response."""
        mock_response = MagicMock()
        mock_response.content = content
        mock_response.url = url
        mock_response.history = []
        mock_response.raise_for_status = MagicMock()
        return mock_response

    @pytest.mark.asyncio
    async def test_fetch_video_list_success(self):
        """Test successful video list fetch."""
        mock_response = self._create_mock_response(b"<rss></rss>")

        mock_feed_result = {
            "entries": [
                MockFeedEntry(
                    yt_videoid="vid1",
                    link="https://www.youtube.com/watch?v=vid1",
                    title="Video 1",
                    summary="Description 1",
                    published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
                )
            ],
            "bozo": False,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                connector = YouTubeConnector({
                    "channel_url": "https://www.youtube.com/@TestChannel"
                })
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

        assert isinstance(result, FetchResult)
        assert len(result.items) == 1
        assert result.items[0]["video_id"] == "vid1"

    @pytest.mark.asyncio
    async def test_fetch_video_list_http_error(self):
        """Test fetch raises ConnectorError on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=http_error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            connector = YouTubeConnector({
                "channel_url": "https://www.youtube.com/@TestChannel"
            })

            with pytest.raises(ConnectorError, match="Failed to fetch YouTube RSS"):
                await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

    @pytest.mark.asyncio
    async def test_fetch_video_list_with_permanent_redirect(self):
        """Test permanent redirect (301/308) is detected."""
        mock_response = self._create_mock_response(b"<rss></rss>")
        mock_response.url = "https://www.youtube.com/feeds/videos.xml?channel_id=new_id"

        # Simulate 301 redirect history
        mock_history = MagicMock()
        mock_history.status_code = 301
        mock_response.history = [mock_history]

        mock_feed_result = {"entries": [], "bozo": False}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                connector = YouTubeConnector({
                    "channel_url": "https://www.youtube.com/@TestChannel"
                })
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=old_id"
                )

        assert result.redirect_info is not None
        assert result.redirect_info["status_code"] == 301

    @pytest.mark.asyncio
    async def test_fetch_video_list_bozo_feed(self):
        """Test bozo (malformed) feed is still processed."""
        mock_response = self._create_mock_response(b"<rss>malformed")

        mock_feed_result = {
            "entries": [
                MockFeedEntry(
                    yt_videoid="vid1",
                    link="https://www.youtube.com/watch?v=vid1",
                    title="Video",
                    summary="Desc",
                    published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
                )
            ],
            "bozo": True,
            "bozo_exception": Exception("Malformed XML"),
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                connector = YouTubeConnector({
                    "channel_url": "https://www.youtube.com/@TestChannel"
                })
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

        # Bozo feeds should still be processed
        assert len(result.items) == 1


class TestYouTubeConnectorFetchTranscript:
    """Tests for _fetch_transcript method."""

    @pytest.mark.asyncio
    async def test_fetch_transcript_success_english(self):
        """Test successful transcript fetch in English."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mock transcript API response
        mock_snippet = MagicMock()
        mock_snippet.text = "Hello world this is a transcript"

        with patch("cyberpulse.services.youtube_connector.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.return_value = [mock_snippet]
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result == "Hello world this is a transcript"

    @pytest.mark.asyncio
    async def test_fetch_transcript_language_fallback(self):
        """Test language fallback when preferred language not found."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        mock_snippet = MagicMock()
        mock_snippet.text = "Fallback transcript"

        with patch("cyberpulse.services.youtube_connector.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            # First calls raise NoTranscriptFound, later call succeeds
            mock_api.fetch.side_effect = [
                NoTranscriptFound("video123", ["en"], MagicMock()),
                [mock_snippet]
            ]
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result == "Fallback transcript"

    @pytest.mark.asyncio
    async def test_fetch_transcript_disabled(self):
        """Test None returned when transcripts are disabled."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch("cyberpulse.services.youtube_connector.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.side_effect = TranscriptsDisabled("Transcripts disabled")
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_transcript_not_found(self):
        """Test None returned when no transcript found in any language."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch("cyberpulse.services.youtube_connector.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch.side_effect = NoTranscriptFound("video123", ["en"], MagicMock())
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        assert result is None


class TestYouTubeConnectorProcessVideos:
    """Tests for _process_videos method."""

    @pytest.mark.asyncio
    async def test_process_videos_with_transcript(self):
        """Test video processing with transcript."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid1",
            "url": "https://www.youtube.com/watch?v=vid1",
            "title": "Test Video",
            "description": "Video description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["security"],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = "Full transcript content here"

            items = await connector._process_videos(video_entries)

        assert len(items) == 1
        assert items[0]["content"] == "Full transcript content here"
        assert items[0]["raw_metadata"]["has_transcript"] is True

    @pytest.mark.asyncio
    async def test_process_videos_fallback_to_description(self):
        """Test video processing falls back to description when no transcript."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid2",
            "url": "https://www.youtube.com/watch?v=vid2",
            "title": "No Transcript Video",
            "description": "Fallback description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": [],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = None

            items = await connector._process_videos(video_entries)

        assert len(items) == 1
        assert items[0]["content"] == "Fallback description"
        assert items[0]["raw_metadata"]["has_transcript"] is False

    @pytest.mark.asyncio
    async def test_process_videos_skip_no_content(self):
        """Test video is skipped when both transcript and description are empty."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid3",
            "url": "https://www.youtube.com/watch?v=vid3",
            "title": "Empty Video",
            "description": "",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": [],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = None

            items = await connector._process_videos(video_entries)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_process_videos_output_format(self):
        """Test output format matches expected Item fields."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        video_entries = [{
            "video_id": "vid4",
            "url": "https://www.youtube.com/watch?v=vid4",
            "title": "Format Test",
            "description": "Description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Author",
            "tags": ["tag1", "tag2"],
        }]

        with patch.object(connector, "_fetch_transcript", new_callable=AsyncMock) as mock_transcript:
            mock_transcript.return_value = "Transcript"

            items = await connector._process_videos(video_entries)

        item = items[0]
        assert item["external_id"] == "vid4"
        assert item["url"] == "https://www.youtube.com/watch?v=vid4"
        assert item["title"] == "Format Test"
        assert item["content"] == "Transcript"
        assert item["author"] == "Test Author"
        assert item["tags"] == ["tag1", "tag2"]
        assert "published_at" in item
        assert "raw_metadata" in item


class TestYouTubeConnectorFetch:
    """Tests for main fetch method."""

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        """Test that fetch returns FetchResult."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg"
        })

        # Mock all internal methods
        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            with patch.object(connector, "_fetch_video_list", new_callable=AsyncMock) as mock_fetch_list:
                with patch.object(connector, "_process_videos", new_callable=AsyncMock) as mock_process:
                    mock_resolve.return_value = "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                    mock_fetch_list.return_value = FetchResult(items=[], redirect_info=None)
                    mock_process.return_value = []

                    result = await connector.fetch()

        assert isinstance(result, FetchResult)
        assert result.items == []
        assert result.redirect_info is None

    @pytest.mark.asyncio
    async def test_fetch_full_workflow(self):
        """Test complete fetch workflow with mock data."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mock video entry from RSS
        mock_video_entry = {
            "video_id": "test123",
            "url": "https://www.youtube.com/watch?v=test123",
            "title": "Test Video",
            "description": "Test Description",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["test"],
        }

        mock_rss_result = FetchResult(items=[mock_video_entry], redirect_info=None)

        # Mock final item after transcript processing
        mock_final_item = {
            "external_id": "test123",
            "url": "https://www.youtube.com/watch?v=test123",
            "title": "Test Video",
            "content": "Transcript content",
            "published_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "author": "Test Channel",
            "tags": ["test"],
            "raw_metadata": {"has_transcript": True, "video_id": "test123"},
        }

        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            with patch.object(connector, "_fetch_video_list", new_callable=AsyncMock) as mock_fetch_list:
                with patch.object(connector, "_process_videos", new_callable=AsyncMock) as mock_process:
                    mock_resolve.return_value = "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                    mock_fetch_list.return_value = mock_rss_result
                    mock_process.return_value = [mock_final_item]

                    result = await connector.fetch()

        assert len(result.items) == 1
        assert result.items[0]["external_id"] == "test123"
        assert result.items[0]["content"] == "Transcript content"

    @pytest.mark.asyncio
    async def test_fetch_raises_on_invalid_config(self):
        """Test fetch raises error on invalid config."""
        connector = YouTubeConnector({})  # Missing channel_url

        with pytest.raises(ValueError, match="requires 'channel_url'"):
            await connector.fetch()

    @pytest.mark.asyncio
    async def test_fetch_propagates_connector_error(self):
        """Test fetch propagates ConnectorError from internal methods."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch.object(connector, "_resolve_channel_url", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = ConnectorError("Failed to resolve channel")

            with pytest.raises(ConnectorError, match="Failed to resolve channel"):
                await connector.fetch()


class TestYouTubeConnectorSSRFProtection:
    """Tests for SSRF protection in redirects."""

    @pytest.mark.asyncio
    async def test_fetch_video_list_ssrf_redirect_blocked(self):
        """Test SSRF redirect to internal URL is blocked."""

        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mock the internal method to simulate SSRF validation failure
        with patch.object(
            connector, "_fetch_video_list",
            new_callable=AsyncMock
        ) as mock_fetch:
            # Simulate what happens when SSRF validation fails
            mock_fetch.side_effect = ConnectorError(
                "RSS redirect to blocked URL: Access to localhost is not allowed"
            )

            with pytest.raises(ConnectorError, match="RSS redirect to blocked URL"):
                await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

    def test_validate_url_for_ssrf_blocks_localhost(self):
        """Test that validate_url_for_ssrf blocks localhost URLs."""
        from cyberpulse.services.base import SSRFError, validate_url_for_ssrf

        with pytest.raises(SSRFError, match="localhost"):
            validate_url_for_ssrf("http://127.0.0.1/internal")


class TestYouTubeConnectorFormatTranscript:
    """Tests for _format_transcript method."""

    def test_format_transcript_with_list(self):
        """Test formatting transcript from list of dicts."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        transcript_list = [
            {"text": "Hello"},
            {"text": "world"},
            {"text": "test"},
        ]

        result = connector._format_transcript(transcript_list)

        assert result == "Hello world test"

    def test_format_transcript_with_objects(self):
        """Test formatting transcript from list of objects."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        mock_snippet1 = MagicMock()
        mock_snippet1.text = "First sentence"
        mock_snippet2 = MagicMock()
        mock_snippet2.text = "Second sentence"

        result = connector._format_transcript([mock_snippet1, mock_snippet2])

        assert result == "First sentence Second sentence"

    def test_format_transcript_empty_list(self):
        """Test formatting empty transcript list."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        result = connector._format_transcript([])

        assert result == ""

    def test_format_transcript_mixed_access(self):
        """Test formatting transcript with mixed dict/object access."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Mix of dict and object with text attribute
        mock_obj = MagicMock()
        mock_obj.text = "object text"

        transcript_list = [
            {"text": "dict text"},
            mock_obj,
        ]

        result = connector._format_transcript(transcript_list)

        assert "dict text" in result
        assert "object text" in result


class TestYouTubeConnectorLanguagePriority:
    """Tests for transcript language priority."""

    @pytest.mark.asyncio
    async def test_fetch_transcript_priority_order(self):
        """Verify en tried before en-US before en-GB."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        call_order = []

        def track_calls(video_id, languages, **kwargs):
            call_order.append(languages[0] if languages else "unknown")
            if languages == ["en"]:
                raise NoTranscriptFound(video_id, languages, MagicMock())
            if languages == ["en-US"]:
                raise NoTranscriptFound(video_id, languages, MagicMock())
            # en-GB succeeds
            mock_snippet = MagicMock()
            mock_snippet.text = "British English transcript"
            return [mock_snippet]

        with patch("cyberpulse.services.youtube_connector.YouTubeTranscriptApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.fetch = track_calls
            mock_api_class.return_value = mock_api

            result = await connector._fetch_transcript("video123")

        # Verify order: en -> en-US -> en-GB
        assert call_order == ["en", "en-US", "en-GB"]
        assert result == "British English transcript"


class TestYouTubeConnectorRequestError:
    """Tests for httpx.RequestError handling."""

    @pytest.mark.asyncio
    async def test_fetch_video_list_request_error(self):
        """Test httpx.RequestError (timeout, connection) handling."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.RequestError("Connection timeout")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with pytest.raises(ConnectorError, match="Failed to fetch YouTube RSS"):
                await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )


class TestYouTubeConnectorMetaTagExtraction:
    """Tests for meta tag channel_id extraction."""

    @pytest.mark.asyncio
    async def test_fetch_channel_id_from_meta_tag(self):
        """Test channel_id extracted from og:url meta tag."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # HTML with og:url meta tag instead of JSON channelId
        mock_html = '<meta property="og:url" content="https://www.youtube.com/channel/UCMETATAG123">'
        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            channel_id = await connector._fetch_channel_id(
                "https://www.youtube.com/@TestChannel"
            )

        assert channel_id == "UCMETATAG123"


class TestYouTubeConnectorMaxItems:
    """Tests for MAX_ITEMS truncation."""

    @pytest.mark.asyncio
    async def test_fetch_video_list_truncates_to_max_items(self):
        """Test that feed with more than MAX_ITEMS is truncated."""
        connector = YouTubeConnector({
            "channel_url": "https://www.youtube.com/@TestChannel"
        })

        # Create 20 entries (more than MAX_ITEMS=15)
        entries = [
            MockFeedEntry(
                yt_videoid=f"vid{i}",
                link=f"https://www.youtube.com/watch?v=vid{i}",
                title=f"Video {i}",
                summary=f"Description {i}",
                published_parsed=time.struct_time((2024, 1, 15, 10, 30, 0, 0, 15, 0)),
            )
            for i in range(20)
        ]

        mock_response = MagicMock()
        mock_response.content = b"<rss></rss>"
        mock_response.url = "https://www.youtube.com/feeds/videos.xml?channel_id=test"
        mock_response.history = []
        mock_response.raise_for_status = MagicMock()

        mock_feed_result = {"entries": entries, "bozo": False}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=test"
                )

        # Should be truncated to MAX_ITEMS=15
        assert len(result.items) == 15


class TestYouTubeConnectorRedirect308:
    """Tests for 308 permanent redirect handling."""

    @pytest.mark.asyncio
    async def test_fetch_video_list_with_308_redirect(self):
        """Test 308 permanent redirect is detected."""
        mock_response = MagicMock()
        mock_response.content = b"<rss></rss>"
        mock_response.url = "https://www.youtube.com/feeds/videos.xml?channel_id=new_id"

        mock_history = MagicMock()
        mock_history.status_code = 308
        mock_response.history = [mock_history]
        mock_response.raise_for_status = MagicMock()

        mock_feed_result = {"entries": [], "bozo": False}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch("feedparser.parse", return_value=mock_feed_result):
                connector = YouTubeConnector({
                    "channel_url": "https://www.youtube.com/@TestChannel"
                })
                result = await connector._fetch_video_list(
                    "https://www.youtube.com/feeds/videos.xml?channel_id=old_id"
                )

        assert result.redirect_info is not None
        assert result.redirect_info["status_code"] == 308
