"""Normalization service for content processing."""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

import trafilatura


logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """Result of content normalization."""

    normalized_title: str
    normalized_body: str  # Markdown format
    canonical_hash: str  # For deduplication
    language: Optional[str]
    word_count: int
    extraction_method: str  # "trafilatura" | "raw"


class NormalizationService:
    """Service for content normalization.

    This service handles the normalization pipeline:
    1. Content extraction using trafilatura
    2. HTML cleaning (removing ads, navigation, scripts)
    3. Markdown conversion
    4. Hash calculation for deduplication
    """

    def normalize(
        self,
        title: str,
        raw_content: str,
        url: Optional[str] = None,
    ) -> NormalizationResult:
        """Normalize content.

        Pipeline:
        1. Extract main content using trafilatura (markdown output)
        2. Clean HTML tags, ads, navigation
        3. Calculate canonical_hash

        Args:
            title: The title of the content
            raw_content: Raw HTML or text content
            url: Optional URL for context during extraction

        Returns:
            NormalizationResult with normalized content and metadata
        """
        # Clean the title
        normalized_title = self._clean_text(title)

        # Extract main content directly as markdown (single trafilatura call)
        markdown_body, extraction_method = self._extract_markdown(raw_content, url)

        # Calculate canonical hash for deduplication
        canonical_hash = self._calculate_canonical_hash(
            normalized_title, markdown_body
        )

        # Detect language
        language = self._detect_language(markdown_body)

        # Count words
        word_count = self._count_words(markdown_body)

        return NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=markdown_body,
            canonical_hash=canonical_hash,
            language=language,
            word_count=word_count,
            extraction_method=extraction_method,
        )

    def _extract_markdown(
        self, raw_content: str, url: Optional[str]
    ) -> tuple[str, str]:
        """Extract content as markdown using trafilatura.

        Single call to trafilatura with markdown output format.

        Args:
            raw_content: Raw HTML content
            url: Optional URL for context

        Returns:
            Tuple of (markdown_body, extraction_method)
        """
        if not raw_content:
            return "", "raw"

        # Use trafilatura to extract content as markdown in a single call
        markdown = trafilatura.extract(
            raw_content,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        if markdown:
            # Clean up excessive whitespace
            markdown = self._normalize_markdown(markdown)
            return markdown, "trafilatura"

        # Fallback to raw content cleaning if extraction fails
        return self._clean_html(raw_content), "raw"

    def _clean_html(self, content: str) -> str:
        """Remove HTML tags, ads, navigation.

        If content is HTML, extracts text. If already plain text,
        just cleans whitespace.

        Args:
            content: HTML or text content

        Returns:
            Cleaned text
        """
        if not content:
            return ""

        # Try to extract text from HTML using trafilatura
        extracted = trafilatura.extract(
            content,
            include_comments=False,
            include_tables=True,
        )

        if extracted:
            return extracted

        # Fallback: remove HTML tags manually if trafilatura fails
        # Remove script and style blocks
        cleaned = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # Decode HTML entities
        cleaned = self._decode_html_entities(cleaned)

        # Normalize whitespace
        cleaned = self._clean_text(cleaned)

        return cleaned

    def _calculate_canonical_hash(self, title: str, body: str) -> str:
        """Calculate hash for deduplication.

        Uses MD5 for fast hashing. The hash is calculated from
        normalized title + normalized body to identify duplicate content.

        Args:
            title: Normalized title
            body: Normalized body (Markdown)

        Returns:
            MD5 hash string
        """
        # Normalize for consistent hashing
        normalized_title = title.strip().lower()
        normalized_body = body.strip().lower()

        # Remove extra whitespace for consistent hashing
        normalized_title = " ".join(normalized_title.split())
        normalized_body = " ".join(normalized_body.split())

        # Combine title and body
        content_to_hash = f"{normalized_title}|{normalized_body}"

        # Calculate MD5 hash
        hash_value = hashlib.md5(content_to_hash.encode("utf-8")).hexdigest()

        return hash_value

    def _detect_language(self, content: str) -> Optional[str]:
        """Detect content language.

        Uses trafilatura's built-in language detection.

        Args:
            content: Text content to analyze

        Returns:
            ISO 639-1 language code (e.g., 'en', 'zh') or None if detection fails
        """
        if not content or len(content.strip()) < 20:
            # Need sufficient content for language detection
            return None

        try:
            # Use trafilatura's language detection
            from trafilatura import bare_extraction

            # Create a simple HTML wrapper for detection
            html_wrapper = f"<html><body>{content}</body></html>"
            result = bare_extraction(
                html_wrapper,
                only_with_metadata=False,
            )

            if result and hasattr(result, "language") and result.language:
                return result.language

        except Exception as e:
            # Language detection via trafilatura failed, use heuristic fallback
            logger.debug(f"Trafilatura language detection failed: {e}")

        # Fallback: simple character-based detection for Chinese
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", content))
        total_chars = len(content.strip())

        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            return "zh"

        # Default to English if no other language detected
        # This is a heuristic and may not always be correct
        if total_chars > 50:
            return "en"

        return None

    def _count_words(self, content: str) -> int:
        """Count words in content.

        For Chinese text, counts characters. For other languages,
        counts whitespace-separated words.

        Args:
            content: Text content

        Returns:
            Word count
        """
        if not content:
            return 0

        # Check if content is primarily Chinese
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", content))
        total_chars = len(content.strip())

        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            # Chinese text: count characters (excluding punctuation and spaces)
            return chinese_chars

        # Non-Chinese: count words
        words = content.split()
        return len(words)

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text.

        Removes extra whitespace and decodes HTML entities.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Decode HTML entities
        text = self._decode_html_entities(text)

        # Normalize whitespace
        text = " ".join(text.split())

        return text.strip()

    def _decode_html_entities(self, text: str) -> str:
        """Decode common HTML entities.

        Args:
            text: Text with HTML entities

        Returns:
            Text with decoded entities
        """
        if not text:
            return ""

        # Common HTML entities
        entities = {
            "&nbsp;": " ",
            "&amp;": "&",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": '"',
            "&#39;": "'",
            "&apos;": "'",
            "&hellip;": "...",
            "&mdash;": "-",
            "&ndash;": "-",
            "&bull;": "*",
        }

        for entity, char in entities.items():
            text = text.replace(entity, char)

        # Decode numeric entities
        text = re.sub(
            r"&#(\d+);",
            lambda m: chr(int(m.group(1))),
            text,
        )
        text = re.sub(
            r"&#x([0-9a-fA-F]+);",
            lambda m: chr(int(m.group(1), 16)),
            text,
        )

        return text

    def _normalize_markdown(self, markdown: str) -> str:
        """Normalize markdown content.

        Cleans up excessive whitespace and normalizes formatting.

        Args:
            markdown: Markdown content

        Returns:
            Normalized markdown
        """
        if not markdown:
            return ""

        # Remove excessive blank lines (more than 2 consecutive)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        # Remove trailing whitespace on lines
        markdown = re.sub(r"[ \t]+$", "", markdown, flags=re.MULTILINE)

        # Ensure single newline at end
        markdown = markdown.strip()

        return markdown