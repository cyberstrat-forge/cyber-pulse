"""Source quality validator for validating RSS sources."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)


@dataclass
class SourceValidationResult:
    """Result of source quality validation."""

    is_valid: bool
    content_type: str  # 'article' | 'summary_only' | 'empty'
    sample_completeness: float
    avg_content_length: int
    rejection_reason: Optional[str] = None
    samples_analyzed: int = 0


class SourceQualityValidator:
    """Validator for RSS source quality.

    Validates that sources meet minimum quality standards before being added.
    """

    # Quality thresholds
    MIN_SAMPLE_ITEMS = 3
    MAX_SAMPLE_ITEMS = 10
    MIN_AVG_COMPLETENESS = 0.4
    MIN_AVG_CONTENT_LENGTH = 50

    # HTTP settings
    REQUEST_TIMEOUT = 30.0

    async def validate_source(
        self,
        source_config: Dict[str, Any],
    ) -> SourceValidationResult:
        """Validate a source's quality.

        Args:
            source_config: Source configuration with 'feed_url'.

        Returns:
            SourceValidationResult with validation outcome.
        """
        feed_url = source_config.get("feed_url")
        if not feed_url:
            return SourceValidationResult(
                is_valid=False,
                content_type="unknown",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Missing feed_url in configuration",
            )

        # Fetch samples
        samples = await self._fetch_samples(feed_url)

        if not samples:
            return SourceValidationResult(
                is_valid=False,
                content_type="empty",
                sample_completeness=0.0,
                avg_content_length=0,
                rejection_reason="Could not fetch any items from feed",
            )

        # Analyze samples
        analysis = self._analyze_samples(samples)

        # Determine content type
        if analysis["avg_content_length"] == 0:
            content_type = "empty"
            rejection_reason = "RSS feed has no content"
        elif analysis["avg_content_length"] < self.MIN_AVG_CONTENT_LENGTH:
            content_type = "summary_only"
            rejection_reason = "RSS content quality below threshold"
        else:
            content_type = "article"
            rejection_reason = None

        # Check if meets quality standards
        is_valid = (
            len(samples) >= self.MIN_SAMPLE_ITEMS
            and analysis["avg_completeness"] >= self.MIN_AVG_COMPLETENESS
            and analysis["avg_content_length"] >= self.MIN_AVG_CONTENT_LENGTH
        )

        return SourceValidationResult(
            is_valid=is_valid,
            content_type=content_type,
            sample_completeness=analysis["avg_completeness"],
            avg_content_length=analysis["avg_content_length"],
            rejection_reason=rejection_reason if not is_valid else None,
            samples_analyzed=len(samples),
        )

    async def validate_source_with_force(
        self,
        source_config: Dict[str, Any],
        force: bool = False,
    ) -> SourceValidationResult:
        """Validate source with option to force acceptance.

        Args:
            source_config: Source configuration.
            force: If True, skip quality validation.

        Returns:
            SourceValidationResult.
        """
        if force:
            return SourceValidationResult(
                is_valid=True,
                content_type="unknown",
                sample_completeness=0.0,
                avg_content_length=0,
            )
        return await self.validate_source(source_config)

    async def _fetch_samples(self, feed_url: str) -> List[Dict[str, Any]]:
        """Fetch sample items from RSS feed.

        Args:
            feed_url: URL of the RSS feed.

        Returns:
            List of sample items with content.
        """
        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                response = await client.get(feed_url, follow_redirects=True)
                response.raise_for_status()
                content = response.content

            feed = feedparser.parse(content)
            entries = feed.get("entries", [])[:self.MAX_SAMPLE_ITEMS]

            samples = []
            for entry in entries:
                # Extract content
                entry_content = ""
                if hasattr(entry, "content") and entry.content:
                    for content_obj in entry.content:
                        if hasattr(content_obj, "value"):
                            entry_content = content_obj.value
                            break
                if not entry_content:
                    entry_content = entry.get("summary") or entry.get("description") or ""

                samples.append({
                    "title": entry.get("title", ""),
                    "content": entry_content,
                    "url": entry.get("link", ""),
                })

            return samples

        except Exception as e:
            logger.error(f"Failed to fetch samples from {feed_url}: {e}")
            return []

    def _analyze_samples(self, samples: List[Dict[str, Any]]) -> Dict[str, float]:
        """Analyze sample content quality.

        Args:
            samples: List of sample items.

        Returns:
            Dictionary with analysis metrics.
        """
        if not samples:
            return {"avg_content_length": 0, "avg_completeness": 0.0}

        total_length = 0
        completeness_scores = []

        for sample in samples:
            content = sample.get("content", "")
            length = len(content)
            total_length += length

            # Calculate completeness score
            if length >= 500:
                completeness_scores.append(1.0)
            elif length >= 200:
                completeness_scores.append(0.7)
            elif length >= 50:
                completeness_scores.append(0.4)
            else:
                completeness_scores.append(0.2)

        return {
            "avg_content_length": int(total_length / len(samples)),
            "avg_completeness": sum(completeness_scores) / len(completeness_scores),
        }