# 数据模型重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构数据模型以符合设计文档，移除冗余字段，添加缺失字段，修复数据流链路，集成 JOB 状态更新和源质量验证

**Architecture:**
- Item 模型：移除 `content_id`、`content_hash`，添加 `normalized_title`、`normalized_body`、`canonical_hash`、`word_count`、`language`
- Source 模型：删除 `last_fetched_at`（`last_ingested_at` 已存在）、`fetch_interval`、`is_in_observation`、`observation_until`、`total_contents`
- 移除 Content 模型及相关服务/API
- JOB 状态更新：在 ingestion_tasks 中集成 Job 状态追踪
- 源质量验证：在 Admin Sources API 中集成 SourceQualityValidator

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Alembic, FastAPI, Pydantic

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|---------|------|
| `src/cyberpulse/models/item.py` | 修改 | Item 模型字段变更 |
| `src/cyberpulse/models/source.py` | 修改 | Source 模型字段变更（删除冗余字段） |
| `src/cyberpulse/models/__init__.py` | 修改 | 移除 Content 导出 |
| `src/cyberpulse/models/content.py` | 删除 | Content 模型（不再需要） |
| `src/cyberpulse/services/rss_connector.py` | 修改 | 移除 content_hash 计算 |
| `src/cyberpulse/services/item_service.py` | 修改 | 移除 content_hash 参数 |
| `src/cyberpulse/services/source_service.py` | 修改 | 更新 last_fetched_at → last_ingested_at |
| `src/cyberpulse/tasks/ingestion_tasks.py` | 修改 | 移除 content_hash 参数，更新字段名，集成 Job 状态更新 |
| `src/cyberpulse/tasks/normalization_tasks.py` | 修改 | 存储标准化结果到 Item，集成 TitleParserService |
| `src/cyberpulse/tasks/quality_tasks.py` | 修改 | 移除 ContentService 依赖，直接更新 Item |
| `src/cyberpulse/services/content_service.py` | 删除 | Content 服务（不再需要） |
| `src/cyberpulse/api/routers/content.py` | 删除 | Content API（不再需要） |
| `src/cyberpulse/api/schemas/content.py` | 删除 | Content Schema（不再需要） |
| `src/cyberpulse/api/main.py` | 修改 | 移除 content router |
| `src/cyberpulse/api/routers/items.py` | 修改 | 更新字段映射 |
| `src/cyberpulse/api/routers/admin/sources.py` | 修改 | 移除废弃字段，集成 SourceQualityValidator |
| `src/cyberpulse/api/schemas/item.py` | 修改 | 更新 Item schema |
| `src/cyberpulse/api/schemas/source.py` | 修改 | 更新 Source schema，移除 last_fetched_at |
| `alembic/versions/xxx_data_model_refactor.py` | 新增 | 数据库迁移 |

---

## Task 1: 更新 Item 模型

**Files:**
- Modify: `src/cyberpulse/models/item.py`

- [ ] **Step 1: 编写 Item 模型新版本**

```python
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, Index, Enum as SAEnum, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from ..database import Base
from .base import TimestampMixin


class ItemStatus(str, Enum):
    """Item processing status"""
    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"


class Item(Base, TimestampMixin):
    """Raw item from source with normalized content"""
    __tablename__ = "items"

    item_id = Column(String(64), primary_key=True, index=True)
    source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=False, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    url = Column(String(1024), nullable=False, index=True)
    title = Column(String(1024), nullable=False)

    # Raw content from source
    raw_content = Column(Text, nullable=True)

    # Normalized content (filled after normalization)
    normalized_title = Column(String(1024), nullable=True)
    normalized_body = Column(Text, nullable=True)
    canonical_hash = Column(String(64), nullable=True, index=True)  # For deduplication

    # Metadata
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
    status = Column(SAEnum(ItemStatus, name="itemstatus"), nullable=False, default=ItemStatus.NEW)
    raw_metadata = Column(JSONB, nullable=False, default=dict)

    # Quality metrics (filled after quality check)
    meta_completeness = Column(Float, nullable=True)
    content_completeness = Column(Float, nullable=True)
    noise_ratio = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)
    language = Column(String(10), nullable=True)

    # Full content fetch status
    full_fetch_attempted = Column(Boolean, nullable=False, default=False)
    full_fetch_succeeded = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
        Index("ix_items_canonical_hash", "canonical_hash"),
    )
```

- [ ] **Step 2: 运行测试验证模型定义**

Run: `uv run python -c "from cyberpulse.models import Item; print('Item model OK')"`
Expected: `Item model OK`

---

## Task 2: 更新 Source 模型

**Files:**
- Modify: `src/cyberpulse/models/source.py`

**注意**：`last_ingested_at` 字段已存在于当前模型中，只需删除冗余的 `last_fetched_at`。

- [ ] **Step 1: 编写 Source 模型新版本**

```python
from typing import TYPE_CHECKING
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, Enum, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    from .job import Job


class SourceTier(str, PyEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(str, PyEnum):
    """Source status"""
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    REMOVED = "REMOVED"


class Source(Base, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    connector_type = Column(String(50), nullable=False)
    tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
    score = Column(Float, nullable=False, default=50.0)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    pending_review = Column(Boolean, nullable=False, default=False)
    review_reason = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False, default=dict)

    # Statistics (last_ingested_at already exists, remove last_fetched_at)
    last_ingested_at = Column(DateTime, nullable=True)
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)

    # Failure tracking
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error_at = Column(DateTime, nullable=True)
    last_error_message = Column(String(255), nullable=True)
    last_job_id = Column(String(64), nullable=True)

    # Full content fetch configuration
    needs_full_fetch = Column(Boolean, nullable=False, default=False)
    full_fetch_threshold = Column(Float, nullable=True, default=0.7)

    # Source quality markers
    content_type = Column(String(20), nullable=True)  # 'full' | 'summary' | 'mixed'
    avg_content_length = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True, default=50.0)

    # Full fetch statistics
    full_fetch_success_count = Column(Integer, nullable=False, default=0)
    full_fetch_failure_count = Column(Integer, nullable=False, default=0)

    # Scheduling fields
    schedule_interval = Column(Integer, nullable=True)  # seconds, null = not scheduled
    next_ingest_at = Column(DateTime, nullable=True)

    # Collection statistics
    items_last_7d = Column(Integer, nullable=False, default=0)
    last_ingest_result = Column(String(20), nullable=True)  # success, partial, failed

    # Relationships
    jobs = relationship("Job", back_populates="source")
```

**变更说明**：
- ❌ 删除 `last_fetched_at`（`last_ingested_at` 已存在）
- ❌ 删除 `fetch_interval`（使用 `schedule_interval` 代替）
- ❌ 删除 `is_in_observation`、`observation_until`（废弃字段）
- ❌ 删除 `total_contents`（Content 模型已移除）

- [ ] **Step 2: 运行测试验证模型定义**

Run: `uv run python -c "from cyberpulse.models import Source; print('Source model OK')"`
Expected: `Source model OK`

---

## Task 3: 更新 models/__init__.py

**Files:**
- Modify: `src/cyberpulse/models/__init__.py`

- [ ] **Step 1: 移除 Content 相关导出**

```python
"""SQLAlchemy models for cyberpulse."""

from .base import Base, TimestampMixin
from .item import Item, ItemStatus
from .source import Source, SourceStatus, SourceTier
from .job import Job, JobStatus, JobType
from .api_client import ApiClient, ApiClientStatus
from .settings import Settings

# Content model removed - normalized content stored directly in Item

__all__ = [
    "Base",
    "TimestampMixin",
    "Item",
    "ItemStatus",
    "Source",
    "SourceStatus",
    "SourceTier",
    "Job",
    "JobStatus",
    "JobType",
    "ApiClient",
    "ApiClientStatus",
    "Settings",
]
```

- [ ] **Step 2: 验证导入正确**

Run: `uv run python -c "from cyberpulse.models import Item, Source, Job; print('Models import OK')"`
Expected: `Models import OK`

---

## Task 4: 删除 Content 模型文件

**Files:**
- Delete: `src/cyberpulse/models/content.py`

- [ ] **Step 1: 删除文件**

Run: `rm src/cyberpulse/models/content.py`
Expected: File deleted

---

## Task 5: 更新 RSS Connector

**Files:**
- Modify: `src/cyberpulse/services/rss_connector.py`

- [ ] **Step 1: 移除 content_hash 计算**

修改 `_parse_entry` 方法，移除 `content_hash` 相关代码：

```python
def _parse_entry(self, entry: Any) -> Optional[Dict[str, Any]]:
    """Parse a single RSS entry into standardized format.

    Args:
        entry: feedparser entry object

    Returns:
        Standardized item dictionary or None if entry is invalid
    """
    # Get external_id - prefer guid, fallback to link
    external_id = entry.get("guid") or entry.get("id") or entry.get("link")
    if not external_id:
        return None

    # Get URL - use link
    url = entry.get("link")
    if not url:
        return None

    # Get title
    title = entry.get("title", "")

    # Get content
    content = self._get_content(entry)

    # Parse published date
    published_at = self._parse_date(entry)

    # Get author
    author = entry.get("author", "")

    # Get tags
    tags = []
    if hasattr(entry, "tags") and entry.tags:
        tags = [t.term for t in entry.tags if hasattr(t, "term")]

    return {
        "external_id": external_id,
        "url": url,
        "title": title,
        "published_at": published_at,
        "content": content,
        "author": author,
        "tags": tags,
    }
```

- [ ] **Step 2: 移除 generate_content_hash 方法**

从 `BaseConnector` 或 `RSSConnector` 中移除 `generate_content_hash` 方法（如果存在）。

- [ ] **Step 3: 验证修改**

Run: `uv run python -c "from cyberpulse.services.rss_connector import RSSConnector; print('RSSConnector OK')"`
Expected: `RSSConnector OK`

---

## Task 6: 更新 ingestion_tasks.py

**Files:**
- Modify: `src/cyberpulse/tasks/ingestion_tasks.py`

- [ ] **Step 1: 移除 content_hash 参数，更新字段名**

修改 `ingest_source` 函数中的 item 创建逻辑：

```python
# 在 ingest_source 函数中，修改 item 创建部分
for item_data in items_data:
    try:
        # Check if this is a duplicate before creating
        item = item_service.create_item(
            source_id=source_id,
            external_id=item_data["external_id"],
            url=item_data["url"],
            title=item_data["title"],
            raw_content=item_data.get("content", ""),
            published_at=item_data["published_at"],
            raw_metadata={
                "author": item_data.get("author", ""),
                "tags": item_data.get("tags", []),
            },
        )
        # ... rest of the logic
```

- [ ] **Step 2: 更新 last_fetched_at 为 last_ingested_at**

```python
# 将所有 source.last_fetched_at 改为 source.last_ingested_at
source.last_ingested_at = datetime.now(timezone.utc).replace(tzinfo=None)
```

- [ ] **Step 3: 验证修改**

Run: `uv run python -c "from cyberpulse.tasks.ingestion_tasks import ingest_source; print('ingestion_tasks OK')"`
Expected: `ingestion_tasks OK`

---

## Task 7: 更新 ItemService

**Files:**
- Modify: `src/cyberpulse/services/item_service.py`

- [ ] **Step 1: 移除 content_hash 参数**

修改 `create_item` 方法签名和实现：

```python
def create_item(
    self,
    source_id: str,
    external_id: str,
    url: str,
    title: str,
    raw_content: str = "",
    published_at: Optional[datetime] = None,
    raw_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Item]:
    """Create a new item or return None if duplicate.

    Deduplication is based on (source_id, url) combination.
    canonical_hash will be set during normalization.
    """
    # ... implementation without content_hash
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.services.item_service import ItemService; print('ItemService OK')"`
Expected: `ItemService OK`

---

## Task 8: 更新 SourceService

**Files:**
- Modify: `src/cyberpulse/services/source_service.py`

- [ ] **Step 1: 更新字段引用**

将所有 `last_fetched_at` 引用改为 `last_ingested_at`：

```python
# 在 serialize_source 或类似方法中
"last_ingested_at": source.last_ingested_at.isoformat() if source.last_ingested_at else None,
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.services.source_service import SourceService; print('SourceService OK')"`
Expected: `SourceService OK`

---

## Task 9: 更新 normalization_tasks.py

**Files:**
- Modify: `src/cyberpulse/tasks/normalization_tasks.py`

- [ ] **Step 1: 存储标准化结果到 Item，集成 TitleParserService**

修改 `normalize_item` 函数，将标准化结果直接存储到 Item，并使用 TitleParserService 解析复合标题：

```python
@dramatiq.actor(max_retries=3)
def normalize_item(item_id: str) -> None:
    """Normalize an item.

    This task:
    1. Gets item from database
    2. Runs NormalizationService
    3. Uses TitleParserService for compound titles
    4. Updates item with normalized content
    5. Queues quality check

    Args:
        item_id: The item ID to normalize.
    """
    db = SessionLocal()
    try:
        # Get item from database
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting normalization for item: {item_id}")

        # Initialize services
        normalization_service = NormalizationService()
        title_parser = TitleParserService()

        # Run normalization
        result = normalization_service.normalize(
            title=item.title,  # type: ignore[arg-type]
            raw_content=item.raw_content or "",  # type: ignore[arg-type]
            url=item.url,  # type: ignore[arg-type]
        )

        # Parse compound title if needed (for sources like Anthropic Research)
        source = item.source
        source_name = source.name if source else None
        parsed = title_parser.parse_compound_title(
            result.normalized_title,
            source_name=source_name,
        )
        # Use parsed title if it differs from original
        final_title = parsed.title if parsed.title != result.normalized_title else result.normalized_title

        logger.debug(
            f"Normalization complete for {item_id}: "
            f"word_count={result.word_count}, "
            f"language={result.language}"
        )

        # Store normalized content directly in Item
        item.normalized_title = final_title
        item.normalized_body = result.normalized_body
        item.canonical_hash = result.canonical_hash
        item.word_count = result.word_count
        item.language = result.language

        # Update status to NORMALIZED
        item.status = ItemStatus.NORMALIZED  # type: ignore[assignment]

        db.commit()
        logger.info(f"Normalization complete for item: {item_id}")

        # Queue quality check
        quality_actor = broker.get_actor("quality_check_item")
        quality_actor.send(item_id=item_id)

    except Exception as e:
        logger.error(f"Normalization failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
```

需要在文件顶部添加导入：

```python
from ..services.title_parser_service import TitleParserService
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.tasks.normalization_tasks import normalize_item; print('normalize_item OK')"`
Expected: `normalize_item OK`

---

## Task 10: 更新 quality_tasks.py

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`

- [ ] **Step 1: 移除 ContentService 导入和依赖**

```python
"""Quality check tasks for validating normalized items."""

import logging
from typing import Optional

import dramatiq

from ..database import SessionLocal
from ..models import Item, ItemStatus, Source
from ..services.quality_gate_service import QualityGateService, QualityDecision
from ..services.full_content_fetch_service import FullContentFetchService
from .worker import broker

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def quality_check_item(item_id: str) -> None:
    """Run quality check on an item.

    This task:
    1. Gets item with normalized content
    2. Runs QualityGateService
    3. If pass: mark as MAPPED
    4. If reject: mark as REJECTED

    Args:
        item_id: The item ID to check.
    """
    db = SessionLocal()
    try:
        # Get item from database
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        logger.info(f"Starting quality check for item: {item_id}")

        # Build normalization result from item fields
        from ..services.normalization_service import NormalizationResult

        normalization_result = NormalizationResult(
            normalized_title=item.normalized_title or "",
            normalized_body=item.normalized_body or "",
            canonical_hash=item.canonical_hash or "",
            language=item.language,
            word_count=item.word_count or 0,
            extraction_method="trafilatura",
        )

        # Run quality check
        quality_service = QualityGateService()
        quality_result = quality_service.check(item, normalization_result)

        logger.debug(
            f"Quality check result for {item_id}: "
            f"decision={quality_result.decision.value}, "
            f"warnings={len(quality_result.warnings)}"
        )

        if quality_result.decision == QualityDecision.PASS:
            _handle_pass(db, item, quality_result)
        else:
            _handle_reject(db, item, quality_result)

        db.commit()
        logger.info(
            f"Quality check complete for item {item_id}: "
            f"{quality_result.decision.value}"
        )

    except Exception as e:
        logger.error(f"Quality check failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


def _handle_pass(db, item: Item, quality_result) -> None:
    """Handle a passed quality check.

    Args:
        db: Database session.
        item: The item that passed.
        quality_result: Quality check result with metrics.
    """
    quality_service = QualityGateService()

    # Check if content needs full fetch
    content_validity, content_reason = quality_service._validate_content_quality(
        item.normalized_title or "",
        item.normalized_body or "",
    )

    # Determine if we should trigger full content fetch
    source = getattr(item, "source", None)
    needs_full_fetch = False

    if not content_validity and item.url:
        if source and source.needs_full_fetch:
            needs_full_fetch = True
            logger.info(
                f"Item {item.item_id} needs full fetch: {content_reason}"
            )

    # Update item status and metrics
    item.status = ItemStatus.MAPPED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    logger.info(f"Item {item.item_id} passed quality check")

    # Trigger full content fetch if needed
    if needs_full_fetch and not item.full_fetch_attempted:
        fetch_actor = broker.get_actor("fetch_full_content")
        fetch_actor.send(item.item_id)


def _handle_reject(db, item: Item, quality_result) -> None:
    """Handle a rejected quality check.

    Args:
        db: Database session.
        item: The rejected item.
        quality_result: Quality check result with rejection reason.
    """
    item.status = ItemStatus.REJECTED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Store rejection reason in raw_metadata
    if item.raw_metadata is None:
        item.raw_metadata = {}
    item.raw_metadata["rejection_reason"] = quality_result.rejection_reason
    item.raw_metadata["quality_warnings"] = quality_result.warnings

    logger.warning(
        f"Item {item.item_id} rejected: {quality_result.rejection_reason}"
    )


@dramatiq.actor(max_retries=3)
def recheck_item(item_id: str) -> None:
    """Re-run quality check on an item.

    Args:
        item_id: The item ID to recheck.
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        # Reset status to new and re-process
        item.status = ItemStatus.NEW  # type: ignore[assignment]
        item.normalized_title = None
        item.normalized_body = None
        item.canonical_hash = None
        db.commit()

        # Queue normalization
        normalize_actor = broker.get_actor("normalize_item")
        normalize_actor.send(item_id)

        logger.info(f"Queued re-processing for item: {item_id}")

    except Exception as e:
        logger.error(f"Recheck failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


@dramatiq.actor(max_retries=2)
def fetch_full_content(item_id: str) -> None:
    """Fetch full content for an item.

    Args:
        item_id: The item ID to fetch full content for.
    """
    import asyncio

    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        # Mark as attempted
        item.full_fetch_attempted = True  # type: ignore[assignment]

        if not item.url:
            logger.warning(f"Item {item_id} has no URL, cannot fetch full content")
            db.commit()
            return

        db.commit()

        logger.info(f"Fetching full content for item: {item_id}")

        # Fetch full content
        fetch_service = FullContentFetchService()
        result = asyncio.run(fetch_service.fetch_with_retry(item.url))

        if result.success:
            # Update item with full content
            item.raw_content = result.content
            item.full_fetch_succeeded = True  # type: ignore[assignment]

            # Update source statistics
            source = db.query(Source).filter(Source.source_id == item.source_id).first()
            if source:
                source.full_fetch_success_count = (source.full_fetch_success_count or 0) + 1

            db.commit()
            logger.info(f"Full content fetched for item {item_id}: {len(result.content)} chars")

            # Re-queue normalization with new content
            normalize_actor = broker.get_actor("normalize_item")
            normalize_actor.send(item_id)
        else:
            item.full_fetch_succeeded = False  # type: ignore[assignment]

            # Update source statistics
            source = db.query(Source).filter(Source.source_id == item.source_id).first()
            if source:
                source.full_fetch_failure_count = (source.full_fetch_failure_count or 0) + 1

            db.commit()
            logger.warning(f"Failed to fetch full content for item {item_id}: {result.error}")

    except Exception as e:
        logger.error(f"Full content fetch failed for item {item_id}: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.tasks.quality_tasks import quality_check_item; print('quality_tasks OK')"`
Expected: `quality_tasks OK`

---

## Task 11: 删除 ContentService

**Files:**
- Delete: `src/cyberpulse/services/content_service.py`

- [ ] **Step 1: 删除文件**

Run: `rm src/cyberpulse/services/content_service.py`
Expected: File deleted

---

## Task 12: 更新 Items API Router

**Files:**
- Modify: `src/cyberpulse/api/routers/items.py`

- [ ] **Step 1: 更新字段映射**

修改 `build_item_response` 函数：

```python
def build_item_response(item: Item, source: Optional[Source] = None) -> ItemResponse:
    """Build ItemResponse from Item model."""
    return ItemResponse(
        item_id=item.item_id,
        source_id=item.source_id,
        source_name=source.name if source else None,
        url=item.url,
        title=item.normalized_title or item.title,  # Fallback to original title
        body=item.normalized_body,
        published_at=item.published_at,
        fetched_at=item.fetched_at,
        status=item.status.value,
        language=item.language,
        word_count=item.word_count,
        meta_completeness=item.meta_completeness,
        content_completeness=item.content_completeness,
        noise_ratio=item.noise_ratio,
        full_fetch_attempted=item.full_fetch_attempted,
        full_fetch_succeeded=item.full_fetch_succeeded,
        author=(item.raw_metadata or {}).get("author"),
        tags=(item.raw_metadata or {}).get("tags", []),
    )
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.api.routers.items import router; print('items router OK')"`
Expected: `items router OK`

---

## Task 13: 更新 Item Schema

**Files:**
- Modify: `src/cyberpulse/api/schemas/item.py`

- [ ] **Step 1: 更新 schema 定义**

```python
"""Pydantic schemas for Item API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ItemResponse(BaseModel):
    """Response model for a single item."""

    item_id: str = Field(..., description="Unique item identifier")
    source_id: str = Field(..., description="Source identifier")
    source_name: Optional[str] = Field(None, description="Source name")
    url: str = Field(..., description="Original URL")
    title: str = Field(..., description="Normalized title (fallback to original)")
    body: Optional[str] = Field(None, description="Normalized body content")
    published_at: datetime = Field(..., description="Publication date")
    fetched_at: datetime = Field(..., description="Fetch timestamp")
    status: str = Field(..., description="Processing status")
    language: Optional[str] = Field(None, description="Detected language")
    word_count: Optional[int] = Field(None, description="Word count")
    meta_completeness: Optional[float] = Field(None, description="Metadata completeness score")
    content_completeness: Optional[float] = Field(None, description="Content completeness score")
    noise_ratio: Optional[float] = Field(None, description="Noise ratio")
    full_fetch_attempted: bool = Field(False, description="Whether full fetch was attempted")
    full_fetch_succeeded: Optional[bool] = Field(None, description="Whether full fetch succeeded")
    author: Optional[str] = Field(None, description="Author name")
    tags: List[str] = Field(default_factory=list, description="Tags")


class ItemListResponse(BaseModel):
    """Response model for item list."""

    data: List[ItemResponse]
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
    has_more: bool = Field(False, description="Whether more items exist")
    count: int = Field(..., description="Number of items returned")
    server_timestamp: datetime = Field(..., description="Server timestamp")
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.api.schemas.item import ItemResponse; print('Item schema OK')"`
Expected: `Item schema OK`

---

## Task 14: 更新 Admin Sources Router

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/sources.py`

- [ ] **Step 1: 移除废弃字段**

修改 `build_source_response` 函数，移除 `is_in_observation`, `observation_until`, `fetch_interval`, `total_contents`，将 `last_fetched_at` 改为 `last_ingested_at`：

```python
def build_source_response(source: Source) -> SourceResponse:
    """Build SourceResponse from Source model."""
    warnings = []
    if source.consecutive_failures >= 3:
        warnings.append(f"连续失败 {source.consecutive_failures} 次")
    if source.status == SourceStatus.FROZEN:
        warnings.append("源已冻结")

    return SourceResponse(
        source_id=source.source_id,
        name=source.name,
        connector_type=source.connector_type or "rss",
        tier=source.tier.value if source.tier else "T2",
        score=source.score or 50.0,
        status=source.status.value if source.status else "ACTIVE",
        pending_review=source.pending_review or False,
        review_reason=source.review_reason,
        config=source.config or {},
        last_scored_at=source.last_scored_at,
        total_items=source.total_items or 0,
        schedule_interval=source.schedule_interval,
        next_ingest_at=source.next_ingest_at,
        last_ingested_at=source.last_ingested_at,
        last_ingest_result=source.last_ingest_result,
        items_last_7d=source.items_last_7d or 0,
        consecutive_failures=source.consecutive_failures or 0,
        last_error_at=source.last_error_at,
        last_error_message=source.last_error_message,
        last_job_id=source.last_job_id,
        needs_full_fetch=source.needs_full_fetch or False,
        full_fetch_threshold=source.full_fetch_threshold,
        content_type=source.content_type,
        avg_content_length=source.avg_content_length,
        quality_score=source.quality_score,
        full_fetch_success_count=source.full_fetch_success_count or 0,
        full_fetch_failure_count=source.full_fetch_failure_count or 0,
        warnings=warnings,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )
```

- [ ] **Step 2: 更新 create_source 函数**

移除 `fetch_interval` 参数处理。

- [ ] **Step 3: 更新 update_source 函数**

移除 `fetch_interval` 更新逻辑。

- [ ] **Step 4: 验证修改**

Run: `uv run python -c "from cyberpulse.api.routers.admin.sources import router; print('sources router OK')"`
Expected: `sources router OK`

---

## Task 15: 更新 Source Schema

**Files:**
- Modify: `src/cyberpulse/api/schemas/source.py`

- [ ] **Step 1: 移除废弃字段，添加新字段**

```python
"""Pydantic schemas for Source API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Request model for creating a source."""

    name: str = Field(..., min_length=1, max_length=255, description="Source name")
    connector_type: str = Field(default="rss", description="Connector type")
    tier: str = Field(default="T2", description="Tier: T0, T1, T2, T3")
    score: Optional[float] = Field(None, ge=0, le=100, description="Quality score")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Connector config")


class SourceUpdate(BaseModel):
    """Request model for updating a source."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    tier: Optional[str] = None
    score: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class SourceResponse(BaseModel):
    """Response model for a single source."""

    source_id: str
    name: str
    connector_type: str
    tier: str
    score: float
    status: str
    pending_review: bool
    review_reason: Optional[str]
    config: Dict[str, Any]
    last_scored_at: Optional[datetime]
    total_items: int
    schedule_interval: Optional[int]
    next_ingest_at: Optional[datetime]
    last_ingested_at: Optional[datetime]
    last_ingest_result: Optional[str]
    items_last_7d: int
    consecutive_failures: int
    last_error_at: Optional[datetime]
    last_error_message: Optional[str]
    last_job_id: Optional[str]
    needs_full_fetch: bool
    full_fetch_threshold: Optional[float]
    content_type: Optional[str]
    avg_content_length: Optional[int]
    quality_score: Optional[float]
    full_fetch_success_count: int
    full_fetch_failure_count: int
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SourceListResponse(BaseModel):
    """Response model for source list."""

    data: List[SourceResponse]
    count: int
    offset: int
    limit: int
    server_timestamp: datetime
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.api.schemas.source import SourceResponse; print('Source schema OK')"`
Expected: `Source schema OK`

---

## Task 16: 删除 Content API Router

**Files:**
- Delete: `src/cyberpulse/api/routers/content.py`

- [ ] **Step 1: 删除文件**

Run: `rm src/cyberpulse/api/routers/content.py`
Expected: File deleted

---

## Task 17: 删除 Content Schema

**Files:**
- Delete: `src/cyberpulse/api/schemas/content.py`

- [ ] **Step 1: 删除文件**

Run: `rm src/cyberpulse/api/schemas/content.py`
Expected: File deleted

---

## Task 18: 更新 API Main

**Files:**
- Modify: `src/cyberpulse/api/main.py`

- [ ] **Step 1: 移除 content router 导入和注册**

```python
# 移除这行:
# from .routers import content

# 移除这行:
# app.include_router(content.router, prefix="/api/v1", tags=["content"])
```

- [ ] **Step 2: 验证修改**

Run: `uv run python -c "from cyberpulse.api.main import app; print('API main OK')"`
Expected: `API main OK`

---

## Task 19: 集成 JOB 状态更新

**Files:**
- Modify: `src/cyberpulse/tasks/ingestion_tasks.py`

- [ ] **Step 1: 添加 job_id 参数和状态更新逻辑**

修改 `ingest_source` 函数，添加 Job 状态追踪：

```python
@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str, job_id: str | None = None) -> None:
    """Ingest items from a source.

    This task:
    1. Updates Job status to RUNNING if job_id provided
    2. Fetches items from source
    3. Creates items in database
    4. Queues normalization for each item
    5. Updates source statistics
    6. Updates Job status to COMPLETED/FAILED

    Args:
        source_id: The source ID to ingest from.
        job_id: Optional job ID for status tracking.
    """
    from ..models import Job, JobStatus

    db = SessionLocal()
    job: Job | None = None

    try:
        # Update job status to RUNNING if job_id provided
        if job_id:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
                logger.info(f"Job {job_id} started for source {source_id}")

        # Get source
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            error_msg = f"Source not found: {source_id}"
            logger.error(error_msg)
            if job:
                _mark_job_failed(db, job, "source_not_found", error_msg)
            return

        # ... existing ingestion logic ...

        # Update source statistics on success
        source.last_ingested_at = datetime.now(timezone.utc).replace(tzinfo=None)
        source.consecutive_failures = 0
        source.last_ingest_result = "success"

        # Update job status to COMPLETED
        if job:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.result = {"items_created": new_count, "items_skipped": skip_count}

        db.commit()
        logger.info(f"Ingestion complete for source {source_id}: {new_count} new, {skip_count} skipped")

    except Exception as e:
        logger.error(f"Ingestion failed for source {source_id}: {e}", exc_info=True)
        db.rollback()

        # Update job status to FAILED
        if job:
            _mark_job_failed(db, job, "ingestion_error", str(e))

        # Update source failure tracking
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if source:
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            source.last_error_at = datetime.now(timezone.utc).replace(tzinfo=None)
            source.last_error_message = str(e)[:255]
            source.last_ingest_result = "failed"
            db.commit()

        raise
    finally:
        db.close()


def _mark_job_failed(db: Session, job: Job, error_type: str, error_message: str) -> None:
    """Mark a job as failed.

    Args:
        db: Database session.
        job: The job to mark as failed.
        error_type: Error type classification.
        error_message: Detailed error message.
    """
    job.status = JobStatus.FAILED
    job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    job.error_type = error_type
    job.error_message = error_message[:255] if len(error_message) > 255 else error_message
    db.commit()
    logger.error(f"Job {job.job_id} failed: {error_type} - {error_message}")
```

需要在文件顶部添加导入：

```python
from ..models import Job, JobStatus
```

- [ ] **Step 2: 更新 Admin Jobs API 调用**

修改 `src/cyberpulse/api/routers/admin/jobs.py` 中的 `create_job` 函数，传递 job_id：

```python
@router.post("/jobs", response_model=JobCreatedResponse, status_code=201)
async def create_job(
    request: JobCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobCreatedResponse:
    """Create a manual ingestion job."""
    logger.info(f"Creating job for source: {request.source_id}")

    # Verify source exists
    source = db.query(Source).filter(Source.source_id == request.source_id).first()
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"Source not found: {request.source_id}"
        )

    # Create job
    job = Job(
        job_id=f"job_{secrets.token_hex(8)}",
        type=JobType.INGEST,
        status=JobStatus.PENDING,
        source_id=request.source_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created job: {job.job_id}")

    # Trigger Dramatiq task with job_id
    task_enqueued = False
    try:
        ingest_source.send(request.source_id, job_id=job.job_id)  # 传递 job_id
        task_enqueued = True
        logger.info(f"Triggered ingest_source task for source: {request.source_id}")
    except (OSError, ConnectionError) as e:
        logger.error(f"Failed to trigger ingest_source task for job {job.job_id}: {e}")

    return JobCreatedResponse(
        job_id=job.job_id,
        type=job.type.value,
        status=job.status.value,
        source_id=request.source_id,
        source_name=source.name,
        message="Job created and queued" if task_enqueued else "Job created but task queue unavailable. Job may need manual trigger.",
    )
```

- [ ] **Step 3: 验证修改**

Run: `uv run python -c "from cyberpulse.tasks.ingestion_tasks import ingest_source; print('ingestion_tasks with job tracking OK')"`
Expected: `ingestion_tasks with job tracking OK`

---

## Task 20: 集成 SourceQualityValidator

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/sources.py`

- [ ] **Step 1: 导入 SourceQualityValidator**

```python
from ....services.source_quality_validator import SourceQualityValidator
```

- [ ] **Step 2: 在创建源时进行质量验证**

修改 `create_source` 函数：

```python
@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    source: SourceCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Create a new intelligence source with quality validation."""
    logger.info(f"Creating source: name={source.name}")

    # Check for duplicate name
    existing = db.query(Source).filter(Source.name == source.name).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Source with name '{source.name}' already exists"
        )

    # Run source quality validation
    validator = SourceQualityValidator()
    validation_result = validator.validate_source(source.name, source.config or {})

    if not validation_result.is_valid:
        logger.warning(f"Source quality validation failed: {validation_result.issues}")
        # Still create the source but mark for review
        pending_review = True
        review_reason = "; ".join(validation_result.issues[:3])  # Top 3 issues
    else:
        pending_review = False
        review_reason = None

    # Create source with quality info
    new_source = Source(
        source_id=f"src_{uuid.uuid4().hex[:8]}",
        name=source.name,
        connector_type=source.connector_type,
        tier=SourceTier(source.tier) if source.tier else SourceTier.T2,
        score=source.score or 50.0,
        config=source.config or {},
        pending_review=pending_review,
        review_reason=review_reason,
    )

    db.add(new_source)
    db.commit()
    db.refresh(new_source)

    logger.info(f"Created source: {new_source.source_id}, pending_review={pending_review}")

    return build_source_response(new_source)
```

- [ ] **Step 3: 添加手动验证端点**

添加 `/sources/{source_id}/validate` 端点：

```python
@router.post("/sources/{source_id}/validate")
async def validate_source(
    source_id: str,
    force: bool = Query(False, description="Force re-validation"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Validate source quality and update status."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    validator = SourceQualityValidator()

    if force:
        validation_result = validator.validate_source_with_force(source.name, source.config or {})
    else:
        validation_result = validator.validate_source(source.name, source.config or {})

    # Update source status based on validation
    if validation_result.is_valid:
        source.pending_review = False
        source.review_reason = None
    else:
        source.pending_review = True
        source.review_reason = "; ".join(validation_result.issues[:3])

    db.commit()

    return {
        "source_id": source_id,
        "is_valid": validation_result.is_valid,
        "issues": validation_result.issues,
        "warnings": validation_result.warnings,
        "score": validation_result.score,
    }
```

- [ ] **Step 4: 验证修改**

Run: `uv run python -c "from cyberpulse.api.routers.admin.sources import router; print('sources router with validator OK')"`
Expected: `sources router with validator OK`

---

## Task 21: 创建数据库迁移

**Files:**
- Create: `alembic/versions/xxx_data_model_refactor.py`

- [ ] **Step 1: 创建迁移文件**

Run: `uv run alembic revision -m "data_model_refactor"`
Expected: New migration file created

- [ ] **Step 2: 编写迁移脚本**

```python
"""data model refactor

Revision ID: xxx
Revises: previous_revision
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'xxx'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new columns to items table
    op.add_column('items', sa.Column('normalized_title', sa.String(1024), nullable=True))
    op.add_column('items', sa.Column('normalized_body', sa.Text(), nullable=True))
    op.add_column('items', sa.Column('canonical_hash', sa.String(64), nullable=True))
    op.add_column('items', sa.Column('word_count', sa.Integer(), nullable=True))
    op.add_column('items', sa.Column('language', sa.String(10), nullable=True))

    # Create index on canonical_hash
    op.create_index('ix_items_canonical_hash', 'items', ['canonical_hash'])

    # 2. Drop obsolete columns from sources
    # Note: last_ingested_at already exists, just drop last_fetched_at
    op.drop_column('sources', 'last_fetched_at')
    op.drop_column('sources', 'is_in_observation')
    op.drop_column('sources', 'observation_until')
    op.drop_column('sources', 'fetch_interval')
    op.drop_column('sources', 'total_contents')

    # 3. Drop obsolete columns from items
    op.drop_column('items', 'content_id')
    op.drop_column('items', 'content_hash')

    # 4. Drop contents table (if exists)
    op.drop_table('contents')


def downgrade() -> None:
    # Recreate contents table
    op.create_table(
        'contents',
        sa.Column('content_id', sa.String(64), primary_key=True),
        sa.Column('canonical_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('normalized_title', sa.String(1024), nullable=False),
        sa.Column('normalized_body', sa.Text(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('source_count', sa.Integer(), nullable=False, default=1),
        sa.Column('status', sa.String(20), nullable=False, default='ACTIVE'),
    )

    # Restore items columns
    op.add_column('items', sa.Column('content_id', sa.String(64), sa.ForeignKey('contents.content_id'), nullable=True))
    op.add_column('items', sa.Column('content_hash', sa.String(64), nullable=False))
    op.drop_index('ix_items_canonical_hash', 'items')
    op.drop_column('items', 'normalized_title')
    op.drop_column('items', 'normalized_body')
    op.drop_column('items', 'canonical_hash')
    op.drop_column('items', 'word_count')
    op.drop_column('items', 'language')

    # Restore sources columns
    op.add_column('sources', sa.Column('last_fetched_at', sa.DateTime(), nullable=True))
    op.add_column('sources', sa.Column('is_in_observation', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('sources', sa.Column('observation_until', sa.DateTime(), nullable=True))
    op.add_column('sources', sa.Column('fetch_interval', sa.Integer(), nullable=True))
    op.add_column('sources', sa.Column('total_contents', sa.Integer(), nullable=False, server_default='0'))
```

- [ ] **Step 3: 验证迁移脚本**

Run: `uv run alembic check`
Expected: No errors

---

## Task 22: 运行测试

**Files:**
- Test: All affected files

- [ ] **Step 1: 运行单元测试**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: 运行类型检查**

Run: `uv run mypy src/cyberpulse/ --ignore-missing-imports`
Expected: No errors

- [ ] **Step 3: 运行 lint**

Run: `uv run ruff check src/ tests/`
Expected: No errors

---

## Task 23: 提交变更

- [ ] **Step 1: 暂存所有变更**

Run: `git add -A`

- [ ] **Step 2: 提交**

```bash
git commit -m "$(cat <<'EOF'
refactor: data model restructuring with job tracking and source validation

- Item model: remove content_id, content_hash; add normalized_title, normalized_body, canonical_hash
- Source model: remove fetch_interval, is_in_observation, observation_until, total_contents; rename last_fetched_at to last_ingested_at
- Remove Content model and ContentService
- Update RSS connector to remove content_hash calculation
- Update ingestion/normalization/quality tasks to store normalized content directly in Item
- Add Job status tracking in ingestion_tasks (PENDING → RUNNING → COMPLETED/FAILED)
- Integrate SourceQualityValidator in Admin Sources API
- Add /sources/{source_id}/validate endpoint for manual validation
- Remove Content API endpoints

BREAKING CHANGE: Contents table removed, normalized content now stored in items table

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验证清单

完成所有任务后，验证以下功能正常：

- [ ] 创建新源并触发采集
- [ ] 检查 Item 是否正确存储 normalized_title, normalized_body, canonical_hash
- [ ] 检查 Source.last_ingested_at 正确更新
- [ ] 检查 Items API 返回正确字段
- [ ] 检查 Admin Sources API 返回正确字段
- [ ] 检查全文获取流程正常工作
- [ ] 检查质量门禁正确标记 Item 状态
- [ ] 检查 Job 状态正确更新（PENDING → RUNNING → COMPLETED/FAILED）
- [ ] 检查 Job 详情包含 result 和 error 信息
- [ ] 检查 SourceQualityValidator 在创建源时自动运行
- [ ] 检查 /sources/{source_id}/validate 端点正常工作