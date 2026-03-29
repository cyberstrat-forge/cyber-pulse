# SQLAlchemy Mapped 类型迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目模型层从 SQLAlchemy 1.x Column 风格迁移到 2.0 Mapped[T] 风格，消除 140+ 个 mypy 类型错误。

**Architecture:** 按复杂度递增顺序迁移 6 个模型文件 + 1 个 Mixin，每个文件迁移后立即验证类型检查和测试，确保数据库结构不变。

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Mapped[T], mapped_column, PostgreSQL

---

## 文件结构

| 文件 | 变更类型 | 字段数 | 说明 |
|------|----------|--------|------|
| `src/cyberpulse/models/base.py` | Modify | 2 | TimestampMixin 迁移 |
| `src/cyberpulse/models/settings.py` | Modify | 2 | Settings 模型迁移 |
| `src/cyberpulse/models/api_client.py` | Modify | 8 | ApiClient 模型迁移 |
| `src/cyberpulse/models/item.py` | Modify | 19 + 1关系 | Item 模型迁移 |
| `src/cyberpulse/models/job.py` | Modify | 11 + 1关系 | Job 模型迁移 |
| `src/cyberpulse/models/source.py` | Modify | 27 + 1关系 | Source 模型迁移 |

---

## Task 1: 迁移 TimestampMixin

**Files:**
- Modify: `src/cyberpulse/models/base.py`

- [ ] **Step 1: 迁移 TimestampMixin 到 Mapped 风格**

将 `base.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
from sqlalchemy import Column, DateTime, func


class TimestampMixin:
    """Timestamp mixin for created_at and updated_at"""

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

# After
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Timestamp mixin for created_at and updated_at"""

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: 6 errors in 4 files (枚举字段缺类型注解，其他文件尚未迁移)

- [ ] **Step 3: 运行模型测试**

Run: `uv run pytest tests/test_models.py tests/test_models/ -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: "No new migration operations detected" 或无差异输出

- [ ] **Step 5: 提交 TimestampMixin 迁移**

```bash
git add src/cyberpulse/models/base.py
git commit -m "refactor(models): migrate TimestampMixin to Mapped[T] style

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 迁移 Settings 模型

**Files:**
- Modify: `src/cyberpulse/models/settings.py`

- [ ] **Step 1: 迁移 Settings 模型到 Mapped 风格**

将 `settings.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
"""Settings model for runtime configuration."""

from sqlalchemy import Column, String, Text

from ..database import Base
from .base import TimestampMixin


class Settings(Base, TimestampMixin):
    """Runtime settings stored in database."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)

# After
"""Settings model for runtime configuration."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class Settings(Base, TimestampMixin):
    """Runtime settings stored in database."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: 6 errors in 4 files (其他文件尚未迁移)

- [ ] **Step 3: 运行 Settings 模型测试**

Run: `uv run pytest tests/test_models/test_settings.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: 无差异输出

- [ ] **Step 5: 提交 Settings 模型迁移**

```bash
git add src/cyberpulse/models/settings.py
git commit -m "refactor(models): migrate Settings to Mapped[T] style

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 迁移 ApiClient 模型

**Files:**
- Modify: `src/cyberpulse/models/api_client.py`

- [ ] **Step 1: 迁移 ApiClient 模型到 Mapped 风格**

将 `api_client.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
from enum import StrEnum

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base
from .base import TimestampMixin


class ApiClientStatus(StrEnum):
    """API client status"""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class ApiClient(Base, TimestampMixin):
    """API client for authentication"""
    __tablename__ = "api_clients"

    client_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_key = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(
        SAEnum(ApiClientStatus, name="apiclientstatus"),
        nullable=False,
        default=ApiClientStatus.ACTIVE,
    )
    description = Column(Text, nullable=True)
    permissions = Column(JSONB, nullable=False, default=list)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

# After
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin


class ApiClientStatus(StrEnum):
    """API client status"""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class ApiClient(Base, TimestampMixin):
    """API client for authentication"""
    __tablename__ = "api_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[ApiClientStatus] = mapped_column(default=ApiClientStatus.ACTIVE)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column()
```

**关键变更说明：**
- `status` 字段：移除 `SAEnum()` 包装，`Mapped[ApiClientStatus]` 自动推断枚举类型
- `permissions` 字段：类型注解 `Mapped[list[str]]` 对应 JSONB 存储的列表
- 可空字段：`Mapped[T | None]` 无需 `nullable=True`
- 需添加导入：`datetime`, `Any`, `Mapped`, `mapped_column`

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: 5 errors in 3 files (ApiClient 错误已消除)

- [ ] **Step 3: 运行模型测试**

Run: `uv run pytest tests/test_models.py -v -k ApiClient`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: 无差异输出

- [ ] **Step 5: 提交 ApiClient 模型迁移**

```bash
git add src/cyberpulse/models/api_client.py
git commit -m "refactor(models): migrate ApiClient to Mapped[T] style

- Remove SAEnum wrapper, use Mapped[ApiClientStatus] auto-inference
- Add proper type annotations for JSONB permissions field

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 迁移 Item 模型

**Files:**
- Modify: `src/cyberpulse/models/item.py`

- [ ] **Step 1: 迁移 Item 模型到 Mapped 风格**

将 `item.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin


class ItemStatus(StrEnum):
    """Item processing status"""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PENDING_FULL_FETCH = "PENDING_FULL_FETCH"  # Waiting for full content fetch
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"


class Item(Base, TimestampMixin):
    """Raw item from source with normalized content"""

    __tablename__ = "items"

    item_id = Column(String(64), primary_key=True, index=True)
    source_id = Column(
        String(64), ForeignKey("sources.source_id"), nullable=False, index=True
    )
    external_id = Column(String(255), nullable=False, index=True)
    url = Column(String(1024), nullable=False, index=True)
    title = Column(String(1024), nullable=False)

    # Raw content from source
    raw_content = Column(Text, nullable=True)

    # Normalized content (filled after normalization)
    normalized_title = Column(String(1024), nullable=True)
    normalized_body = Column(Text, nullable=True)
    canonical_hash = Column(String(64), nullable=True)  # For deduplication

    # Metadata
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
    status = Column(
        SAEnum(ItemStatus, name="itemstatus"),
        nullable=False,
        default=ItemStatus.NEW,
    )
    raw_metadata = Column(JSONB, nullable=False, default=dict)

    # Quality metrics (filled after quality check)
    meta_completeness = Column(Float, nullable=True)
    content_completeness = Column(Float, nullable=True)
    noise_ratio = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)

    # Full content fetch status
    full_fetch_attempted = Column(Boolean, nullable=False, default=False)
    full_fetch_succeeded = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
        Index("ix_items_canonical_hash", "canonical_hash"),
    )

    # Relationships
    source = relationship("Source", backref="items", lazy="select")

# After
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin


class ItemStatus(StrEnum):
    """Item processing status"""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PENDING_FULL_FETCH = "PENDING_FULL_FETCH"  # Waiting for full content fetch
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"


class Item(Base, TimestampMixin):
    """Raw item from source with normalized content"""

    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sources.source_id"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(1024), index=True)
    title: Mapped[str] = mapped_column(String(1024))

    # Raw content from source
    raw_content: Mapped[str | None] = mapped_column(Text)

    # Normalized content (filled after normalization)
    normalized_title: Mapped[str | None] = mapped_column(String(1024))
    normalized_body: Mapped[str | None] = mapped_column(Text)
    canonical_hash: Mapped[str | None] = mapped_column(String(64))  # For deduplication

    # Metadata
    published_at: Mapped[datetime] = mapped_column(index=True)
    fetched_at: Mapped[datetime] = mapped_column(index=True)
    status: Mapped[ItemStatus] = mapped_column(default=ItemStatus.NEW)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Quality metrics (filled after quality check)
    meta_completeness: Mapped[float | None] = mapped_column()
    content_completeness: Mapped[float | None] = mapped_column()
    noise_ratio: Mapped[float | None] = mapped_column()
    word_count: Mapped[int | None] = mapped_column()

    # Full content fetch status
    full_fetch_attempted: Mapped[bool] = mapped_column(default=False)
    full_fetch_succeeded: Mapped[bool | None] = mapped_column()

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
        Index("ix_items_canonical_hash", "canonical_hash"),
    )

    # Relationships
    source: Mapped["Source"] = relationship(backref="items", lazy="select")
```

**关键变更说明：**
- `source_id`：非空外键，`Mapped[str]`（无需 `nullable=False`）
- `status`：移除 `SAEnum()`，`Mapped[ItemStatus]` 自动推断
- `raw_metadata`：`Mapped[dict[str, Any]]` 对应 JSONB
- 可空 Float 字段：`Mapped[float | None]` 无需参数
- `full_fetch_attempted`：非空 Boolean 有默认值 → `Mapped[bool]`
- `full_fetch_succeeded`：可空 Boolean → `Mapped[bool | None]`
- `source` relationship：`Mapped["Source"]`（非空外键）
- `__table_args__`：保持不变

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: 3 errors in 2 files (Item 和 ApiClient 错误已消除)

- [ ] **Step 3: 运行 Item 相关测试**

Run: `uv run pytest tests/test_models.py tests/test_services/test_item_service.py tests/test_api/test_items.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: 无差异输出

- [ ] **Step 5: 提交 Item 模型迁移**

```bash
git add src/cyberpulse/models/item.py
git commit -m "refactor(models): migrate Item to Mapped[T] style

- Remove SAEnum wrapper for status field
- Add proper type annotations for JSONB, Float, Boolean fields
- Migrate relationship to Mapped[\"Source\"]

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 迁移 Job 模型

**Files:**
- Modify: `src/cyberpulse/models/job.py`

- [ ] **Step 1: 迁移 Job 模型到 Mapped 风格**

将 `job.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
"""Job model for tracking async task execution."""

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    pass


class JobType(StrEnum):
    """Job type enumeration."""
    INGEST = "INGEST"
    IMPORT = "IMPORT"


class JobStatus(StrEnum):
    """Job status enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base, TimestampMixin):
    """Job tracks async task execution."""
    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True, index=True)
    type = Column(SAEnum(JobType, name="jobtype"), nullable=False)
    status = Column(
        SAEnum(JobStatus, name="jobstatus"),
        nullable=False,
        default=JobStatus.PENDING,
    )

    # For ingest jobs
    source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=True)

    # For import jobs
    file_name = Column(String(255), nullable=True)

    # Results and error info
    result = Column(JSONB, nullable=True)
    error_type = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Tracking
    retry_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    source = relationship("Source", back_populates="jobs")

# After
"""Job model for tracking async task execution."""

from datetime import datetime
from enum import StrEnum
from typing import Any, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    pass


class JobType(StrEnum):
    """Job type enumeration."""
    INGEST = "INGEST"
    IMPORT = "IMPORT"


class JobStatus(StrEnum):
    """Job status enumeration."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base, TimestampMixin):
    """Job tracks async task execution."""
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    type: Mapped[JobType] = mapped_column()
    status: Mapped[JobStatus] = mapped_column(default=JobStatus.PENDING)

    # For ingest jobs
    source_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sources.source_id"))

    # For import jobs
    file_name: Mapped[str | None] = mapped_column(String(255))

    # Results and error info
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_type: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)

    # Tracking
    retry_count: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()

    # Relationships
    source: Mapped["Source | None"] = relationship(back_populates="jobs")
```

**关键变更说明：**
- `type`：无默认值的枚举 → `Mapped[JobType] = mapped_column()`
- `status`：有默认值的枚举 → `Mapped[JobStatus] = mapped_column(default=...)`
- `source_id`：可空外键 → `Mapped[str | None]`
- `result`：可空 JSONB → `Mapped[dict[str, Any] | None]`
- `retry_count`：非空 Integer 有默认值 → `Mapped[int] = mapped_column(default=0)`
- `source` relationship：可空外键 → `Mapped["Source | None"]`
- 需添加导入：`datetime`, `Any`

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: 1 error in 1 file (仅 Source 错误未迁移)

- [ ] **Step 3: 运行 Job 相关测试**

Run: `uv run pytest tests/test_models/test_job.py tests/test_api/test_admin_jobs.py tests/test_tasks/ -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: 无差异输出

- [ ] **Step 5: 提交 Job 模型迁移**

```bash
git add src/cyberpulse/models/job.py
git commit -m "refactor(models): migrate Job to Mapped[T] style

- Remove SAEnum wrapper for type and status fields
- Add proper type annotations for JSONB result field
- Migrate relationship to Mapped[\"Source | None\"] (nullable FK)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 迁移 Source 模型

**Files:**
- Modify: `src/cyberpulse/models/source.py`

这是最复杂的模型，有 27 个字段 + 1 个 relationship。

- [ ] **Step 1: 迁移 Source 模型到 Mapped 风格**

将 `source.py` 从 Column 风格迁移到 Mapped 风格：

```python
# Before
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    pass


class SourceTier(StrEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(StrEnum):
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

    # Statistics
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)

    # Failure tracking
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error_at = Column(DateTime, nullable=True)

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
    last_ingested_at = Column(DateTime, nullable=True)

    # Error tracking fields
    last_error_message = Column(String(255), nullable=True)
    last_job_id = Column(String(64), nullable=True)

    # Collection statistics
    items_last_7d = Column(Integer, nullable=False, default=0)
    last_ingest_result = Column(String(20), nullable=True)  # success, partial, failed

    # Relationships
    jobs = relationship("Job", back_populates="source")

# After
from datetime import datetime
from enum import StrEnum
from typing import Any, TYPE_CHECKING

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .base import TimestampMixin

if TYPE_CHECKING:
    pass


class SourceTier(StrEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(StrEnum):
    """Source status"""
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    REMOVED = "REMOVED"


class Source(Base, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    connector_type: Mapped[str] = mapped_column(String(50))
    tier: Mapped[SourceTier] = mapped_column(default=SourceTier.T2)
    score: Mapped[float] = mapped_column(default=50.0)
    status: Mapped[SourceStatus] = mapped_column(default=SourceStatus.ACTIVE)
    pending_review: Mapped[bool] = mapped_column(default=False)
    review_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Statistics
    last_scored_at: Mapped[datetime | None] = mapped_column()
    total_items: Mapped[int] = mapped_column(default=0)

    # Failure tracking
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    last_error_at: Mapped[datetime | None] = mapped_column()

    # Full content fetch configuration
    needs_full_fetch: Mapped[bool] = mapped_column(default=False)
    full_fetch_threshold: Mapped[float | None] = mapped_column(default=0.7)

    # Source quality markers
    content_type: Mapped[str | None] = mapped_column(String(20))  # 'full' | 'summary' | 'mixed'
    avg_content_length: Mapped[int | None] = mapped_column()
    quality_score: Mapped[float | None] = mapped_column(default=50.0)

    # Full fetch statistics
    full_fetch_success_count: Mapped[int] = mapped_column(default=0)
    full_fetch_failure_count: Mapped[int] = mapped_column(default=0)

    # Scheduling fields
    schedule_interval: Mapped[int | None] = mapped_column()  # seconds, null = not scheduled
    next_ingest_at: Mapped[datetime | None] = mapped_column()
    last_ingested_at: Mapped[datetime | None] = mapped_column()

    # Error tracking fields
    last_error_message: Mapped[str | None] = mapped_column(String(255))
    last_job_id: Mapped[str | None] = mapped_column(String(64))

    # Collection statistics
    items_last_7d: Mapped[int] = mapped_column(default=0)
    last_ingest_result: Mapped[str | None] = mapped_column(String(20))  # success, partial, failed

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(back_populates="source")
```

**关键变更说明：**
- `tier`/`status`：移除 `Enum()` 包装，`Mapped[SourceTier]`/`Mapped[SourceStatus]` 自动推断
- `score`：非空 Float 有默认值 → `Mapped[float]`
- `pending_review`/`needs_full_fetch`：非空 Boolean 有默认值 → `Mapped[bool]`
- `full_fetch_threshold`/`quality_score`：可空 Float 有默认值 → `Mapped[float | None]`
- `config`：非空 JSONB → `Mapped[dict[str, Any]]`
- `avg_content_length`：可空 Integer 无默认值 → `Mapped[int | None]`
- `jobs` relationship：一对多 → `Mapped[list["Job"]]`
- 需添加导入：`datetime`, `Any`

- [ ] **Step 2: 运行模型层类型检查**

Run: `uv run mypy src/cyberpulse/models/ --ignore-missing-imports`
Expected: Success: no issues found in 7 source files

- [ ] **Step 3: 运行 Source 相关测试**

Run: `uv run pytest tests/test_models/test_source_fields.py tests/test_api/test_admin_sources.py tests/test_services/test_source_service.py tests/test_services/test_source_score_service.py -v`
Expected: 所有测试 PASS

- [ ] **Step 4: 验证数据库兼容性**

Run: `uv run alembic check`
Expected: 无差异输出

- [ ] **Step 5: 提交 Source 模型迁移**

```bash
git add src/cyberpulse/models/source.py
git commit -m "refactor(models): migrate Source to Mapped[T] style

- Remove Enum wrapper for tier and status fields
- Add proper type annotations for JSONB, Float, Boolean fields
- Migrate relationship to Mapped[list[\"Job\"]]

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 全量验证

- [ ] **Step 1: 运行全量类型检查**

Run: `uv run mypy src/ --ignore-missing-imports`
Expected: ~9 errors（剩余为非 SQLAlchemy 问题）

剩余问题（预期，不在本次范围）：
- `rss_connector.fetch` 返回类型不兼容
- `datetime` tzinfo 参数冲突
- `avg_content_length` float vs int 类型不匹配

- [ ] **Step 2: 运行全量测试**

Run: `uv run pytest`
Expected: 640 tests passed

- [ ] **Step 3: 运行 Lint 检查**

Run: `uv run ruff check src/ tests/`
Expected: 无错误（或仅有行长度等非关键警告）

- [ ] **Step 4: 最终提交**

将删除旧计划文件的变更一并提交：

```bash
git add docs/superpowers/plans/2026-03-27-type-checking-fix.md
git commit -m "chore: remove outdated type-checking-fix plan

Replaced by SQLAlchemy Mapped migration implementation plan

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 预期结果

### mypy 错误变化

| 类别 | 迁移前 | 迁移后 |
|------|--------|--------|
| SQLAlchemy Column 类型问题 | ~140 | 0 |
| 枚举字段缺类型注解 | 6 | 0 |
| 其他问题（非本次范围） | ~9 | ~9 |
| **总计** | **149** | **~9** |

### 文件变更统计

```
src/cyberpulse/models/base.py      |  8 行变更
src/cyberpulse/models/settings.py  |  8 行变更
src/cyberpulse/models/api_client.py | 15 行变更
src/cyberpulse/models/item.py      | 25 行变更
src/cyberpulse/models/job.py       | 18 行变更
src/cyberpulse/models/source.py    | 30 行变更
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 迁移引入语法错误 | 测试失败 | 每个 Task 后运行模型测试 |
| 类型注解错误 | mypy 新错误 | 每个 Task 后运行类型检查 |
| 运行时行为变化 | 功能异常 | 全量测试验证 |
| Alembic 检测到差异 | 产生意外迁移 | `alembic check` 验证无差异 |
| 导入遗漏 | 运行时错误 | 检查 `datetime`, `Any`, `Mapped`, `mapped_column` 导入 |

---

## 参考资料

- [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [SQLAlchemy ORM Declarative Mapping](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- 设计方案: `docs/superpowers/specs/2026-03-27-sqlalchemy-mapped-migration-design.md`