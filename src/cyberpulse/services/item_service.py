"""Item service for managing item lifecycle."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict

from sqlalchemy.exc import IntegrityError

from .base import BaseService
from ..models import Item, ItemStatus

logger = logging.getLogger(__name__)


class ItemService(BaseService):
    """Service for managing item lifecycle."""

    def generate_item_id(self) -> str:
        """Generate a unique item ID.

        Format: item_{uuid8}
        """
        uuid_str = str(uuid.uuid4()).replace("-", "")[:8]
        return f"item_{uuid_str}"

    def create_item(
        self,
        source_id: str,
        external_id: str,
        url: str,
        title: str,
        raw_content: str,
        published_at: datetime,
        content_hash: str,
        raw_metadata: Optional[Dict] = None,
    ) -> Item:
        """Create a new item with deduplication.

        Deduplication logic:
        - Check uniqueness by (source_id, external_id) or (source_id, url)
        - If exists, return existing item

        Args:
            source_id: Source ID this item belongs to
            external_id: External identifier from the source
            url: URL of the item
            title: Item title
            raw_content: Raw content of the item
            published_at: Publication timestamp
            content_hash: Hash of the content for deduplication
            raw_metadata: Additional metadata (maps to Item.raw_metadata column)

        Returns:
            Item instance (new or existing if duplicate found)
        """
        # Check for existing item by (source_id, external_id)
        existing = self.db.query(Item).filter(
            Item.source_id == source_id,
            Item.external_id == external_id,
        ).first()

        if existing:
            return existing

        # Check for existing item by (source_id, url)
        existing = self.db.query(Item).filter(
            Item.source_id == source_id,
            Item.url == url,
        ).first()

        if existing:
            return existing

        # Create new item
        item_id = self.generate_item_id()
        fetched_at = datetime.now(timezone.utc)

        item = Item(
            item_id=item_id,
            source_id=source_id,
            external_id=external_id,
            url=url,
            title=title,
            raw_content=raw_content,
            published_at=published_at,
            fetched_at=fetched_at,
            content_hash=content_hash,
            status=ItemStatus.NEW,
            raw_metadata=raw_metadata or {},
        )

        self.db.add(item)
        try:
            self.db.commit()
            self.db.refresh(item)
            return item
        except IntegrityError as e:
            # Race condition - another request created an item with same
            # (source_id, external_id) or (source_id, url)
            logger.debug(f"IntegrityError during item creation, checking for existing: {e}")
            self.db.rollback()
            # Re-check for existing item
            existing = self.db.query(Item).filter(
                Item.source_id == source_id,
                Item.external_id == external_id,
            ).first()
            if existing:
                return existing
            existing = self.db.query(Item).filter(
                Item.source_id == source_id,
                Item.url == url,
            ).first()
            if existing:
                return existing
            # If still not found, re-raise the exception
            raise

    def get_items_by_source(
        self,
        source_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Item]:
        """List items for a source.

        Args:
            source_id: Source ID to filter by
            status: Optional status filter (new, normalized, mapped, rejected)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of Item objects
        """
        query = self.db.query(Item).filter(Item.source_id == source_id)

        if status:
            # Convert string to ItemStatus enum if needed
            if isinstance(status, str):
                status = ItemStatus(status.upper())
            query = query.filter(Item.status == status)

        return (
            query.order_by(Item.published_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def update_item_status(
        self,
        item_id: str,
        status: str,
        quality_metrics: Optional[Dict] = None,
    ) -> Optional[Item]:
        """Update item processing status.

        Args:
            item_id: Item ID to update
            status: New status (new, normalized, mapped, rejected)
            quality_metrics: Optional quality metrics to set
                (meta_completeness, content_completeness, noise_ratio)

        Returns:
            Updated Item or None if not found
        """
        item = self.db.query(Item).filter(Item.item_id == item_id).first()

        if not item:
            return None

        # Convert string to ItemStatus enum if needed
        if isinstance(status, str):
            status = ItemStatus(status.upper())

        item.status = status

        if quality_metrics:
            if "meta_completeness" in quality_metrics:
                item.meta_completeness = quality_metrics["meta_completeness"]
            if "content_completeness" in quality_metrics:
                item.content_completeness = quality_metrics["content_completeness"]
            if "noise_ratio" in quality_metrics:
                item.noise_ratio = quality_metrics["noise_ratio"]

        self.db.commit()
        self.db.refresh(item)

        return item

    def get_pending_items(self, limit: int = 100) -> List[Item]:
        """Get items pending normalization.

        Returns items with status=NEW that need to be processed.

        Args:
            limit: Maximum number of results

        Returns:
            List of Item objects with status=NEW
        """
        return (
            self.db.query(Item)
            .filter(Item.status == ItemStatus.NEW)
            .order_by(Item.fetched_at.asc())
            .limit(limit)
            .all()
        )