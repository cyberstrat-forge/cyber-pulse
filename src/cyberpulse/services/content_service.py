"""Content service for managing content with deduplication."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.exc import IntegrityError

from .base import BaseService
from ..models import Content, ContentStatus, Item


class ContentService(BaseService):
    """Service for managing content with deduplication."""

    def generate_content_id(self) -> str:
        """
        Generate unique content ID with timestamp prefix for ordering.

        Format: cnt_{YYYYMMDDHHMMSS}_{uuid8}
        Example: cnt_20260319143052_a1b2c3d4

        The timestamp prefix ensures lexicographic ordering matches creation time,
        enabling efficient cursor-based pagination.

        Returns:
            Unique content ID string
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        uuid_str = str(uuid.uuid4()).replace("-", "")[:8]
        return f"cnt_{timestamp}_{uuid_str}"

    def create_or_get_content(
        self,
        canonical_hash: str,
        normalized_title: str,
        normalized_body: str,
        item: Item,
    ) -> Tuple[Content, bool]:
        """
        Create new content or get existing by canonical_hash.

        If content exists (same canonical_hash):
        - Increment source_count
        - Update last_seen_at to current time
        - Link item to existing content (set item.content_id)

        If content is new:
        - Create Content with source_count=1
        - Set first_seen_at and last_seen_at to current time
        - Link item to new content (set item.content_id)

        Args:
            canonical_hash: Hash for deduplication (unique across contents)
            normalized_title: Normalized title text
            normalized_body: Normalized body text
            item: Source item that triggered this content

        Returns:
            Tuple of (content, is_new) where is_new is True if created
        """
        # Check if content exists by canonical_hash
        existing = self.db.query(Content).filter(
            Content.canonical_hash == canonical_hash
        ).first()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if existing:
            # Update existing content
            existing.source_count += 1
            existing.last_seen_at = now

            # Link item to existing content
            item.content_id = existing.content_id

            self.db.commit()
            self.db.refresh(existing)

            return existing, False

        # Create new content
        content_id = self.generate_content_id()

        content = Content(
            content_id=content_id,
            canonical_hash=canonical_hash,
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            first_seen_at=now,
            last_seen_at=now,
            source_count=1,
            status=ContentStatus.ACTIVE,
        )

        # Link item to new content
        item.content_id = content_id

        self.db.add(content)
        try:
            self.db.commit()
            self.db.refresh(content)
            return content, True
        except IntegrityError:
            # Race condition - another request created the content
            self.db.rollback()
            existing = self.db.query(Content).filter(
                Content.canonical_hash == canonical_hash
            ).first()
            if existing:
                # Link item and update existing content
                item.content_id = existing.content_id
                existing.source_count += 1
                existing.last_seen_at = now
                self.db.commit()
                self.db.refresh(existing)
                return existing, False
            raise

    def get_contents(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        source_tier=None,  # SourceTier enum - for future use
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> List[Content]:
        """
        List contents with filters and cursor pagination.

        Contents are ordered by content_id descending (newest first).

        Args:
            since: Filter contents first_seen_at >= since
            until: Filter contents first_seen_at <= until
            source_tier: Filter by source tier (not implemented yet)
            limit: Maximum number of results
            cursor: Content ID cursor for pagination (excludes this and all after)

        Returns:
            List of Content objects
        """
        query = self.db.query(Content)

        # Apply time filters
        if since:
            # Ensure timezone-naive comparison
            since_naive = since.replace(tzinfo=None) if since.tzinfo else since
            query = query.filter(Content.first_seen_at >= since_naive)

        if until:
            until_naive = until.replace(tzinfo=None) if until.tzinfo else until
            query = query.filter(Content.first_seen_at <= until_naive)

        # Apply cursor filter for pagination
        if cursor:
            # Cursor is a content_id - get contents with ID < cursor
            # (since we order descending, we want items before the cursor)
            query = query.filter(Content.content_id < cursor)

        # Order by content_id descending (newest first due to timestamp prefix)
        query = query.order_by(Content.content_id.desc())

        # Apply limit
        query = query.limit(limit)

        return query.all()

    def get_content_by_id(self, content_id: str) -> Optional[Content]:
        """
        Get content by ID.

        Args:
            content_id: Content ID to look up

        Returns:
            Content instance or None if not found
        """
        return self.db.query(Content).filter(
            Content.content_id == content_id
        ).first()

    def get_content_statistics(self) -> Dict[str, Any]:
        """
        Get content statistics.

        Returns:
            Dictionary with statistics:
            - total_contents: Total number of content records
            - total_source_references: Sum of all source_count values
        """
        from sqlalchemy import func

        result = self.db.query(
            func.count(Content.content_id).label("total_contents"),
            func.sum(Content.source_count).label("total_source_references"),
        ).first()

        if result is None:
            return {"total_contents": 0, "total_source_references": 0}

        return {
            "total_contents": result.total_contents or 0,
            "total_source_references": result.total_source_references or 0,
        }