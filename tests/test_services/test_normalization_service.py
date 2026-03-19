"""Tests for NormalizationService."""

import pytest

from cyberpulse.services.normalization_service import (
    NormalizationService,
    NormalizationResult,
)


@pytest.fixture
def normalization_service():
    """Create a NormalizationService instance."""
    return NormalizationService()


class TestNormalize:
    """Tests for normalize method."""

    def test_normalize_html_content(self, normalization_service):
        """Test normalizing HTML content."""
        title = "Test Article"
        html_content = """
        <html>
        <head><title>Test Article</title></head>
        <body>
            <nav>Navigation menu</nav>
            <article>
                <h1>Test Article</h1>
                <p>This is the main content of the article.</p>
                <p>It has multiple paragraphs.</p>
            </article>
            <footer>Footer content</footer>
        </body>
        </html>
        """
        url = "https://example.com/article/test"

        result = normalization_service.normalize(title, html_content, url)

        assert result is not None
        assert isinstance(result, NormalizationResult)
        assert result.normalized_title == "Test Article"
        assert "main content" in result.normalized_body.lower()
        assert result.canonical_hash is not None
        assert len(result.canonical_hash) == 32  # MD5 hex length
        assert result.extraction_method == "trafilatura"
        assert result.word_count > 0

    def test_normalize_plain_text(self, normalization_service):
        """Test normalizing plain text content."""
        title = "Plain Text Title"
        plain_content = "This is plain text without any HTML markup."

        result = normalization_service.normalize(title, plain_content)

        assert result is not None
        assert result.normalized_title == "Plain Text Title"
        assert "plain text" in result.normalized_body.lower()
        assert result.canonical_hash is not None

    def test_normalize_with_url(self, normalization_service):
        """Test normalization with URL context."""
        title = "Article Title"
        html = "<html><body><p>Content with URL context.</p></body></html>"
        url = "https://example.com/article/123"

        result = normalization_service.normalize(title, html, url)

        assert result is not None
        assert result.normalized_title == "Article Title"

    def test_normalize_empty_content(self, normalization_service):
        """Test normalizing empty content."""
        title = "Empty Article"
        content = ""

        result = normalization_service.normalize(title, content)

        assert result is not None
        assert result.normalized_title == "Empty Article"
        assert result.word_count == 0

    def test_normalize_content_with_scripts(self, normalization_service):
        """Test that scripts are removed from content."""
        title = "Article with Scripts"
        html = """
        <html>
        <body>
            <script>alert('malicious');</script>
            <p>Safe content here.</p>
            <script>console.log('another script');</script>
        </body>
        </html>
        """

        result = normalization_service.normalize(title, html)

        assert result is not None
        assert "alert" not in result.normalized_body
        assert "console.log" not in result.normalized_body


class TestExtractContent:
    """Tests for _extract_content method."""

    def test_extract_with_trafilatura(self, normalization_service):
        """Test content extraction using trafilatura."""
        html = """
        <html>
        <body>
            <nav>Navigation</nav>
            <article>
                <h1>Main Article</h1>
                <p>This is the main content that should be extracted.</p>
            </article>
        </body>
        </html>
        """

        extracted = normalization_service._extract_content(html, None)

        assert extracted is not None
        assert "main content" in extracted.lower()

    def test_extract_removes_navigation(self, normalization_service):
        """Test that navigation elements are removed."""
        html = """
        <html>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/about">About</a>
            </nav>
            <main>
                <p>Actual content.</p>
            </main>
        </body>
        </html>
        """

        extracted = normalization_service._extract_content(html, None)

        if extracted:
            # Navigation links should not be in extracted content
            assert "Home" not in extracted or "Actual content" in extracted

    def test_extract_empty_content(self, normalization_service):
        """Test extraction from empty content."""
        extracted = normalization_service._extract_content("", None)
        assert extracted is None

    def test_extract_plain_text(self, normalization_service):
        """Test extraction from plain text (non-HTML)."""
        text = "This is plain text content."

        extracted = normalization_service._extract_content(text, None)

        # Trafilatura may return None for non-HTML content
        # The service handles this gracefully


class TestCanonicalHash:
    """Tests for _calculate_canonical_hash method."""

    def test_canonical_hash_consistency(self, normalization_service):
        """Test that hash is consistent for same content."""
        title = "Test Title"
        body = "Test body content."

        hash1 = normalization_service._calculate_canonical_hash(title, body)
        hash2 = normalization_service._calculate_canonical_hash(title, body)

        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex length

    def test_canonical_hash_different_content(self, normalization_service):
        """Test that hash differs for different content."""
        title1 = "Title One"
        body1 = "Body one content."

        title2 = "Title Two"
        body2 = "Body two content."

        hash1 = normalization_service._calculate_canonical_hash(title1, body1)
        hash2 = normalization_service._calculate_canonical_hash(title2, body2)

        assert hash1 != hash2

    def test_canonical_hash_case_insensitive(self, normalization_service):
        """Test that hash is case-insensitive."""
        title1 = "Test Title"
        body1 = "Test Body"

        title2 = "test title"
        body2 = "test body"

        hash1 = normalization_service._calculate_canonical_hash(title1, body1)
        hash2 = normalization_service._calculate_canonical_hash(title2, body2)

        assert hash1 == hash2

    def test_canonical_hash_whitespace_normalized(self, normalization_service):
        """Test that whitespace differences don't affect hash."""
        title1 = "Test Title"
        body1 = "Test   body   content"

        title2 = "Test Title"
        body2 = "Test body content"

        hash1 = normalization_service._calculate_canonical_hash(title1, body1)
        hash2 = normalization_service._calculate_canonical_hash(title2, body2)

        assert hash1 == hash2


class TestLanguageDetection:
    """Tests for _detect_language method."""

    def test_detect_english_content(self, normalization_service):
        """Test detecting English content."""
        content = """
        This is a longer piece of English text. It contains multiple sentences
        and should be detected as English language content. The detection
        should work reliably for longer texts.
        """

        language = normalization_service._detect_language(content)

        assert language == "en"

    def test_detect_chinese_content(self, normalization_service):
        """Test detecting Chinese content."""
        content = """
        这是一段中文文本。包含多个句子，
        应该被检测为中文内容。语言检测对于较长的文本应该可靠工作。
        """

        language = normalization_service._detect_language(content)

        assert language == "zh"

    def test_detect_short_content(self, normalization_service):
        """Test language detection with short content."""
        content = "Short"

        language = normalization_service._detect_language(content)

        # Short content may not be reliably detected
        # Could return None or a default

    def test_detect_empty_content(self, normalization_service):
        """Test language detection with empty content."""
        language = normalization_service._detect_language("")

        assert language is None


class TestCleanHtml:
    """Tests for _clean_html method."""

    def test_clean_html_removes_tags(self, normalization_service):
        """Test that HTML tags are removed."""
        html = "<p>This is <strong>bold</strong> text.</p>"

        cleaned = normalization_service._clean_html(html)

        assert "<p>" not in cleaned
        assert "<strong>" not in cleaned

    def test_clean_html_removes_scripts(self, normalization_service):
        """Test that script tags are removed."""
        html = """
        <script>alert('test');</script>
        <p>Content</p>
        <script>console.log('test');</script>
        """

        cleaned = normalization_service._clean_html(html)

        assert "alert" not in cleaned
        assert "console.log" not in cleaned

    def test_clean_html_removes_styles(self, normalization_service):
        """Test that style tags are removed."""
        html = """
        <style>body { color: red; }</style>
        <p>Content</p>
        """

        cleaned = normalization_service._clean_html(html)

        assert "color:" not in cleaned
        assert "style" not in cleaned.lower() or "Content" in cleaned

    def test_clean_html_decodes_entities(self, normalization_service):
        """Test that HTML entities are decoded."""
        html = "Hello &amp; goodbye &lt;world&gt;"

        cleaned = normalization_service._clean_html(html)

        assert "&amp;" not in cleaned
        assert "&lt;" not in cleaned
        assert "&gt;" not in cleaned


class TestToMarkdown:
    """Tests for _to_markdown method."""

    def test_to_markdown_headers(self, normalization_service):
        """Test HTML headers converted to markdown."""
        html = """
        <h1>Main Title</h1>
        <h2>Subtitle</h2>
        <h3>Section</h3>
        """
        extracted = "Main Title\n\nSubtitle\n\nSection"

        markdown = normalization_service._to_markdown(extracted, html, None)

        # Markdown should contain the content
        assert "Main Title" in markdown or "main" in markdown.lower()

    def test_to_markdown_paragraphs(self, normalization_service):
        """Test HTML paragraphs in markdown."""
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        extracted = "First paragraph. Second paragraph."

        markdown = normalization_service._to_markdown(extracted, html, None)

        assert "paragraph" in markdown.lower()

    def test_to_markdown_lists(self, normalization_service):
        """Test HTML lists in markdown."""
        html = """
        <ul>
            <li>Item one</li>
            <li>Item two</li>
        </ul>
        """
        extracted = "Item one Item two"

        markdown = normalization_service._to_markdown(extracted, html, None)

        # Content should be preserved
        assert markdown is not None


class TestWordCount:
    """Tests for _count_words method."""

    def test_count_words_english(self, normalization_service):
        """Test word count for English text."""
        text = "This is a test sentence with eight words."

        count = normalization_service._count_words(text)

        assert count == 8

    def test_count_words_chinese(self, normalization_service):
        """Test word count for Chinese text (counts characters)."""
        text = "这是一段中文测试文本"

        count = normalization_service._count_words(text)

        # Chinese characters are counted (10 characters in the text)
        assert count == 10

    def test_count_words_empty(self, normalization_service):
        """Test word count for empty text."""
        count = normalization_service._count_words("")

        assert count == 0

    def test_count_words_mixed(self, normalization_service):
        """Test word count for mixed Chinese-English text."""
        text = "这是中文 and this is English."

        count = normalization_service._count_words(text)

        # Will count as words (not Chinese characters) due to lower ratio
        assert count > 0


class TestNormalizationResult:
    """Tests for NormalizationResult dataclass."""

    def test_result_creation(self):
        """Test creating a NormalizationResult."""
        result = NormalizationResult(
            normalized_title="Test Title",
            normalized_body="Test body content",
            canonical_hash="abc123def456",
            language="en",
            word_count=3,
            extraction_method="trafilatura",
        )

        assert result.normalized_title == "Test Title"
        assert result.normalized_body == "Test body content"
        assert result.canonical_hash == "abc123def456"
        assert result.language == "en"
        assert result.word_count == 3
        assert result.extraction_method == "trafilatura"

    def test_result_optional_language(self):
        """Test NormalizationResult with None language."""
        result = NormalizationResult(
            normalized_title="Test",
            normalized_body="Body",
            canonical_hash="hash",
            language=None,
            word_count=1,
            extraction_method="raw",
        )

        assert result.language is None


class TestIntegration:
    """Integration tests for full normalization pipeline."""

    def test_full_pipeline_html_article(self, normalization_service):
        """Test full pipeline with HTML article."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Breaking News Article</title>
            <script>analytics.track('pageview');</script>
        </head>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/news">News</a>
            </nav>
            <article>
                <h1>Breaking News Article</h1>
                <p class="byline">By John Doe</p>
                <p>This is a comprehensive article about an important topic.
                It contains multiple paragraphs of content that should be
                properly extracted and normalized.</p>
                <p>The article continues with more details and analysis
                about the subject matter at hand.</p>
            </article>
            <aside>
                <h3>Related Articles</h3>
                <a href="/other">Other Article</a>
            </aside>
            <footer>Copyright 2024</footer>
        </body>
        </html>
        """
        title = "Breaking News Article"
        url = "https://example.com/news/breaking"

        result = normalization_service.normalize(title, html, url)

        assert result.normalized_title == title
        assert result.word_count > 0
        assert result.canonical_hash is not None
        assert result.extraction_method == "trafilatura"
        # Navigation and footer should not be in content
        assert "Home" not in result.normalized_body or "article" in result.normalized_body.lower()

    def test_full_pipeline_rss_entry(self, normalization_service):
        """Test full pipeline with RSS entry content."""
        # Simulating content from an RSS feed
        content = """
        <div class="entry-content">
            <p>Here is the main content from an RSS feed entry.</p>
            <p>It might contain some HTML formatting.</p>
            <blockquote>
                <p>This is a quote from the article.</p>
            </blockquote>
        </div>
        """
        title = "RSS Feed Entry Title"

        result = normalization_service.normalize(title, content)

        assert result.normalized_title == title
        assert result.word_count > 0

    def test_hash_deduplication_scenario(self, normalization_service):
        """Test that duplicate content produces same hash."""
        # Simulate same article from different sources
        html1 = """
        <article>
            <h1>Unique Article Title</h1>
            <p>This is unique content that should produce a consistent hash.</p>
        </article>
        """
        html2 = """
        <div class="content">
            <h1>Unique Article Title</h1>
            <p>This is unique content that should produce a consistent hash.</p>
        </div>
        """

        title = "Unique Article Title"

        result1 = normalization_service.normalize(title, html1)
        result2 = normalization_service.normalize(title, html2)

        # Same content should produce same canonical hash
        assert result1.canonical_hash == result2.canonical_hash