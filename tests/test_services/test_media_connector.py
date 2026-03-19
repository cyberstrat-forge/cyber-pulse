"""Tests for Media API Connector."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services import MediaAPIConnector, ConnectorError
from cyberpulse.services.media_connector import YouTubeRetryableError


class TestMediaAPIConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid_youtube(self):
        """Test validation passes with valid YouTube config."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })
        assert connector.validate_config() is True

    def test_validate_config_missing_platform(self):
        """Test validation fails when platform is missing."""
        connector = MediaAPIConnector({
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })
        with pytest.raises(ValueError, match="requires 'platform'"):
            connector.validate_config()

    def test_validate_config_missing_api_key(self):
        """Test validation fails when api_key is missing."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "channel_id": "UC123456",
        })
        with pytest.raises(ValueError, match="requires 'api_key'"):
            connector.validate_config()

    def test_validate_config_empty_api_key(self):
        """Test validation fails when api_key is empty."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "",
            "channel_id": "UC123456",
        })
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_unsupported_platform(self):
        """Test validation fails for unsupported platform."""
        connector = MediaAPIConnector({
            "platform": "vimeo",
            "api_key": "test-api-key",
            "channel_id": "123456",
        })
        with pytest.raises(ValueError, match="Unsupported platform 'vimeo'"):
            connector.validate_config()

    def test_validate_config_youtube_missing_channel_id(self):
        """Test validation fails when YouTube channel_id is missing."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
        })
        with pytest.raises(ValueError, match="YouTube connector requires 'channel_id'"):
            connector.validate_config()


class TestMediaAPIConnectorFetchYouTube:
    """Tests for fetch method with YouTube platform."""

    @pytest.fixture
    def youtube_search_response(self):
        """Create mock YouTube search API response."""
        return {
            "items": [
                {
                    "id": {"videoId": "video-123"},
                    "snippet": {
                        "title": "Test Video",
                        "description": "This is a test video description",
                        "publishedAt": "2024-01-15T10:30:00Z",
                        "channelTitle": "Test Channel",
                        "tags": ["security", "python"],
                    },
                },
                {
                    "id": {"videoId": "video-456"},
                    "snippet": {
                        "title": "Another Video",
                        "description": "Another video description",
                        "publishedAt": "2024-01-16T14:00:00Z",
                        "channelTitle": "Test Channel",
                    },
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_fetch_youtube(self, youtube_search_response):
        """Test successful fetch from YouTube."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = youtube_search_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })
            items = await connector.fetch()

        assert len(items) == 2
        assert items[0]["external_id"] == "video-123"
        assert items[0]["url"] == "https://www.youtube.com/watch?v=video-123"
        assert items[0]["title"] == "Test Video"
        assert items[0]["content"] == "This is a test video description"
        assert items[0]["author"] == "Test Channel"
        assert items[0]["tags"] == ["security", "python"]
        assert "content_hash" in items[0]

    @pytest.mark.asyncio
    async def test_fetch_youtube_uses_api_key_in_query(self, youtube_search_response):
        """Test that API key is passed in query parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = youtube_search_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "my-youtube-key",
                "channel_id": "UC123456",
            })
            await connector.fetch()

        # Verify API key was passed in query params
        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("key") == "my-youtube-key"

    @pytest.mark.asyncio
    async def test_fetch_youtube_limits_results(self):
        """Test that fetch limits results to MAX_ITEMS."""
        # Create more items than MAX_ITEMS
        items = []
        for i in range(60):
            items.append({
                "id": {"videoId": f"video-{i}"},
                "snippet": {
                    "title": f"Video {i}",
                    "description": f"Description {i}",
                    "publishedAt": "2024-01-15T10:30:00Z",
                    "channelTitle": "Test Channel",
                },
            })

        response_data = {"items": items}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })
            result = await connector.fetch()

        assert len(result) == MediaAPIConnector.MAX_ITEMS


class TestMediaAPIConnectorCheckCaptions:
    """Tests for _check_captions method."""

    @pytest.mark.asyncio
    async def test_check_captions_exists(self):
        """Test checking captions when they exist."""
        captions_response = {
            "items": [
                {"id": "caption-1", "snippet": {"language": "en"}}
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = captions_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })

            async with httpx.AsyncClient() as client:
                has_captions = await connector._check_captions(client, "video-123")

        assert has_captions is True

    @pytest.mark.asyncio
    async def test_check_captions_not_exists(self):
        """Test checking captions when they don't exist."""
        captions_response = {"items": []}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = captions_response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })

            async with httpx.AsyncClient() as client:
                has_captions = await connector._check_captions(client, "video-123")

        assert has_captions is False


class TestMediaAPIConnectorErrorHandling:
    """Tests for error handling with retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_quota_exceeded(self):
        """Test retry on YouTube quota exceeded (HTTP 403 with quotaExceeded)."""
        # First response: quota exceeded
        quota_error_response = MagicMock()
        quota_error_response.status_code = 403
        quota_error_response.json.return_value = {
            "error": {
                "errors": [{"reason": "quotaExceeded"}]
            }
        }

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "retry-video"},
                    "snippet": {
                        "title": "Retry Video",
                        "description": "Description",
                        "publishedAt": "2024-01-15T10:30:00Z",
                        "channelTitle": "Test Channel",
                    },
                },
            ],
        }
        success_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [quota_error_response, success_response]
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]
            items = await connector.fetch()

        assert len(items) == 1
        assert items[0]["external_id"] == "retry-video"

    @pytest.mark.asyncio
    async def test_no_retry_on_invalid_key(self):
        """Test no retry on invalid API key (HTTP 400 with keyInvalid)."""
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {
            "error": {
                "errors": [{"reason": "keyInvalid"}]
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = error_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "invalid-key",
                "channel_id": "UC123456",
            })

            with pytest.raises(ConnectorError, match="Invalid API key"):
                await connector.fetch()

        # Should only be called once (no retry)
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_channel_not_found(self):
        """Test no retry on channel not found (HTTP 404)."""
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.json.return_value = {
            "error": {
                "errors": [{"reason": "channelNotFound"}]
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = error_response
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "INVALID",
            })

            with pytest.raises(ConnectorError, match="Channel not found"):
                await connector.fetch()

        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test retry on HTTP 500 server error."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=error_response
        )

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "server-retry-video"},
                    "snippet": {
                        "title": "Server Retry Video",
                        "description": "Description",
                        "publishedAt": "2024-01-15T10:30:00Z",
                        "channelTitle": "Test Channel",
                    },
                },
            ],
        }
        success_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [error_response, success_response]
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]
            items = await connector.fetch()

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that max retries are exceeded."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            connector = MediaAPIConnector({
                "platform": "youtube",
                "api_key": "test-api-key",
                "channel_id": "UC123456",
            })
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]

            with pytest.raises(ConnectorError, match="Max retries exceeded"):
                await connector.fetch()

        # Initial + 3 retries
        assert mock_client.get.call_count == 4


class TestMediaAPIConnectorParseVideo:
    """Tests for video parsing."""

    def test_parse_youtube_video(self):
        """Test parsing a YouTube video item."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        video_item = {
            "id": {"videoId": "parse-test-123"},
            "snippet": {
                "title": "Parse Test Video",
                "description": "Parse test description",
                "publishedAt": "2024-01-15T10:30:00Z",
                "channelTitle": "Parse Test Channel",
                "tags": ["test", "parsing"],
            },
        }

        result = connector._parse_youtube_video(video_item)

        assert result["external_id"] == "parse-test-123"
        assert result["url"] == "https://www.youtube.com/watch?v=parse-test-123"
        assert result["title"] == "Parse Test Video"
        assert result["content"] == "Parse test description"
        assert result["author"] == "Parse Test Channel"
        assert result["tags"] == ["test", "parsing"]
        assert "content_hash" in result
        assert isinstance(result["published_at"], datetime)
        assert result["published_at"].tzinfo == timezone.utc

    def test_parse_youtube_video_without_tags(self):
        """Test parsing a YouTube video without tags."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        video_item = {
            "id": {"videoId": "no-tags-video"},
            "snippet": {
                "title": "No Tags Video",
                "description": "Description without tags",
                "publishedAt": "2024-01-15T10:30:00Z",
                "channelTitle": "Test Channel",
            },
        }

        result = connector._parse_youtube_video(video_item)

        assert result["tags"] == []

    def test_parse_youtube_video_missing_video_id(self):
        """Test parsing returns None when videoId is missing."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        video_item = {
            "id": {},
            "snippet": {
                "title": "Missing ID Video",
                "description": "Description",
                "publishedAt": "2024-01-15T10:30:00Z",
            },
        }

        result = connector._parse_youtube_video(video_item)

        assert result is None


class TestMediaAPIConnectorCheckYouTubeError:
    """Tests for YouTube error checking logic."""

    def test_check_youtube_error_quota_exceeded(self):
        """Test checking quota exceeded error."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "error": {"errors": [{"reason": "quotaExceeded"}]}
        }

        with pytest.raises(YouTubeRetryableError, match="quota exceeded"):
            connector._check_youtube_error(mock_response, 0)

    def test_check_youtube_error_key_invalid(self):
        """Test checking invalid API key error."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {"errors": [{"reason": "keyInvalid"}]}
        }

        with pytest.raises(ConnectorError, match="Invalid API key"):
            connector._check_youtube_error(mock_response, 0)

    def test_check_youtube_error_channel_not_found(self):
        """Test checking channel not found error."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "error": {"errors": [{"reason": "channelNotFound"}]}
        }

        with pytest.raises(ConnectorError, match="Channel not found"):
            connector._check_youtube_error(mock_response, 0)

    def test_handle_error_timeout(self):
        """Test handling timeout error."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        error = httpx.TimeoutException("Connection timed out")

        should_retry, delay = connector._handle_error(error, 1)

        assert should_retry is True
        assert delay == connector.RETRY_DELAYS[1]

    def test_handle_error_server_error(self):
        """Test handling server error."""
        connector = MediaAPIConnector({
            "platform": "youtube",
            "api_key": "test-api-key",
            "channel_id": "UC123456",
        })

        mock_response = MagicMock()
        mock_response.status_code = 500

        error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        should_retry, delay = connector._handle_error(error, 0)

        assert should_retry is True
        assert delay == connector.RETRY_DELAYS[0]