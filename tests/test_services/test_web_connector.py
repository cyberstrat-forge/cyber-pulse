"""Tests for Web Scraper Connector."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services import ConnectorError
from cyberpulse.services.web_connector import WebScraperConnector


class TestWebScraperConnectorValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_valid(self):
        """Test validation passes with valid config."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        assert connector.validate_config() is True

    def test_validate_config_missing_base_url(self):
        """Test validation fails when base_url is missing."""
        connector = WebScraperConnector({})
        with pytest.raises(ValueError, match="requires 'base_url'"):
            connector.validate_config()

    def test_validate_config_empty_base_url(self):
        """Test validation fails when base_url is empty."""
        connector = WebScraperConnector({"base_url": ""})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_base_url_not_string(self):
        """Test validation fails when base_url is not a string."""
        connector = WebScraperConnector({"base_url": 123})
        with pytest.raises(ValueError, match="must be a non-empty string"):
            connector.validate_config()

    def test_validate_config_invalid_extraction_mode(self):
        """Test validation fails with invalid extraction_mode."""
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "extraction_mode": "invalid",
        })
        with pytest.raises(ValueError, match="Invalid extraction_mode 'invalid'"):
            connector.validate_config()

    def test_validate_config_manual_mode_requires_selectors(self):
        """Test validation fails when manual mode lacks selectors."""
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "extraction_mode": "manual",
        })
        with pytest.raises(ValueError, match="manual extraction_mode requires 'selectors'"):
            connector.validate_config()

    def test_validate_config_manual_mode_with_selectors(self):
        """Test validation passes for manual mode with selectors."""
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "extraction_mode": "manual",
            "selectors": {
                "title": "//h1[@class='title']",
                "content": "//div[@class='article-body']",
            },
        })
        assert connector.validate_config() is True


class TestWebScraperConnectorFetchAutoMode:
    """Tests for fetch method in auto mode."""

    @pytest.fixture
    def sample_html(self):
        """Sample HTML content for testing with substantial content."""
        return """
        <html>
        <head><title>Test Article</title></head>
        <body>
            <article>
                <h1>Article Title</h1>
                <p class="author">John Doe</p>
                <time datetime="2024-01-15">January 15, 2024</time>
                <div class="content">
                    <p>This is the main content of the article. It contains
                    multiple paragraphs with useful information about cybersecurity
                    trends and developments in the industry. We cover various topics
                    including threat intelligence, vulnerability management, and
                    incident response best practices.</p>
                    <p>Second paragraph with more content about the importance of
                    security monitoring and how organizations can improve their
                    security posture through proactive measures and continuous
                    improvement of their security controls.</p>
                    <p>Third paragraph discussing the latest developments in the
                    field of information security and how practitioners can stay
                    ahead of emerging threats through training and awareness programs.</p>
                </div>
            </article>
            <a href="/article/1">Article 1</a>
            <a href="/article/2">Article 2</a>
        </body>
        </html>
        """

    @pytest.fixture
    def sample_html_with_links(self):
        """Sample HTML with article links."""
        return """
        <html>
        <head><title>Articles List</title></head>
        <body>
            <h1>Latest Articles</h1>
            <ul>
                <li><a href="https://example.com/article/1">Article 1</a></li>
                <li><a href="https://example.com/article/2">Article 2</a></li>
                <li><a href="https://example.com/article/3">Article 3</a></li>
            </ul>
        </body>
        </html>
        """

    @pytest.mark.asyncio
    async def test_fetch_auto_mode(self, sample_html):
        """Test successful fetch in auto mode."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sample_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = WebScraperConnector({
                "base_url": "https://example.com/article/test",
                "article_url_pattern": r"/article/",
            })
            items = await connector.fetch()

        assert len(items) >= 1
        assert "content" in items[0]
        assert len(items[0]["content"]) > 0
        assert "url" in items[0]

    @pytest.mark.asyncio
    async def test_fetch_with_custom_user_agent(self, sample_html):
        """Test fetch with custom user agent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sample_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = WebScraperConnector({
                "base_url": "https://example.com/article/test",
                "user_agent": "CustomBot/1.0",
                "article_url_pattern": r"/article/",
            })
            _ = await connector.fetch()

        # Verify user agent was used
        call_args = mock_client.get.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("User-Agent") == "CustomBot/1.0"


class TestWebScraperConnectorExtractLinks:
    """Tests for _extract_links method."""

    def test_extract_links_basic(self):
        """Test extracting links from HTML."""
        html = """
        <html>
        <body>
            <a href="https://example.com/article/1">Article 1</a>
            <a href="https://example.com/article/2">Article 2</a>
            <a href="https://other.com/external">External</a>
        </body>
        </html>
        """
        connector = WebScraperConnector({"base_url": "https://example.com"})
        links = connector._extract_links(html, "https://example.com")

        assert len(links) == 3
        assert "https://example.com/article/1" in links
        assert "https://example.com/article/2" in links
        assert "https://other.com/external" in links

    def test_extract_links_relative_urls(self):
        """Test extracting relative URLs are resolved."""
        html = """
        <html>
        <body>
            <a href="/article/1">Article 1</a>
            <a href="article/2">Article 2</a>
        </body>
        </html>
        """
        connector = WebScraperConnector({"base_url": "https://example.com/news/"})
        links = connector._extract_links(html, "https://example.com/news/")

        assert len(links) == 2
        assert "https://example.com/article/1" in links
        assert "https://example.com/news/article/2" in links

    def test_extract_links_skip_invalid(self):
        """Test that invalid links are skipped."""
        html = """
        <html>
        <body>
            <a href="#section">Anchor</a>
            <a href="javascript:alert('x')">JavaScript</a>
            <a href="mailto:test@example.com">Email</a>
            <a href="https://example.com/article/1">Valid</a>
        </body>
        </html>
        """
        connector = WebScraperConnector({"base_url": "https://example.com"})
        links = connector._extract_links(html, "https://example.com")

        assert len(links) == 1
        assert "https://example.com/article/1" in links

    def test_extract_links_with_pattern(self):
        """Test extracting links with pattern filter."""
        html = """
        <html>
        <body>
            <a href="https://example.com/article/1">Article 1</a>
            <a href="https://example.com/page/about">About</a>
            <a href="https://example.com/article/2">Article 2</a>
        </body>
        </html>
        """
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "link_pattern": r"/article/\d+",
        })
        links = connector._extract_links(html, "https://example.com")

        assert len(links) == 2
        assert "https://example.com/article/1" in links
        assert "https://example.com/article/2" in links

    def test_extract_links_with_selector(self):
        """Test extracting links with XPath selector."""
        html = """
        <html>
        <body>
            <div class="articles">
                <a href="https://example.com/article/1">Article 1</a>
                <a href="https://example.com/article/2">Article 2</a>
            </div>
            <div class="navigation">
                <a href="https://example.com/page/1">Page 1</a>
            </div>
        </body>
        </html>
        """
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "link_selector": "//div[@class='articles']//a[@href]",
        })
        links = connector._extract_links(html, "https://example.com")

        assert len(links) == 2
        assert "https://example.com/article/1" in links
        assert "https://example.com/article/2" in links

    def test_extract_links_deduplication(self):
        """Test that duplicate links are removed."""
        html = """
        <html>
        <body>
            <a href="https://example.com/article/1">Article 1</a>
            <a href="https://example.com/article/1">Article 1 Again</a>
            <a href="https://example.com/article/2">Article 2</a>
        </body>
        </html>
        """
        connector = WebScraperConnector({"base_url": "https://example.com"})
        links = connector._extract_links(html, "https://example.com")

        assert len(links) == 2


class TestWebScraperConnectorExtractContent:
    """Tests for _extract_content method."""

    @pytest.fixture
    def article_html(self):
        """Article HTML content for testing with substantial content."""
        return """
        <html>
        <head>
            <title>Test Article Title</title>
            <meta name="author" content="Jane Smith">
            <meta name="date" content="2024-01-15">
        </head>
        <body>
            <article>
                <h1>Test Article</h1>
                <p>This is the first paragraph of the article content with substantial
                information about cybersecurity threats and defense strategies.</p>
                <p>This is the second paragraph with more details about vulnerability
                assessment methodologies and penetration testing approaches.</p>
                <p>Additional paragraph with information about security monitoring
                and incident response procedures for enterprise environments.</p>
            </article>
        </body>
        </html>
        """

    def test_extract_content_auto(self, article_html):
        """Test content extraction in auto mode."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        result = connector._extract_content(article_html, "https://example.com/article/1", "auto")

        assert result is not None
        assert "content" in result
        assert len(result["content"]) > 0
        assert "url" in result
        assert result["url"] == "https://example.com/article/1"
        assert "external_id" in result

    def test_extract_content_manual(self):
        """Test content extraction in manual mode."""
        html = """
        <html>
        <head><title>Manual Test</title></head>
        <body>
            <h1 class="title">Manual Article Title</h1>
            <div class="author-name">John Author</div>
            <div class="article-body">
                <p>First paragraph of content with substantial information about
                the topic at hand, covering multiple aspects of the subject.</p>
                <p>Second paragraph of content with additional details and
                supporting information that provides context and depth.</p>
                <p>Third paragraph with concluding thoughts and recommendations
                for practitioners in the field.</p>
            </div>
            <span class="date">2024-02-20</span>
        </body>
        </html>
        """
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "extraction_mode": "manual",
            "selectors": {
                "title": "//h1[@class='title']",
                "content": "//div[@class='article-body']",
                "author": "//div[@class='author-name']",
                "date": "//span[@class='date']",
            },
        })
        result = connector._extract_content(html, "https://example.com/article/manual", "manual")

        assert result is not None
        assert "Manual Article Title" in result["title"]
        assert "First paragraph" in result["content"]
        assert "John Author" in result["author"]

    def test_extract_content_fallback_on_parse_failure(self):
        """Test that trafilatura fallback is used on manual extraction failure."""
        html = """
        <html>
        <head><title>Fallback Test</title></head>
        <body>
            <article>
                <h1>Fallback Article</h1>
                <p>This content should be extracted by trafilatura because it contains
                substantial text that can be recognized as article content. We need to
                ensure that the fallback mechanism works correctly when manual selectors
                fail to match any elements in the document.</p>
                <p>Additional paragraphs with more content to ensure the article is
                substantial enough for trafilatura to extract properly.</p>
            </article>
        </body>
        </html>
        """
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "extraction_mode": "manual",
            "selectors": {
                # Invalid selector that won't match
                "content": "//div[@class='nonexistent']",
            },
        })
        result = connector._extract_content(html, "https://example.com/article/fallback", "manual")

        # Should still get content via trafilatura fallback
        assert result is not None
        assert len(result["content"]) > 0


class TestWebScraperConnectorHandlePagination:
    """Tests for pagination handling."""

    @pytest.mark.asyncio
    async def test_handle_pagination_page_based(self):
        """Test page-based pagination."""
        page1_html = """
        <html><body>
            <a href="https://example.com/article/1">Article 1</a>
        </body></html>
        """
        page2_html = """
        <html><body>
            <a href="https://example.com/article/2">Article 2</a>
        </body></html>
        """

        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.text = page1_html
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.text = page2_html
        mock_response2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = [mock_response1, mock_response2]
            mock_client_class.return_value = mock_client

            connector = WebScraperConnector({
                "base_url": "https://example.com?page=1",
                "pagination_type": "page",
                "pagination_param": "page",
                "max_pages": 2,
            })
            _ = await connector.fetch()

        assert mock_client.get.call_count >= 2


class TestWebScraperConnectorRetry:
    """Tests for retry logic."""

    @pytest.fixture
    def substantial_html(self):
        """Substantial HTML content for testing."""
        return """
        <html>
        <body>
            <article>
                <h1>Test Article</h1>
                <p>This is substantial content for testing the web scraper functionality.
                It contains multiple paragraphs with enough text for trafilatura to extract.
                We need this content to be long enough to pass the article detection heuristic.</p>
                <p>Second paragraph with additional content to ensure proper extraction
                and to provide meaningful test data for the connector implementation.</p>
            </article>
        </body>
        </html>
        """

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, substantial_html):
        """Test retry on network timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = substantial_html
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

            connector = WebScraperConnector({
                "base_url": "https://example.com/article/test",
                "article_url_pattern": r"/article/",
            })
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]
            items = await connector.fetch()

        assert len(items) >= 1
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, substantial_html):
        """Test retry on HTTP 500 server error."""
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_error_response
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.text = substantial_html
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

            connector = WebScraperConnector({
                "base_url": "https://example.com/article/test",
                "article_url_pattern": r"/article/",
            })
            connector.SERVER_ERROR_DELAY = 0.01
            items = await connector.fetch()

        assert len(items) >= 1

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

            connector = WebScraperConnector({"base_url": "https://example.com"})

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

            connector = WebScraperConnector({"base_url": "https://example.com"})

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

            connector = WebScraperConnector({"base_url": "https://example.com"})

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

            connector = WebScraperConnector({"base_url": "https://example.com"})
            connector.RETRY_DELAYS = [0.01, 0.02, 0.04]

            with pytest.raises(ConnectorError, match="Max retries exceeded"):
                await connector.fetch()

        # Initial + 3 retries
        assert mock_client.get.call_count == 4


class TestWebScraperConnectorFallback:
    """Tests for fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_on_parse_failure(self):
        """Test that trafilatura fallback is used when manual parsing fails."""
        # HTML that won't match manual selectors but has extractable content
        html = """
        <html>
        <body>
            <article>
                <h1>Fallback Content Title</h1>
                <p>This is content that should be extracted by trafilatura fallback because
                it contains substantial text that can be recognized as article content. We need
                to ensure the fallback mechanism works correctly.</p>
                <p>Additional paragraphs with more content to ensure proper extraction and
                to provide meaningful test data for the connector implementation testing.</p>
            </article>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = WebScraperConnector({
                "base_url": "https://example.com/article/test",
                "extraction_mode": "manual",
                "article_url_pattern": r"/article/",
                "selectors": {
                    # Selectors that won't match
                    "title": "//h1[@class='nonexistent']",
                    "content": "//div[@class='nonexistent']",
                },
            })
            items = await connector.fetch()

        # Should have extracted content via fallback
        assert len(items) >= 1
        assert len(items[0]["content"]) > 0


class TestWebScraperConnectorHelpers:
    """Tests for helper methods."""

    def test_generate_external_id(self):
        """Test external_id generation from URL."""
        connector = WebScraperConnector({"base_url": "https://example.com"})

        id1 = connector._generate_external_id("https://example.com/article/1")
        id2 = connector._generate_external_id("https://example.com/article/1")
        id3 = connector._generate_external_id("https://example.com/article/2")

        assert id1 == id2  # Same URL should produce same ID
        assert id1 != id3  # Different URL should produce different ID

    def test_parse_date_iso_format(self):
        """Test parsing ISO format date."""
        connector = WebScraperConnector({"base_url": "https://example.com"})

        dt = connector._parse_date("2024-01-15")

        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo == timezone.utc

    def test_parse_date_fallback_to_current_time(self):
        """Test that invalid date falls back to current UTC time."""
        connector = WebScraperConnector({"base_url": "https://example.com"})

        before = datetime.now(timezone.utc)
        dt = connector._parse_date("invalid date string")
        after = datetime.now(timezone.utc)

        assert before <= dt <= after
        assert dt.tzinfo == timezone.utc

    def test_build_headers_default(self):
        """Test building headers with defaults."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        headers = connector._build_headers()

        assert "User-Agent" in headers
        assert "CyberPulseBot" in headers["User-Agent"]
        assert "Accept" in headers

    def test_build_headers_custom(self):
        """Test building headers with custom values."""
        connector = WebScraperConnector({
            "base_url": "https://example.com",
            "user_agent": "MyCustomBot/1.0",
            "headers": {
                "X-Custom-Header": "custom-value",
            },
        })
        headers = connector._build_headers()

        assert headers["User-Agent"] == "MyCustomBot/1.0"
        assert headers["X-Custom-Header"] == "custom-value"

    def test_get_next_page_url(self):
        """Test generating next page URL."""
        connector = WebScraperConnector({"base_url": "https://example.com"})

        next_url = connector._get_next_page_url("https://example.com/articles?page=1", 2, "page")
        assert "page=2" in next_url

    def test_get_next_page_url_no_existing_params(self):
        """Test generating next page URL without existing params."""
        connector = WebScraperConnector({"base_url": "https://example.com"})

        next_url = connector._get_next_page_url("https://example.com/articles", 2, "page")
        assert "page=2" in next_url


class TestWebScraperConnectorMaxItems:
    """Tests for max items limit."""

    @pytest.mark.asyncio
    async def test_fetch_limits_to_max_items(self):
        """Test that fetch respects MAX_ITEMS limit."""
        # Create HTML with many links
        links_html = "<html><body>"
        for i in range(100):
            links_html += f'<a href="https://example.com/article/{i}">Article {i}</a>'
        links_html += "</body></html>"

        article_html = """
        <html><body>
            <article>
                <h1>Article</h1>
                <p>This is a sufficiently long content to be considered an article.
                We need at least 200 characters to pass the heuristic check.</p>
            </article>
        </body></html>
        """

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = article_html
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            connector = WebScraperConnector({"base_url": "https://example.com"})
            items = await connector.fetch()

        assert len(items) <= WebScraperConnector.MAX_ITEMS


class TestWebScraperConnectorHandleError:
    """Tests for _handle_error method."""

    def test_handle_error_timeout(self):
        """Test handling timeout error."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        error = httpx.TimeoutException("Timeout")

        should_retry, delay = connector._handle_error(error, 0)

        assert should_retry is True
        assert delay == 10.0

    def test_handle_error_server_error(self):
        """Test handling server error."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)

        should_retry, delay = connector._handle_error(error, 0)

        assert should_retry is True
        assert delay == 30.0  # SERVER_ERROR_DELAY

    def test_handle_error_auth_failure_raises(self):
        """Test that auth failure raises ConnectorError."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)

        with pytest.raises(ConnectorError, match="Authentication failed"):
            connector._handle_error(error, 0)

    def test_handle_error_not_found_raises(self):
        """Test that 404 raises ConnectorError."""
        connector = WebScraperConnector({"base_url": "https://example.com"})
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_response)

        with pytest.raises(ConnectorError, match="Resource not found"):
            connector._handle_error(error, 0)