"""Tests for TitleParserService."""

from cyberpulse.services.title_parser_service import (
    ParsedTitle,
    TitleParserService,
)


class TestTitleParserService:
    """Test cases for TitleParserService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TitleParserService()

    def test_parsed_title_dataclass(self):
        """Test ParsedTitle dataclass."""
        result = ParsedTitle(
            category="AI",
            date="Dec 18, 2024",
            title="Test Title",
            summary=None,
        )
        assert result.category == "AI"
        assert result.date == "Dec 18, 2024"
        assert result.title == "Test Title"

    def test_parse_anthropic_research_title(self):
        """Test parsing Anthropic Research compound title."""
        title = "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides..."
        result = self.service.parse_compound_title(title, source_name="Anthropic Research")

        assert result.category == "Alignment"
        assert result.date == "Dec 18, 2024"
        assert "Alignment faking" in result.title

    def test_parse_title_with_date_no_source(self):
        """Test parsing title with date when no source pattern matches."""
        title = "Some Article Jan 15, 2024 More Text Here"
        result = self.service.parse_compound_title(title)

        assert result.date == "Jan 15, 2024"
        assert result.category is None
        assert "Jan 15, 2024" not in result.title

    def test_parse_simple_title(self):
        """Test parsing simple title without compound structure."""
        title = "Simple Article Title"
        result = self.service.parse_compound_title(title)

        assert result.title == title
        assert result.category is None
        assert result.date is None
        assert result.summary is None

    def test_parse_empty_title(self):
        """Test parsing empty title."""
        result = self.service.parse_compound_title("")

        assert result.title == ""
        assert result.category is None
        assert result.date is None
