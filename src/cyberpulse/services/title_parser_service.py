"""Title parser service for parsing compound RSS titles."""

import re
from dataclasses import dataclass


@dataclass
class ParsedTitle:
    """Result of parsing a compound title."""

    category: str | None
    date: str | None
    title: str
    summary: str | None


class TitleParserService:
    """Service for parsing compound RSS titles.

    Some RSS feeds (e.g., Anthropic Research) have titles that combine
    multiple fields: category, date, actual title, and summary.

    Example: "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides..."
    """

    # Known source-specific patterns
    SOURCE_PATTERNS = {
        "anthropic_research": re.compile(
            r"^(?P<category>[A-Z][a-z]+)"
            r"(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})?"
            r"(?P<title>.+?)"
            r"(?P<summary>This paper provides.*)?$",
            re.DOTALL,
        ),
    }

    # Generic date pattern for fallback
    DATE_PATTERN = re.compile(
        r"\b(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})\b"
    )

    def parse_compound_title(
        self,
        title: str,
        source_name: str | None = None,
    ) -> ParsedTitle:
        """Parse a compound title into its components.

        Args:
            title: The title string to parse.
            source_name: Optional source name for source-specific parsing.

        Returns:
            ParsedTitle with extracted components.
        """
        if not title:
            return ParsedTitle(
                category=None,
                date=None,
                title=title,
                summary=None,
            )

        # Try source-specific pattern
        if source_name:
            source_key = source_name.lower().replace(" ", "_")
            if source_key in self.SOURCE_PATTERNS:
                pattern = self.SOURCE_PATTERNS[source_key]
                match = pattern.match(title)
                if match:
                    return ParsedTitle(
                        category=match.group("category"),
                        date=match.group("date"),
                        title=match.group("title").strip(),
                        summary=match.group("summary"),
                    )

        # Fallback: extract date from title
        date_match = self.DATE_PATTERN.search(title)
        if date_match:
            # Remove date from title
            clean_title = self.DATE_PATTERN.sub("", title).strip()
            return ParsedTitle(
                category=None,
                date=date_match.group("date"),
                title=clean_title,
                summary=None,
            )

        # No parsing possible, return original
        return ParsedTitle(
            category=None,
            date=None,
            title=title,
            summary=None,
        )
