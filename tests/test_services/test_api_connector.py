"""Tests for API Connector."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services import APIConnector, ConnectorError


class TestAPIConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid(self):
        """Test validation passes with valid config."""
        connector = APIConnector({"base_url": "https://api.example.com"})
        assert connector.validate_config() is True

    def test_validate_config_missing_base_url(self):
        """Test validation fails when base_url is missing."""
        connector = APIConnector({})
        with pytest.raises(ValueError, match="requires 'base_url'"):
            connector.validate_config()

    def test_validate_config_empty_base_url(self):
        """Test validation fails when base_url is empty."""
        connector = APIConnector({"base_url": ""})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_base_url_not_string(self):
        """Test validation fails when base_url is not a string."""
        connector = APIConnector({"base_url": 123})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_with_bearer_auth(self):
        """Test validation passes with bearer auth config."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "auth_token": "test-token",
        })
        assert connector.validate_config() is True

    def test_validate_config_bearer_missing_token(self):
        """Test validation fails when bearer auth is missing token."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
        })
        with pytest.raises(ValueError, match="bearer auth requires 'auth_token'"):
            connector.validate_config()

    def test_validate_config_with_api_key_auth(self):
        """Test validation passes with api_key auth config."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "api_key",
            "api_key": "test-key",
        })
        assert connector.validate_config() is True

    def test_validate_config_api_key_missing_key(self):
        """Test validation fails when api_key auth is missing key."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "api_key",
        })
        with pytest.raises(ValueError, match="api_key auth requires 'api_key'"):
            connector.validate_config()

    def test_validate_config_with_basic_auth(self):
        """Test validation passes with basic auth config."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "basic",
            "username": "user",
            "password": "pass",
        })
        assert connector.validate_config() is True

    def test_validate_config_basic_missing_credentials(self):
        """Test validation fails when basic auth is missing credentials."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "basic",
            "username": "user",
        })
        with pytest.raises(ValueError, match="basic auth requires 'username' and 'password'"):
            connector.validate_config()

    def test_validate_config_invalid_auth_type(self):
        """Test validation fails with invalid auth_type value."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "oauth",
        })
        with pytest.raises(ValueError, match="Invalid auth_type 'oauth'"):
            connector.validate_config()

    def test_validate_config_unknown_auth_type(self):
        """Test validation fails with unknown auth_type value."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "auth_type": "invalid",
        })
        with pytest.raises(ValueError, match="Invalid auth_type 'invalid'"):
            connector.validate_config()


class TestAPIConnectorFetchNoAuth:
    """Tests for fetch method with no authentication."""

    @pytest.fixture
    def mock_response_data(self):
        """Create mock API response data."""
        return {
            "items": [
                {
                    "id": "item-1",
                    "url": "https://example.com/articles/1",
                    "title": "First Article",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content of first article",
                    "author": "John Doe",
                    "tags": ["security", "python"],
                },
                {
                    "id": "item-2",
                    "url": "https://example.com/articles/2",
                    "title": "Second Article",
                    "published_at": "2024-01-16T14:00:00Z",
                    "content": "Content of second article",
                    "author": "Jane Smith",
                    "tags": ["news"],
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_fetch_no_auth(self, mock_response_data):
        """Test successful fetch without authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})
            items = await connector.fetch()

        assert len(items) == 2
        assert items[0]["external_id"] == "item-1"
        assert items[0]["url"] == "https://example.com/articles/1"
        assert items[0]["title"] == "First Article"
        assert items[0]["content"] == "Content of first article"
        assert items[0]["author"] == "John Doe"
        assert items[0]["tags"] == ["security", "python"]

    @pytest.mark.asyncio
    async def test_fetch_with_custom_item_path(self):
        """Test fetch with custom item path in response."""
        mock_response_data = {
            "data": {
                "results": [
                    {
                        "id": "custom-item",
                        "url": "https://example.com/custom",
                        "title": "Custom Item",
                        "published_at": "2024-01-15T10:30:00Z",
                        "content": "Custom content",
                    },
                ],
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "item_path": "data.results",
            })
            items = await connector.fetch()

        assert len(items) == 1
        assert items[0]["external_id"] == "custom-item"


class TestAPIConnectorFetchBearerAuth:
    """Tests for fetch method with bearer authentication."""

    @pytest.mark.asyncio
    async def test_fetch_bearer_auth(self):
        """Test fetch with bearer token authentication."""
        mock_response_data = {
            "items": [
                {
                    "id": "auth-item",
                    "url": "https://example.com/auth-article",
                    "title": "Authenticated Article",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Protected content",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "auth_type": "bearer",
                "auth_token": "secret-token",
            })
            items = await connector.fetch()

        # Verify bearer token was used
        call_args = mock_client.get.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer secret-token"
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_fetch_api_key_in_header(self):
        """Test fetch with API key in header."""
        mock_response_data = {
            "items": [
                {
                    "id": "api-key-item",
                    "url": "https://example.com/api-article",
                    "title": "API Key Article",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "auth_type": "api_key",
                "api_key": "my-api-key",
                "api_key_header": "X-API-Key",
            })
            items = await connector.fetch()

        call_args = mock_client.get.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("X-API-Key") == "my-api-key"
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_fetch_api_key_in_query(self):
        """Test fetch with API key in query parameter."""
        mock_response_data = {
            "items": [
                {
                    "id": "query-item",
                    "url": "https://example.com/query-article",
                    "title": "Query Param Article",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "auth_type": "api_key",
                "api_key": "my-api-key",
                "api_key_location": "query",
                "api_key_param": "key",
            })
            items = await connector.fetch()

        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("key") == "my-api-key"
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_fetch_basic_auth(self):
        """Test fetch with basic authentication."""
        import base64

        mock_response_data = {
            "items": [
                {
                    "id": "basic-auth-item",
                    "url": "https://example.com/basic-auth-article",
                    "title": "Basic Auth Article",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Protected content",
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "auth_type": "basic",
                "username": "testuser",
                "password": "testpass",
            })
            items = await connector.fetch()

        # Verify basic auth header was used
        call_args = mock_client.get.call_args
        headers = call_args.kwargs.get("headers", {})
        expected_credentials = base64.b64encode(b"testuser:testpass").decode()
        assert headers.get("Authorization") == f"Basic {expected_credentials}"
        assert len(items) == 1
        assert items[0]["external_id"] == "basic-auth-item"


class TestAPIConnectorFetchPagination:
    """Tests for fetch method with pagination."""

    @pytest.mark.asyncio
    async def test_fetch_with_page_pagination(self):
        """Test fetch with page-based pagination."""
        # First page
        page1_data = {
            "items": [
                {
                    "id": "page1-item",
                    "url": "https://example.com/1",
                    "title": "Page 1",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 1",
                },
            ],
            "has_more": True,
        }

        # Second page
        page2_data = {
            "items": [
                {
                    "id": "page2-item",
                    "url": "https://example.com/2",
                    "title": "Page 2",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 2",
                },
            ],
            "has_more": False,
        }

        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = page1_data
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = page2_data
        mock_response2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [mock_response1, mock_response2]
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "pagination_type": "page",
                "pagination_param": "page",
                "has_more_path": "has_more",
            })
            items = await connector.fetch()

        assert len(items) == 2
        assert items[0]["external_id"] == "page1-item"
        assert items[1]["external_id"] == "page2-item"

    @pytest.mark.asyncio
    async def test_fetch_with_offset_pagination(self):
        """Test fetch with offset-based pagination."""
        # First page
        page1_data = {
            "items": [
                {
                    "id": "offset-item-1",
                    "url": "https://example.com/1",
                    "title": "Offset 1",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 1",
                },
            ],
            "total": 2,
        }

        # Second page
        page2_data = {
            "items": [
                {
                    "id": "offset-item-2",
                    "url": "https://example.com/2",
                    "title": "Offset 2",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 2",
                },
            ],
            "total": 2,
        }

        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = page1_data
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = page2_data
        mock_response2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [mock_response1, mock_response2]
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "pagination_type": "offset",
                "pagination_param": "offset",
                "page_size": 1,
                "total_path": "total",
            })
            items = await connector.fetch()

        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_fetch_with_cursor_pagination(self):
        """Test fetch with cursor-based pagination."""
        # First page
        page1_data = {
            "items": [
                {
                    "id": "cursor-item-1",
                    "url": "https://example.com/1",
                    "title": "Cursor 1",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 1",
                },
            ],
            "next_cursor": "abc123",
        }

        # Second page
        page2_data = {
            "items": [
                {
                    "id": "cursor-item-2",
                    "url": "https://example.com/2",
                    "title": "Cursor 2",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content 2",
                },
            ],
            "next_cursor": None,
        }

        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = page1_data
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = page2_data
        mock_response2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [mock_response1, mock_response2]
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "pagination_type": "cursor",
                "pagination_param": "cursor",
                "cursor_path": "next_cursor",
            })
            items = await connector.fetch()

        assert len(items) == 2


class TestAPIConnectorRetry:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """Test retry on network timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": "retry-item",
                    "url": "https://example.com/retry",
                    "title": "Retry Success",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content",
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            # First call times out, second succeeds
            mock_client.get.side_effect = [
                httpx.TimeoutException("Connection timed out"),
                mock_response,
            ]
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})
            # Use short delay for testing
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]
            items = await connector.fetch()

        assert len(items) == 1
        assert items[0]["external_id"] == "retry-item"

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test retry on HTTP 500 server error."""
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_error_response
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {
            "items": [
                {
                    "id": "server-retry-item",
                    "url": "https://example.com/server-retry",
                    "title": "Server Retry",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content",
                },
            ],
        }
        mock_success_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [
                mock_error_response,
                mock_success_response,
            ]
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]
            items = await connector.fetch()

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_failure(self):
        """Test no retry on HTTP 401 authentication failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({
                "base_url": "https://api.example.com",
                "auth_type": "bearer",
                "auth_token": "invalid-token",
            })

            with pytest.raises(ConnectorError, match="Authentication failed"):
                await connector.fetch()

        # Should only be called once (no retry)
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_forbidden(self):
        """Test no retry on HTTP 403 forbidden."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})

            with pytest.raises(ConnectorError, match="Authentication failed"):
                await connector.fetch()

        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_not_found(self):
        """Test no retry on HTTP 404 not found."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})

            with pytest.raises(ConnectorError, match="Resource not found"):
                await connector.fetch()

        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that max retries are exceeded."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("Timeout")
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]

            with pytest.raises(ConnectorError, match="Max retries exceeded"):
                await connector.fetch()

        # Initial + 3 retries
        assert mock_client.get.call_count == 4


class TestAPIConnectorRateLimit:
    """Tests for rate limit handling."""

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test handling of HTTP 429 rate limit."""
        mock_rate_limit_response = MagicMock()
        mock_rate_limit_response.status_code = 429
        mock_rate_limit_response.headers = {"Retry-After": "1"}
        mock_rate_limit_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_rate_limit_response
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {
            "items": [
                {
                    "id": "rate-limit-item",
                    "url": "https://example.com/rate-limit",
                    "title": "Rate Limit Success",
                    "published_at": "2024-01-15T10:30:00Z",
                    "content": "Content",
                },
            ],
        }
        mock_success_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [
                mock_rate_limit_response,
                mock_success_response,
            ]
            mock_client_class.return_value = mock_client

            connector = APIConnector({"base_url": "https://api.example.com"})
            connector.RATE_LIMIT_DELAY = 0.01  # Short delay for testing
            items = await connector.fetch()

        assert len(items) == 1


class TestAPIConnectorParseResponse:
    """Tests for response parsing."""

    def test_parse_response_with_default_mapping(self):
        """Test parsing response with default field mapping."""
        connector = APIConnector({"base_url": "https://api.example.com"})

        data = {
            "id": "parse-test",
            "url": "https://example.com/parse",
            "title": "Parse Test",
            "published_at": "2024-01-15T10:30:00Z",
            "content": "Test content",
            "author": "Test Author",
            "tags": ["tag1", "tag2"],
        }

        items = connector._parse_response([data])

        assert len(items) == 1
        assert items[0]["external_id"] == "parse-test"
        assert items[0]["url"] == "https://example.com/parse"
        assert items[0]["title"] == "Parse Test"
        assert items[0]["author"] == "Test Author"
        assert items[0]["tags"] == ["tag1", "tag2"]

    def test_parse_response_with_custom_field_mapping(self):
        """Test parsing response with custom field mapping."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "field_mapping": {
                "external_id": "article_id",
                "title": "headline",
                "content": "body",
                "published_at": "created_at",
                "author": "author_name",
                "tags": "categories",
            },
        })

        data = {
            "article_id": "custom-id",
            "url": "https://example.com/custom",
            "headline": "Custom Headline",
            "created_at": "2024-01-15T10:30:00Z",
            "body": "Custom body content",
            "author_name": "Custom Author",
            "categories": ["cat1", "cat2"],
        }

        items = connector._parse_response([data])

        assert len(items) == 1
        assert items[0]["external_id"] == "custom-id"
        assert items[0]["title"] == "Custom Headline"
        assert items[0]["content"] == "Custom body content"
        assert items[0]["author"] == "Custom Author"
        assert items[0]["tags"] == ["cat1", "cat2"]

    def test_parse_response_missing_optional_fields(self):
        """Test parsing response with missing optional fields."""
        connector = APIConnector({"base_url": "https://api.example.com"})

        data = {
            "id": "minimal-item",
            "url": "https://example.com/minimal",
        }

        items = connector._parse_response([data])

        assert len(items) == 1
        assert items[0]["external_id"] == "minimal-item"
        assert items[0]["title"] == ""
        assert items[0]["content"] == ""
        assert items[0]["author"] == ""
        assert items[0]["tags"] == []

    def test_parse_date_iso_format(self):
        """Test parsing ISO format date."""
        connector = APIConnector({"base_url": "https://api.example.com"})

        dt = connector._parse_date("2024-01-15T10:30:00Z")

        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.tzinfo == timezone.utc

    def test_parse_date_iso_format_with_timezone(self):
        """Test parsing ISO format date with timezone offset."""
        connector = APIConnector({"base_url": "https://api.example.com"})

        dt = connector._parse_date("2024-01-15T10:30:00+08:00")

        # Should be converted to UTC
        assert dt.tzinfo == timezone.utc

    def test_parse_date_fallback_to_current_time(self):
        """Test that missing date falls back to current UTC time."""
        connector = APIConnector({"base_url": "https://api.example.com"})

        before = datetime.now(timezone.utc)
        dt = connector._parse_date(None)
        after = datetime.now(timezone.utc)

        assert before <= dt <= after
        assert dt.tzinfo == timezone.utc


class TestAPIConnectorBuildRequest:
    """Tests for request building."""

    def test_build_request_basic(self):
        """Test building basic request without auth."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "endpoint": "/articles",
        })

        request = connector._build_request(page=1)

        assert request["url"] == "https://api.example.com/articles"
        assert request["params"] == {}

    def test_build_request_with_query_params(self):
        """Test building request with query params."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "endpoint": "/articles",
            "query_params": {
                "status": "published",
                "limit": 10,
            },
        })

        request = connector._build_request(page=1)

        assert request["params"]["status"] == "published"
        assert request["params"]["limit"] == 10

    def test_build_request_with_headers(self):
        """Test building request with custom headers."""
        connector = APIConnector({
            "base_url": "https://api.example.com",
            "endpoint": "/articles",
            "headers": {
                "X-Custom-Header": "custom-value",
            },
        })

        request = connector._build_request(page=1)

        assert request["headers"]["X-Custom-Header"] == "custom-value"