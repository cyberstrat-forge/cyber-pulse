"""Tests for SourceQualityValidator."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cyberpulse.services.source_quality_validator import (
    SourceQualityValidator,
    SourceValidationResult,
)


class TestValidateWebSource:
    """Test cases for validate_web_source."""

    @pytest.fixture
    def validator(self):
        return SourceQualityValidator()

    @pytest.mark.asyncio
    async def test_valid_web_source(self, validator):
        """正常 web 源：≥1 篇内容达标即有效。"""
        listing_html = (
            '<html><body><a href="https://example.com/a">A</a>'
            '<a href="https://example.com/b">B</a></body></html>'
        )
        article_html = "<html><body><h1>T</h1><p>" + "x" * 2000 + "</p></body></html>"

        def fake_get(url, follow_redirects=True):
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status = MagicMock()
            r.url = url
            r.text = (
                article_html
                if "/a" in str(url) or "/b" in str(url)
                else listing_html
            )
            return r

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = fake_get
            mock_cls.return_value = mock_client
            result = await validator.validate_web_source({"base_url": "https://example.com/"})

        assert result.is_valid is True
        assert result.content_type == "article"
        assert result.samples_analyzed == 2

    @pytest.mark.asyncio
    async def test_listing_fetch_failure(self, validator):
        """listing 抓取失败 -> is_valid=False + rejection_reason。"""

        def fake_get(url, follow_redirects=True):
            r = MagicMock()
            r.status_code = 500
            r.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=r
            )
            return r

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = fake_get
            mock_cls.return_value = mock_client
            result = await validator.validate_web_source({"base_url": "https://example.com/"})

        assert result.is_valid is False
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_missing_base_url(self, validator):
        """缺 base_url -> is_valid=False。"""
        result = await validator.validate_web_source({})
        assert result.is_valid is False
        assert "base_url" in (result.rejection_reason or "")

    @pytest.mark.asyncio
    async def test_no_links_returns_empty(self, validator):
        """listing 无链接 -> content_type=empty。"""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status = MagicMock()
            r.url = "https://example.com/"
            r.text = "<html><body>no links</body></html>"
            mock_client.get.return_value = r
            mock_cls.return_value = mock_client
            result = await validator.validate_web_source({"base_url": "https://example.com/"})

        assert result.is_valid is False
        assert result.content_type == "empty"

    @pytest.mark.asyncio
    async def test_low_quality_content(self, validator):
        """文章页提取失败 -> is_valid=False。"""
        listing_html = (
            '<html><body><a href="https://example.com/a">A</a></body></html>'
        )
        empty_article = "<html><body></body></html>"

        def fake_get(url, follow_redirects=True):
            r = MagicMock()
            r.status_code = 200
            r.raise_for_status = MagicMock()
            r.url = url
            r.text = empty_article if "/a" in str(url) else listing_html
            return r

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = fake_get
            mock_cls.return_value = mock_client
            result = await validator.validate_web_source({"base_url": "https://example.com/"})

        assert result.is_valid is False
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_threshold_enforced(self, validator):
        """正文质量低于 MIN_AVG_CONTENT_LENGTH -> summary_only + is_valid=False。"""
        with patch.object(
            validator, "_fetch_web_samples",
            new=AsyncMock(return_value=[
                {"title": "T", "content": "x" * 30, "url": "https://example.com/a"},
            ]),
        ):
            result = await validator.validate_web_source({"base_url": "https://example.com/"})

        assert result.is_valid is False
        assert result.content_type == "summary_only"
        assert result.rejection_reason is not None


class TestSourceQualityValidator:
    """Test cases for SourceQualityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = SourceQualityValidator()

    def test_source_validation_result_dataclass(self):
        """Test SourceValidationResult dataclass."""
        result = SourceValidationResult(
            is_valid=True,
            content_type="article",
            sample_completeness=0.8,
            avg_content_length=500,
        )
        assert result.is_valid is True
        assert result.content_type == "article"

    def test_quality_constants(self):
        """Test quality threshold constants."""
        assert self.validator.MIN_SAMPLE_ITEMS == 3
        assert self.validator.MIN_AVG_COMPLETENESS == 0.4
        assert self.validator.MIN_AVG_CONTENT_LENGTH == 50

    @pytest.mark.asyncio
    async def test_validate_source_high_quality(self):
        """Test validation of high-quality source."""
        config = {"feed_url": "https://example.com/feed.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": "x" * 600} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is True
        assert result.sample_completeness >= 0.4

    @pytest.mark.asyncio
    async def test_validate_source_low_quality(self):
        """Test validation of low-quality source (empty content)."""
        config = {"feed_url": "https://example.com/empty.xml"}

        with patch.object(self.validator, "_fetch_samples") as mock_fetch:
            mock_fetch.return_value = [
                {"content": ""} for _ in range(5)
            ]

            result = await self.validator.validate_source(config)

        assert result.is_valid is False
        assert result.rejection_reason is not None

    @pytest.mark.asyncio
    async def test_validate_source_with_force(self):
        """Test validation with force option."""
        config = {"feed_url": "https://example.com/bad.xml"}

        result = await self.validator.validate_source_with_force(
            config,
            force=True,
        )

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_source_missing_feed_url(self):
        """Test validation when feed_url is missing from config."""
        config = {}  # Missing feed_url

        result = await self.validator.validate_source(config)

        assert result.is_valid is False
        assert result.rejection_reason is not None
        assert "feed_url" in result.rejection_reason.lower()

    @pytest.mark.asyncio
    async def test_validate_source_none_feed_url(self):
        """Test validation when feed_url is None."""
        config = {"feed_url": None}

        result = await self.validator.validate_source(config)

        assert result.is_valid is False
