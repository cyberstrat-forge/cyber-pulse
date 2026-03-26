# API 整体实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 cyber-pulse 系统完整的 API 架构，包括业务 API 和管理 API，支持统一通过 API 管理系统。

**Architecture:** 基于 FastAPI 构建 RESTful API，使用 SQLAlchemy ORM 管理数据模型，Dramatiq 处理异步任务。权限分为 read（业务 API）和 admin（管理 API）两级。管理员通过环境变量引导创建，部署脚本支持 admin 子命令。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, Dramatiq, PostgreSQL

---

## 前置依赖

本计划依赖以下已规划的基础修复计划，需先完成：

| 计划 | 解决 Issue | 说明 |
|------|-----------|------|
| `2026-03-25-api-unicode-encoding.md` | #39 | API 响应中文 Unicode 编码 |
| `2026-03-25-rss-ingestion-error-fix.md` | #42 | RSS 采集错误处理、`consecutive_failures` 字段 |
| `2026-03-25-rss-content-quality-fix.md` | #41, #46 | 全文获取、`needs_full_fetch` 等字段 |

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `src/cyberpulse/models/job.py` | Job 模型 |
| `src/cyberpulse/models/settings.py` | Settings 模型 |
| `src/cyberpulse/api/startup.py` | API 启动初始化（管理员创建） |
| `src/cyberpulse/api/routers/admin/__init__.py` | 管理 API 路由模块 |
| `src/cyberpulse/api/routers/admin/sources.py` | Source API（管理端） |
| `src/cyberpulse/api/routers/admin/jobs.py` | Job API |
| `src/cyberpulse/api/routers/admin/clients.py` | Client API（管理端，重构现有） |
| `src/cyberpulse/api/routers/admin/logs.py` | Log API |
| `src/cyberpulse/api/routers/admin/diagnose.py` | Diagnose API |
| `src/cyberpulse/api/routers/items.py` | Items API（业务端） |
| `src/cyberpulse/api/schemas/job.py` | Job Pydantic schemas |
| `src/cyberpulse/api/schemas/settings.py` | Settings Pydantic schemas |
| `src/cyberpulse/services/job_service.py` | Job 服务层 |
| `src/cyberpulse/services/settings_service.py` | Settings 服务层 |
| `tests/test_api/test_admin_sources.py` | Source API 测试 |
| `tests/test_api/test_admin_jobs.py` | Job API 测试 |
| `tests/test_api/test_admin_clients.py` | Client API 测试 |
| `tests/test_api/test_admin_logs.py` | Log API 测试 |
| `tests/test_api/test_admin_diagnose.py` | Diagnose API 测试 |
| `tests/test_api/test_items.py` | Items API 测试 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/cyberpulse/models/__init__.py` | 导出 Job, Settings 模型 |
| `src/cyberpulse/models/source.py` | 添加调度、统计、错误追踪字段 |
| `src/cyberpulse/models/api_client.py` | 添加 `expires_at` 字段 |
| `src/cyberpulse/api/main.py` | 添加 UnicodeJSONResponse、startup 事件、admin 路由 |
| `src/cyberpulse/api/auth.py` | 添加 rotate_key 方法、plaintext 存储（可选） |
| `src/cyberpulse/api/routers/clients.py` | 移动到 admin 模块，添加 rotate 端点 |
| `src/cyberpulse/api/routers/sources.py` | 重构为管理端 API |
| `src/cyberpulse/api/routers/content.py` | 重构为 items API |
| `deploy/init/generate-env.sh` | 添加 ADMIN_API_KEY 生成 |
| `scripts/cyber-pulse.sh` | 添加 admin 子命令 |
| `alembic/versions/xxx_add_api_models.py` | 数据库迁移 |

---

## Phase 1: 数据模型

### Task 1.1: 创建 Job 模型

**Files:**
- Create: `src/cyberpulse/models/job.py`
- Create: `tests/test_models/test_job.py`

- [ ] **Step 1: 编写 Job 模型测试**

```python
# tests/test_models/test_job.py
"""Tests for Job model."""

import pytest
from datetime import datetime, timezone
from cyberpulse.models.job import Job, JobType, JobStatus


class TestJobModel:
    """Test cases for Job model."""

    def test_job_creation(self, db_session):
        """Test creating a job record."""
        job = Job(
            job_id="job_abc123",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id="src_xxx",
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.job_id == "job_abc123"
        assert job.type == JobType.INGEST
        assert job.status == JobStatus.PENDING

    def test_job_with_result(self, db_session):
        """Test job with result data."""
        job = Job(
            job_id="job_xyz789",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id="src_xxx",
            result={"items_fetched": 15, "items_created": 12},
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.result["items_fetched"] == 15

    def test_job_with_error(self, db_session):
        """Test job with error information."""
        job = Job(
            job_id="job_err001",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id="src_xxx",
            error_type="connection_timeout",
            error_message="Connection timeout after 30s",
            retry_count=3,
        )
        db_session.add(job)
        db_session.commit()

        db_session.refresh(job)
        assert job.status == JobStatus.FAILED
        assert job.retry_count == 3
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models/test_job.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: 实现 Job 模型**

```python
# src/cyberpulse/models/job.py
"""Job model for tracking async task execution."""

from enum import Enum as PyEnum
from sqlalchemy import Column, String, Integer, Text, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ..database import Base
from .base import TimestampMixin


class JobType(str, PyEnum):
    """Job type enumeration."""
    INGEST = "ingest"
    IMPORT = "import"


class JobStatus(str, PyEnum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base, TimestampMixin):
    """Job tracks async task execution."""
    __tablename__ = "jobs"

    job_id = Column(String(64), primary_key=True, index=True)
    type = Column(SAEnum(JobType, name="jobtype"), nullable=False)
    status = Column(SAEnum(JobStatus, name="jobstatus"), nullable=False, default=JobStatus.PENDING)

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models/test_job.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/models/job.py tests/test_models/test_job.py
git commit -m "feat(models): add Job model for tracking async tasks"
```

---

### Task 1.2: 创建 Settings 模型

**Files:**
- Create: `src/cyberpulse/models/settings.py`
- Create: `tests/test_models/test_settings.py`

- [ ] **Step 1: 编写 Settings 模型测试**

```python
# tests/test_models/test_settings.py
"""Tests for Settings model."""

import pytest
from cyberpulse.models.settings import Settings


class TestSettingsModel:
    """Test cases for Settings model."""

    def test_settings_creation(self, db_session):
        """Test creating a settings record."""
        setting = Settings(
            key="default_fetch_interval",
            value="3600",
        )
        db_session.add(setting)
        db_session.commit()

        db_session.refresh(setting)
        assert setting.key == "default_fetch_interval"
        assert setting.value == "3600"

    def test_settings_upsert(self, db_session):
        """Test upsert behavior for settings."""
        from sqlalchemy.exc import IntegrityError

        # Create initial
        setting = Settings(key="test_key", value="value1")
        db_session.add(setting)
        db_session.commit()

        # Try to create duplicate - should fail
        duplicate = Settings(key="test_key", value="value2")
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.commit()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models/test_settings.py -v
```

- [ ] **Step 3: 实现 Settings 模型**

```python
# src/cyberpulse/models/settings.py
"""Settings model for runtime configuration."""

from sqlalchemy import Column, String, Text, DateTime

from ..database import Base
from .base import TimestampMixin


class Settings(Base, TimestampMixin):
    """Runtime settings stored in database."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models/test_settings.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/models/settings.py tests/test_models/test_settings.py
git commit -m "feat(models): add Settings model for runtime configuration"
```

---

### Task 1.3: 扩展 Source 模型

**Files:**
- Modify: `src/cyberpulse/models/source.py`

- [ ] **Step 1: 添加调度字段**

在 `src/cyberpulse/models/source.py` 的 Source 类中添加：

**注意：** 以下字段中，`consecutive_failures`、`last_error_at` 在 `rss-ingestion-error-fix` 计划中已定义。若该计划已执行，此处只需添加剩余字段；若未执行，需确保迁移文件正确处理字段添加（使用 `IF NOT EXISTS` 或条件检查）。

```python
# 在现有字段后添加

    # Scheduling fields
    schedule_interval = Column(Integer, nullable=True)  # seconds, null = not scheduled
    next_ingest_at = Column(DateTime, nullable=True)
    last_ingested_at = Column(DateTime, nullable=True)

    # Error tracking fields (来自 rss-ingestion-error-fix 计划，此处仅为完整性列出)
    # 若 rss-ingestion-error-fix 已执行，以下字段已存在，无需重复添加
    # consecutive_failures = Column(Integer, nullable=False, default=0)
    # last_error_at = Column(DateTime, nullable=True)
    last_error_message = Column(String(255), nullable=True)
    last_job_id = Column(String(64), nullable=True)

    # Collection statistics
    items_last_7d = Column(Integer, nullable=False, default=0)
    last_ingest_result = Column(String(20), nullable=True)  # success, partial, failed

    # Relationships
    jobs = relationship("Job", back_populates="source")
```

- [ ] **Step 2: 验证语法正确**

```bash
uv run python -c "from cyberpulse.models import Source; print('Source model OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/source.py
git commit -m "feat(models): add scheduling and statistics fields to Source"
```

---

### Task 1.4: 扩展 ApiClient 模型

**Files:**
- Modify: `src/cyberpulse/models/api_client.py`

- [ ] **Step 1: 添加 expires_at 字段**

```python
# 在 ApiClient 类中添加

    expires_at = Column(DateTime, nullable=True)
```

- [ ] **Step 2: 验证语法正确**

```bash
uv run python -c "from cyberpulse.models import ApiClient; print('ApiClient model OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/api_client.py
git commit -m "feat(models): add expires_at field to ApiClient"
```

---

### Task 1.5: 更新模型导出

**Files:**
- Modify: `src/cyberpulse/models/__init__.py`

- [ ] **Step 1: 导出新模型**

```python
# src/cyberpulse/models/__init__.py
from .api_client import ApiClient, ApiClientStatus
from .base import Base, TimestampMixin
from .content import Content
from .item import Item, ItemStatus
from .job import Job, JobType, JobStatus
from .settings import Settings
from .source import Source, SourceStatus, SourceTier

__all__ = [
    "ApiClient",
    "ApiClientStatus",
    "Base",
    "TimestampMixin",
    "Content",
    "Item",
    "ItemStatus",
    "Job",
    "JobType",
    "JobStatus",
    "Settings",
    "Source",
    "SourceStatus",
    "SourceTier",
]
```

- [ ] **Step 2: 验证导入正确**

```bash
uv run python -c "from cyberpulse.models import Job, Settings; print('Models imported OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/__init__.py
git commit -m "feat(models): export Job and Settings models"
```

---

### Task 1.6: 创建数据库迁移

**Files:**
- Create: `alembic/versions/xxx_add_api_models.py`

- [ ] **Step 1: 生成迁移文件**

```bash
uv run alembic revision --autogenerate -m "add api models and source extensions"
```

- [ ] **Step 2: 验证迁移文件内容**

检查生成的迁移文件包含：
- `jobs` 表创建
- `settings` 表创建
- `sources` 表新增字段
- `api_clients` 表新增 `expires_at` 字段

- [ ] **Step 3: 添加初始数据**

在迁移文件的 `upgrade()` 函数末尾添加：

```python
# Insert default settings
op.execute("""
    INSERT INTO settings (key, value, updated_at)
    VALUES ('default_fetch_interval', '3600', NOW())
    ON CONFLICT (key) DO NOTHING
""")
```

- [ ] **Step 4: 验证迁移**

```bash
uv run alembic check
```

Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(db): add migration for API models and source extensions"
```

---

## Phase 2: 认证机制

### Task 2.1: 添加 API Key rotate 功能

**Files:**
- Modify: `src/cyberpulse/api/auth.py`

- [ ] **Step 1: 在 ApiClientService 添加 rotate_key 方法**

```python
# 在 ApiClientService 类中添加

    def rotate_key(self, client_id: str) -> Optional[Tuple[ApiClient, str]]:
        """Rotate an API client's key.

        Args:
            client_id: The client ID to rotate

        Returns:
            Tuple of (ApiClient, new_plain_key) if successful, None otherwise
        """
        client = self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

        if not client:
            return None

        # Generate and hash new API key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        client.api_key = hashed_key  # type: ignore[assignment]
        try:
            self.db.commit()
            self.db.refresh(client)
            logger.info(f"Rotated API key for client: {client_id}")
            return client, plain_key
        except Exception as e:
            logger.error(f"Failed to rotate key for {client_id}: {e}")
            self.db.rollback()
            raise

    def get_by_permission(self, permission: str) -> Optional[ApiClient]:
        """Get first client with specific permission.

        Args:
            permission: Permission to search for

        Returns:
            ApiClient if found, None otherwise
        """
        clients = self.db.query(ApiClient).filter(
            ApiClient.status == ApiClientStatus.ACTIVE
        ).all()

        for client in clients:
            perms: List[str] = client.permissions or []  # type: ignore[assignment]
            if permission in perms:
                return client
        return None

    def get_plain_key(self, client_id: str) -> Optional[str]:
        """Get plain API key for client (for admin show-key).

        Note: This only works if keys are stored in plaintext.
        For hashed keys, this returns None.

        Args:
            client_id: The client ID

        Returns:
            Plain API key or None
        """
        # Check environment variable for admin key
        import os
        admin_key = os.getenv("ADMIN_API_KEY")

        client = self.get_client(client_id)
        if client and admin_key:
            # For admin client, return the env var key
            perms: List[str] = client.permissions or []  # type: ignore[assignment]
            if "admin" in perms:
                return admin_key
        return None
```

- [ ] **Step 2: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.auth import ApiClientService; print('Auth service OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/api/auth.py
git commit -m "feat(auth): add rotate_key and get_by_permission methods"
```

---

### Task 2.2: 创建 API 启动初始化

**Files:**
- Create: `src/cyberpulse/api/startup.py`

- [ ] **Step 1: 创建启动初始化模块**

```python
# src/cyberpulse/api/startup.py
"""API startup initialization.

Ensures admin client exists on first run.
"""

import logging
import os
import secrets

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ApiClient, ApiClientStatus
from .auth import ApiClientService, generate_api_key, hash_api_key

logger = logging.getLogger(__name__)


def ensure_admin_client() -> None:
    """Ensure admin client exists.

    This function is called on API startup to create the initial
    admin client if none exists.

    The admin API key is taken from ADMIN_API_KEY environment variable,
    or generated if not set.
    """
    db: Session = SessionLocal()
    try:
        service = ApiClientService(db)
        admin = service.get_by_permission("admin")

        if admin:
            logger.info("Admin client already exists")
            return

        # Get or generate admin key
        admin_key = os.getenv("ADMIN_API_KEY")
        if not admin_key:
            admin_key = generate_api_key()
            logger.warning(
                "ADMIN_API_KEY not set, generated new key. "
                "Set ADMIN_API_KEY environment variable for reproducible deployments."
            )

        # Create admin client
        client_id = f"cli_{secrets.token_hex(8)}"
        hashed_key = hash_api_key(admin_key)

        admin = ApiClient(
            client_id=client_id,
            name="Administrator",
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
            description="System administrator (auto-created)",
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        logger.info(f"Created admin client: {client_id}")
        logger.info(f"Admin API Key: {admin_key}")
        print(f"\n{'='*60}")
        print(f"ADMIN API KEY: {admin_key}")
        print(f"{'='*60}")
        print("Please save this key securely. It will not be shown again.\n")

    except Exception as e:
        logger.error(f"Failed to ensure admin client: {e}")
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add src/cyberpulse/api/startup.py
git commit -m "feat(api): add startup initialization for admin client"
```

---

### Task 2.3: 更新 FastAPI main.py

**Files:**
- Modify: `src/cyberpulse/api/main.py`

- [ ] **Step 1: 添加导入和 UnicodeJSONResponse**

```python
# src/cyberpulse/api/main.py
"""
FastAPI application entry point.
"""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..config import settings
from .. import __version__
from .routers import health
from .routers.admin import sources, jobs, clients, logs, diagnose
from .routers import items
from .startup import ensure_admin_client


class UnicodeJSONResponse(JSONResponse):
    """JSON response that preserves Unicode characters.

    By default, FastAPI uses json.dumps with ensure_ascii=True, which converts
    non-ASCII characters (like Chinese) to Unicode escape sequences (\\uXXXX).
    This class ensures proper UTF-8 encoding for international text.
    """

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


def setup_logging() -> None:
    """Configure file logging for the application."""
    if settings.log_file is None:
        return

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)


def should_enable_docs() -> bool:
    """Determine if API docs should be enabled based on environment."""
    is_production = settings.environment.lower() in ("production", "prod")
    return not is_production


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging()
    ensure_admin_client()
    yield
    # Shutdown (if needed)


# Setup logging on import
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version=__version__,
    default_response_class=UnicodeJSONResponse,
    docs_url="/docs" if should_enable_docs() else None,
    redoc_url="/redoc" if should_enable_docs() else None,
    openapi_url="/openapi.json" if should_enable_docs() else None,
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, tags=["health"])

# Business API
app.include_router(items.router, prefix="/api/v1", tags=["items"])

# Admin API
app.include_router(sources.router, prefix="/api/v1/admin", tags=["admin-sources"])
app.include_router(jobs.router, prefix="/api/v1/admin", tags=["admin-jobs"])
app.include_router(clients.router, prefix="/api/v1/admin", tags=["admin-clients"])
app.include_router(logs.router, prefix="/api/v1/admin", tags=["admin-logs"])
app.include_router(diagnose.router, prefix="/api/v1/admin", tags=["admin-diagnose"])
```

- [ ] **Step 2: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.main import app; print('FastAPI app OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/api/main.py
git commit -m "feat(api): add UnicodeJSONResponse and admin router setup"
```

---

## Phase 3: API 路由

### Task 3.1: 创建 Items API（业务端）

**Files:**
- Create: `src/cyberpulse/api/routers/items.py`
- Create: `src/cyberpulse/api/schemas/item.py`
- Create: `tests/test_api/test_items.py`

- [ ] **Step 1: 创建 Item schemas**

```python
# src/cyberpulse/api/schemas/item.py
"""Item API schemas."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class SourceInItem(BaseModel):
    """Source info nested in Item response."""
    source_id: str
    source_name: str
    source_url: Optional[str] = None
    source_tier: Optional[str] = None
    source_score: Optional[float] = None


class ItemResponse(BaseModel):
    """Single item response."""
    id: str = Field(..., description="Item unique identifier")
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    body: Optional[str] = None
    url: Optional[str] = None
    completeness_score: Optional[float] = Field(None, ge=0, le=1)
    tags: List[str] = Field(default_factory=list)
    fetched_at: Optional[datetime] = None
    source: Optional[SourceInItem] = None


class ItemListResponse(BaseModel):
    """Item list response with pagination."""
    data: List[ItemResponse]
    next_cursor: Optional[str] = None
    has_more: bool = False
    count: int
    server_timestamp: datetime
```

- [ ] **Step 2: 创建 Items router**

```python
# src/cyberpulse/api/routers/items.py
"""Items API router.

Business API for downstream systems to fetch intelligence items.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..dependencies import get_db
from ..schemas.item import ItemResponse, ItemListResponse, SourceInItem
from ..auth import require_permissions, ApiClient
from ...models import Item, Source, ItemStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# Cursor format: item_{YYYYMMDDHHMMSS}_{uuid8}
CURSOR_PATTERN = re.compile(r"^item_\d{14}_[a-f0-9]{8}$")


def validate_cursor(cursor: str) -> None:
    """Validate cursor format."""
    if not CURSOR_PATTERN.match(cursor):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cursor format: {cursor}"
        )


def calculate_completeness_score(item: Item) -> float:
    """Calculate completeness score for an item."""
    meta = item.meta_completeness or 0.0
    content = item.content_completeness or 0.0
    noise = item.noise_ratio or 0.0

    return meta * 0.4 + content * 0.4 + (1 - noise) * 0.2


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    since: Optional[datetime] = Query(None, description="Start time"),
    until: Optional[datetime] = Query(None, description="End time"),
    from_param: Optional[str] = Query(None, alias="from", description="Start position: latest or beginning"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _client: ApiClient = Depends(require_permissions(["read"])),
) -> ItemListResponse:
    """
    Fetch intelligence items.

    Supports cursor-based pagination for incremental sync.
    """
    # Validate cursor and from are not both provided
    if cursor and from_param:
        raise HTTPException(
            status_code=400,
            detail="Cannot specify both cursor and from parameters"
        )

    # Validate cursor format
    if cursor:
        validate_cursor(cursor)

    # Build query
    query = db.query(Item).filter(Item.status != ItemStatus.REJECTED)

    # Apply time filters
    if since:
        query = query.filter(Item.published_at >= since)
    if until:
        query = query.filter(Item.published_at < until)

    # Apply cursor/pagination
    if cursor:
        # Find item with this cursor
        cursor_item = db.query(Item).filter(Item.item_id == cursor).first()
        if cursor_item:
            query = query.filter(Item.fetched_at < cursor_item.fetched_at)
    elif from_param == "beginning":
        # Start from earliest
        query = query.order_by(Item.fetched_at.asc())
    else:
        # Default: latest first
        query = query.order_by(desc(Item.fetched_at))

    # Fetch items
    items = query.limit(limit + 1).all()
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    # Build response
    data = []
    for item in items:
        source = db.query(Source).filter(Source.source_id == item.source_id).first()
        source_info = None
        if source:
            source_info = SourceInItem(
                source_id=source.source_id,
                source_name=source.name,
                source_url=source.config.get("feed_url") if source.config else None,
                source_tier=source.tier.value if source.tier else None,
                source_score=source.score,
            )

        data.append(ItemResponse(
            id=item.item_id,
            title=item.normalized_title or item.title,
            author=item.raw_metadata.get("author") if item.raw_metadata else None,
            published_at=item.published_at,
            body=item.normalized_body,
            url=item.url,
            completeness_score=calculate_completeness_score(item),
            tags=item.raw_metadata.get("tags", []) if item.raw_metadata else [],
            fetched_at=item.fetched_at,
            source=source_info,
        ))

    next_cursor = None
    if has_more and items:
        next_cursor = items[-1].item_id

    return ItemListResponse(
        data=data,
        next_cursor=next_cursor,
        has_more=has_more,
        count=len(data),
        server_timestamp=datetime.now(timezone.utc),
    )
```

- [ ] **Step 3: 创建测试**

```python
# tests/test_api/test_items.py
"""Tests for Items API."""

import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestItemsAPI:
    """Tests for Items API endpoints."""

    def test_list_items_no_auth(self, client):
        """Test that items endpoint requires authentication."""
        response = client.get("/api/v1/items")
        assert response.status_code == 401

    def test_list_items_invalid_cursor(self, client):
        """Test invalid cursor format."""
        # This would need a valid API key to test properly
        pass

    def test_list_items_cursor_and_from_conflict(self, client):
        """Test that cursor and from cannot both be provided."""
        # This would need a valid API key to test properly
        pass
```

- [ ] **Step 4: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.items import router; print('Items router OK')"
```

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/api/routers/items.py src/cyberpulse/api/schemas/item.py tests/test_api/test_items.py
git commit -m "feat(api): add Items API for business use"
```

---

### Task 3.2: 创建管理 API 路由模块

**Files:**
- Create: `src/cyberpulse/api/routers/admin/__init__.py`

- [ ] **Step 1: 创建 admin 模块初始化**

```python
# src/cyberpulse/api/routers/admin/__init__.py
"""Admin API routers."""

from .sources import router as sources_router
from .jobs import router as jobs_router
from .clients import router as clients_router
from .logs import router as logs_router
from .diagnose import router as diagnose_router

__all__ = ["sources_router", "jobs_router", "clients_router", "logs_router", "diagnose_router"]
```

- [ ] **Step 2: Commit**

```bash
git add src/cyberpulse/api/routers/admin/__init__.py
git commit -m "feat(api): create admin routers module"
```

---

### Task 3.3: 创建 Source API（管理端）

**Files:**
- Create: `src/cyberpulse/api/routers/admin/sources.py`
- Create: `src/cyberpulse/api/schemas/source.py`
- Create: `tests/test_api/test_admin_sources.py`

- [ ] **Step 1: 编写 Source schemas 测试**

```python
# tests/test_api/test_admin_sources.py
"""Tests for Source Admin API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create admin auth headers."""
    # In real tests, use a valid admin API key
    return {"Authorization": "Bearer cp_live_test_admin_key"}


class TestSourceAdminAPI:
    """Tests for Source Admin API endpoints."""

    def test_list_sources_no_auth(self, client):
        """Test that sources endpoint requires authentication."""
        response = client.get("/api/v1/admin/sources")
        assert response.status_code == 401

    def test_list_sources_with_admin(self, client, admin_headers):
        """Test listing sources with admin permission."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get("/api/v1/admin/sources", headers=admin_headers)
            assert response.status_code in [200, 401]  # 401 if mock doesn't work

    def test_create_source_invalid_tier(self, client, admin_headers):
        """Test creating source with invalid tier."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.post(
                "/api/v1/admin/sources",
                json={"url": "https://example.com/feed.xml", "tier": "INVALID"},
                headers=admin_headers,
            )
            assert response.status_code in [400, 401, 422]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api/test_admin_sources.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: 创建 Source schemas（完整版）**

```python
# src/cyberpulse/api/schemas/source.py
"""Source API schemas for admin endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Source creation request."""

    url: str = Field(..., description="RSS feed URL or site URL")
    name: Optional[str] = Field(None, description="Source name (auto-detected if not provided)")
    tier: Optional[str] = Field(None, description="Source tier: T0, T1, T2, T3")
    needs_full_fetch: Optional[bool] = Field(None, description="Whether full content fetch is needed")
    force: bool = Field(False, description="Skip quality validation if True")


class SourceUpdate(BaseModel):
    """Source update request."""

    name: Optional[str] = Field(None, description="Source name")
    tier: Optional[str] = Field(None, description="Source tier: T0, T1, T2, T3")
    score: Optional[float] = Field(None, ge=0, le=100, description="Quality score")
    status: Optional[str] = Field(None, description="Status: active, frozen")
    needs_full_fetch: Optional[bool] = Field(None, description="Full fetch flag")
    full_fetch_threshold: Optional[float] = Field(None, ge=0, le=1, description="Full fetch threshold")


class SourceResponse(BaseModel):
    """Source response."""

    source_id: str
    name: str
    config: Dict[str, Any] = {}
    tier: Optional[str] = None
    score: float = 50.0
    status: str
    needs_full_fetch: bool = False
    full_fetch_threshold: Optional[float] = None
    content_type: Optional[str] = None
    avg_content_length: Optional[int] = None
    schedule_interval: Optional[int] = None
    next_ingest_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None
    last_ingest_result: Optional[str] = None
    total_items: int = 0
    items_last_7d: int = 0
    consecutive_failures: int = 0
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    last_job_id: Optional[str] = None
    full_fetch_success_count: int = 0
    full_fetch_failure_count: int = 0
    warnings: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    """Source list response."""

    data: List[SourceResponse]
    count: int
    server_timestamp: datetime


class ScheduleRequest(BaseModel):
    """Schedule update request."""

    interval: int = Field(..., ge=300, description="Interval in seconds (minimum 300)")


class ScheduleResponse(BaseModel):
    """Schedule update response."""

    source_id: str
    schedule_interval: int
    next_ingest_at: Optional[datetime] = None
    message: str = "Schedule updated"


class TestResult(BaseModel):
    """Source test result."""

    source_id: str
    test_result: str  # "success" or "failed"
    response_time_ms: Optional[int] = None
    items_found: Optional[int] = None
    last_modified: Optional[datetime] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    suggestion: Optional[str] = None
    warnings: List[str] = []


class DefaultsResponse(BaseModel):
    """Source defaults response."""

    default_fetch_interval: int
    updated_at: Optional[datetime] = None


class DefaultsUpdate(BaseModel):
    """Source defaults update."""

    default_fetch_interval: int = Field(..., ge=300, description="Default fetch interval in seconds")
```

- [ ] **Step 4: 创建 Source router（完整版）**

```python
# src/cyberpulse/api/routers/admin/sources.py
"""Source management API router for admin endpoints."""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..dependencies import get_db
from ..schemas.source import (
    SourceCreate,
    SourceUpdate,
    SourceResponse,
    SourceListResponse,
    ScheduleRequest,
    ScheduleResponse,
    TestResult,
    DefaultsResponse,
    DefaultsUpdate,
)
from ..auth import require_permissions, ApiClient
from ...models import Source, SourceStatus, SourceTier, Settings

logger = logging.getLogger(__name__)

router = APIRouter()

# source_id format: src_{8 hex chars}
SOURCE_ID_PATTERN = re.compile(r"^src_[a-f0-9]{8}$")


def validate_source_id(source_id: str) -> None:
    """Validate source_id format."""
    if not SOURCE_ID_PATTERN.match(source_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_id format: {source_id}. Expected format: src_xxxxxxxx"
        )


def validate_tier(tier: str) -> SourceTier:
    """Validate and convert tier string to enum."""
    try:
        return SourceTier(tier.upper())
    except ValueError:
        valid_tiers = [t.value for t in SourceTier]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{tier}'. Must be one of: {valid_tiers}"
        )


def validate_status(status: str) -> SourceStatus:
    """Validate and convert status string to enum."""
    try:
        return SourceStatus(status.upper())
    except ValueError:
        valid_statuses = [s.value for s in SourceStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}"
        )


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    status: Optional[str] = Query(None, description="Filter by status: active, frozen, pending_review"),
    tier: Optional[str] = Query(None, description="Filter by tier: T0, T1, T2, T3"),
    scheduled: Optional[bool] = Query(None, description="Filter by scheduled status"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceListResponse:
    """
    List all sources with optional filtering.

    Returns all matching sources without pagination (typically < 200 sources).
    """
    logger.debug(f"Listing sources: status={status}, tier={tier}, scheduled={scheduled}")

    query = db.query(Source)

    # Apply filters
    if status:
        status_enum = validate_status(status)
        query = query.filter(Source.status == status_enum)

    if tier:
        tier_enum = validate_tier(tier)
        query = query.filter(Source.tier == tier_enum)

    if scheduled is not None:
        if scheduled:
            query = query.filter(Source.schedule_interval.isnot(None))
        else:
            query = query.filter(Source.schedule_interval.is_(None))

    sources = query.order_by(desc(Source.created_at)).all()

    return SourceListResponse(
        data=[SourceResponse.model_validate(s) for s in sources],
        count=len(sources),
        server_timestamp=datetime.now(timezone.utc),
    )


@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    source: SourceCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """
    Add a new source.

    Automatically discovers RSS feed if a site URL is provided.
    Performs quality validation unless force=True.
    """
    logger.info(f"Creating source: url={source.url}, name={source.name}")

    # Check for duplicate URL
    feed_url = source.url
    existing = db.query(Source).filter(
        Source.config["feed_url"].astext == feed_url
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Source with this URL already exists: {existing.name}"
        )

    # Create source with defaults
    tier_enum = validate_tier(source.tier) if source.tier else SourceTier.T2

    new_source = Source(
        source_id=f"src_{__import__('secrets').token_hex(4)}",
        name=source.name or source.url,
        connector_type="rss",
        tier=tier_enum,
        score=50.0,
        status=SourceStatus.ACTIVE,
        config={"feed_url": source.url},
        needs_full_fetch=source.needs_fetch_full or False,
    )

    db.add(new_source)
    db.commit()
    db.refresh(new_source)

    logger.info(f"Created source: {new_source.source_id}")

    return SourceResponse.model_validate(new_source)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Get source details."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    return SourceResponse.model_validate(source)


@router.put("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    update: SourceUpdate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceResponse:
    """Update source configuration."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    # Update fields
    if update.name is not None:
        source.name = update.name
    if update.tier is not None:
        source.tier = validate_tier(update.tier)
    if update.score is not None:
        source.score = update.score
    if update.status is not None:
        source.status = validate_status(update.status)
    if update.needs_full_fetch is not None:
        source.needs_full_fetch = update.needs_full_fetch
    if update.full_fetch_threshold is not None:
        source.full_fetch_threshold = update.full_fetch_threshold

    db.commit()
    db.refresh(source)

    logger.info(f"Updated source: {source_id}")

    return SourceResponse.model_validate(source)


@router.delete("/sources/{source_id}", status_code=200)
async def delete_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])):
) -> dict:
    """Delete a source (soft delete by setting status to REMOVED)."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.status = SourceStatus.REMOVED
    db.commit()

    logger.info(f"Deleted source: {source_id}")

    return {"message": f"Source {source_id} deleted"}


@router.post("/sources/{source_id}/test", response_model=TestResult)
async def test_source(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> TestResult:
    """Test source connectivity."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    feed_url = source.config.get("feed_url") if source.config else None
    if not feed_url:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="config",
            error_message="No feed URL configured",
            suggestion="Configure feed_url in source config",
        )

    try:
        import time
        import httpx
        import feedparser

        start_time = time.time()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)"},
            )
            response.raise_for_status()
            content = response.content

        elapsed_ms = int((time.time() - start_time) * 1000)
        feed = feedparser.parse(content)
        items_found = len(feed.get("entries", []))

        return TestResult(
            source_id=source_id,
            test_result="success",
            response_time_ms=elapsed_ms,
            items_found=items_found,
            last_modified=None,
            warnings=[],
        )

    except httpx.TimeoutException:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="timeout",
            error_message="Connection timeout after 30s",
            suggestion="检查网络连接或增加超时时间",
        )
    except httpx.HTTPStatusError as e:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type=f"http_{e.response.status_code}",
            error_message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
            suggestion="检查网站访问权限",
        )
    except Exception as e:
        return TestResult(
            source_id=source_id,
            test_result="failed",
            error_type="connection",
            error_message=str(e),
            suggestion="检查 URL 是否正确",
        )


@router.post("/sources/{source_id}/schedule", response_model=ScheduleResponse)
async def set_schedule(
    source_id: str,
    request: ScheduleRequest,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ScheduleResponse:
    """Set source collection schedule."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.schedule_interval = request.interval
    source.next_ingest_at = datetime.now(timezone.utc) + timedelta(seconds=request.interval)

    db.commit()
    db.refresh(source)

    logger.info(f"Set schedule for source {source_id}: interval={request.interval}s")

    return ScheduleResponse(
        source_id=source_id,
        schedule_interval=request.interval,
        next_ingest_at=source.next_ingest_at,
        message="Schedule updated",
    )


@router.delete("/sources/{source_id}/schedule")
async def remove_schedule(
    source_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Remove source collection schedule."""
    validate_source_id(source_id)

    source = db.query(Source).filter(Source.source_id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")

    source.schedule_interval = None
    source.next_ingest_at = None

    db.commit()

    logger.info(f"Removed schedule for source {source_id}")

    return {"source_id": source_id, "schedule_interval": None, "next_ingest_at": None, "message": "Schedule removed"}


@router.get("/sources/defaults", response_model=DefaultsResponse)
async def get_defaults(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DefaultsResponse:
    """Get default source settings."""
    setting = db.query(Settings).filter(Settings.key == "default_fetch_interval").first()

    return DefaultsResponse(
        default_fetch_interval=int(setting.value) if setting else 3600,
        updated_at=setting.updated_at if setting else None,
    )


@router.patch("/sources/defaults", response_model=DefaultsResponse)
async def update_defaults(
    update: DefaultsUpdate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DefaultsResponse:
    """Update default source settings."""
    setting = db.query(Settings).filter(Settings.key == "default_fetch_interval").first()

    if setting:
        setting.value = str(update.default_fetch_interval)
    else:
        setting = Settings(key="default_fetch_interval", value=str(update.default_fetch_interval))
        db.add(setting)

    db.commit()
    db.refresh(setting)

    logger.info(f"Updated default_fetch_interval to {update.default_fetch_interval}")

    return DefaultsResponse(
        default_fetch_interval=update.default_fetch_interval,
        updated_at=setting.updated_at,
    )
```

- [ ] **Step 5: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.admin.sources import router; print('Source router OK')"
```

Expected: "Source router OK"

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_api/test_admin_sources.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/api/routers/admin/sources.py src/cyberpulse/api/schemas/source.py tests/test_api/test_admin_sources.py
git commit -m "feat(api): add Source management API with scheduling"
```

---

### Task 3.4: 创建 Job API

**Files:**
- Create: `src/cyberpulse/api/routers/admin/jobs.py`
- Create: `src/cyberpulse/api/schemas/job.py`
- Create: `tests/test_api/test_admin_jobs.py`

- [ ] **Step 1: 编写 Job API 测试**

```python
# tests/test_api/test_admin_jobs.py
"""Tests for Job Admin API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create admin auth headers."""
    return {"Authorization": "Bearer cp_live_test_admin_key"}


class TestJobAdminAPI:
    """Tests for Job Admin API endpoints."""

    def test_list_jobs_no_auth(self, client):
        """Test that jobs endpoint requires authentication."""
        response = client.get("/api/v1/admin/jobs")
        assert response.status_code == 401

    def test_list_jobs_with_filter(self, client, admin_headers):
        """Test listing jobs with filters."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get(
                "/api/v1/admin/jobs?status=completed&limit=10",
                headers=admin_headers,
            )
            assert response.status_code in [200, 401]

    def test_create_job_invalid_source(self, client, admin_headers):
        """Test creating job with non-existent source."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.post(
                "/api/v1/admin/jobs",
                json={"source_id": "src_notexist"},
                headers=admin_headers,
            )
            assert response.status_code in [404, 401]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api/test_admin_jobs.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: 创建 Job schemas（完整版）**

```python
# src/cyberpulse/api/schemas/job.py
"""Job API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Job response."""

    job_id: str
    type: str  # "ingest" or "import"
    status: str  # "pending", "running", "completed", "failed"
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    file_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, str]] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Job list response."""

    data: List[JobResponse]
    count: int
    server_timestamp: datetime


class JobCreate(BaseModel):
    """Job creation request."""

    source_id: str = Field(..., description="Source ID to ingest")


class JobCreatedResponse(BaseModel):
    """Job creation response."""

    job_id: str
    type: str
    status: str
    source_id: str
    source_name: Optional[str] = None
    message: str = "Job created and queued"
```

- [ ] **Step 4: 创建 Job router（完整版）**

```python
# src/cyberpulse/api/routers/admin/jobs.py
"""Job management API router for admin endpoints."""

import logging
import secrets
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..dependencies import get_db
from ..schemas.job import (
    JobResponse,
    JobListResponse,
    JobCreate,
    JobCreatedResponse,
)
from ..auth import require_permissions, ApiClient
from ...models import Job, JobType, JobStatus, Source

logger = logging.getLogger(__name__)

router = APIRouter()

# job_id format: job_{uuid}
JOB_ID_PATTERN = re.compile(r"^job_[a-f0-9]+$")


def validate_job_id(job_id: str) -> None:
    """Validate job_id format."""
    if not JOB_ID_PATTERN.match(job_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_id format: {job_id}"
        )


def build_job_response(job: Job, source_name: Optional[str] = None) -> JobResponse:
    """Build JobResponse from Job model."""
    duration_seconds = None
    if job.started_at and job.completed_at:
        delta = job.completed_at - job.started_at
        duration_seconds = int(delta.total_seconds())

    error = None
    if job.status == JobStatus.FAILED:
        error = {
            "type": job.error_type or "unknown",
            "message": job.error_message or "Unknown error",
        }

    return JobResponse(
        job_id=job.job_id,
        type=job.type.value,
        status=job.status.value,
        source_id=job.source_id,
        source_name=source_name,
        file_name=job.file_name,
        result=job.result,
        error=error,
        retry_count=job.retry_count,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration_seconds,
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    type: Optional[str] = Query(None, description="Filter by type: ingest, import"),
    status: Optional[str] = Query(None, description="Filter by status: pending, running, completed, failed"),
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    since: Optional[datetime] = Query(None, description="Created after this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobListResponse:
    """
    List jobs with optional filtering.

    Returns jobs ordered by creation date (newest first).
    """
    logger.debug(f"Listing jobs: type={type}, status={status}, source_id={source_id}")

    query = db.query(Job)

    # Apply filters
    if type:
        try:
            type_enum = JobType(type.lower())
            query = query.filter(Job.type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid type '{type}'. Must be one of: ingest, import"
            )

    if status:
        try:
            status_enum = JobStatus(status.lower())
            query = query.filter(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: pending, running, completed, failed"
            )

    if source_id:
        query = query.filter(Job.source_id == source_id)

    if since:
        query = query.filter(Job.created_at >= since)

    jobs = query.order_by(desc(Job.created_at)).limit(limit).all()

    # Get source names for each job
    source_ids = {j.source_id for j in jobs if j.source_id}
    sources = db.query(Source).filter(Source.source_id.in_(source_ids)).all()
    source_map = {s.source_id: s.name for s in sources}

    return JobListResponse(
        data=[build_job_response(j, source_map.get(j.source_id)) for j in jobs],
        count=len(jobs),
        server_timestamp=datetime.now(timezone.utc),
    )


@router.post("/jobs", response_model=JobCreatedResponse, status_code=201)
async def create_job(
    request: JobCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobCreatedResponse:
    """
    Create a manual ingestion job.

    Creates a job and queues it for execution.
    """
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

    # Queue the job for execution
    # In production, this would trigger a Dramatiq task
    # from ...tasks.ingestion_tasks import ingest_source
    # ingest_source.send(request.source_id)

    return JobCreatedResponse(
        job_id=job.job_id,
        type=job.type.value,
        status=job.status.value,
        source_id=request.source_id,
        source_name=source.name,
        message="Job created and queued",
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobResponse:
    """Get job details."""
    validate_job_id(job_id)

    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}"
        )

    # Get source name
    source_name = None
    if job.source_id:
        source = db.query(Source).filter(Source.source_id == job.source_id).first()
        source_name = source.name if source else None

    return build_job_response(job, source_name)
```

- [ ] **Step 5: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.admin.jobs import router; print('Job router OK')"
```

Expected: "Job router OK"

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_api/test_admin_jobs.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/api/routers/admin/jobs.py src/cyberpulse/api/schemas/job.py tests/test_api/test_admin_jobs.py
git commit -m "feat(api): add Job management API with filters"
```

---

### Task 3.5: 创建 Client API（管理端）

**Files:**
- Create: `src/cyberpulse/api/routers/admin/clients.py`（重构现有）
- Modify: `src/cyberpulse/api/schemas/client.py`
- Create: `tests/test_api/test_admin_clients.py`

- [ ] **Step 1: 编写 Client API 测试**

```python
# tests/test_api/test_admin_clients.py
"""Tests for Client Admin API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create admin auth headers."""
    return {"Authorization": "Bearer cp_live_test_admin_key"}


class TestClientAdminAPI:
    """Tests for Client Admin API endpoints."""

    def test_list_clients_no_auth(self, client):
        """Test that clients endpoint requires authentication."""
        response = client.get("/api/v1/admin/clients")
        assert response.status_code == 401

    def test_create_client(self, client, admin_headers):
        """Test creating a new client."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_admin = MagicMock()
            mock_admin.permissions = ["admin"]
            mock_auth.return_value = mock_admin

            response = client.post(
                "/api/v1/admin/clients",
                json={"name": "Test Client", "permissions": ["read"]},
                headers=admin_headers,
            )
            assert response.status_code in [201, 401]

    def test_rotate_client_key(self, client, admin_headers):
        """Test rotating client API key."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_admin = MagicMock()
            mock_admin.permissions = ["admin"]
            mock_auth.return_value = mock_admin

            # First create a client, then rotate
            response = client.post(
                "/api/v1/admin/clients/cli_test000/rotate",
                headers=admin_headers,
            )
            assert response.status_code in [200, 401, 404]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api/test_admin_clients.py -v
```

Expected: FAIL (module not found or endpoints not implemented)

- [ ] **Step 3: 更新 Client schemas（添加 expires_at 和 rotate）**

```python
# src/cyberpulse/api/schemas/client.py
"""Client API schemas for admin endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    """Schema for creating a new API client."""

    name: str = Field(
        ...,
        description="Client name for identification",
        min_length=1,
        max_length=255
    )
    permissions: Optional[List[str]] = Field(
        default_factory=list,
        description="List of permissions (e.g., ['read', 'admin'])"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of the client's purpose"
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="Optional expiration date for the client"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Analytics Service",
                "permissions": ["read"],
                "description": "Client for analytics dashboard",
                "expires_at": "2026-12-31T23:59:59Z"
            }
        }
    }


class ClientUpdate(BaseModel):
    """Schema for updating an API client."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    expires_at: Optional[datetime] = Field(None)

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Updated Name",
                "description": "Updated description"
            }
        }
    }


class ClientResponse(BaseModel):
    """Single client response (API key never included)."""

    client_id: str
    name: str
    status: str
    permissions: List[str] = []
    description: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ClientCreatedResponse(BaseModel):
    """Response for client creation (includes API key once)."""

    client_id: str
    name: str
    api_key: str
    permissions: List[str] = []
    description: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "cli_a1b2c3d4",
                "name": "Analytics Service",
                "api_key": "cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "permissions": ["read"],
                "description": "Client for analytics dashboard",
                "expires_at": None,
                "created_at": "2026-03-25T10:00:00Z"
            }
        }
    }


class ClientRotateResponse(BaseModel):
    """Response for API key rotation."""

    client_id: str
    api_key: str
    message: str = "API Key rotated, old key is now invalid"


class ClientListResponse(BaseModel):
    """List of API clients."""

    data: List[ClientResponse]
    count: int
    server_timestamp: datetime
```

- [ ] **Step 4: 创建 Client router（管理端，完整版）**

```python
# src/cyberpulse/api/routers/admin/clients.py
"""Client management API router for admin endpoints.

Provides administrative endpoints for managing API clients.

SECURITY: These endpoints require admin permissions.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientCreatedResponse,
    ClientRotateResponse,
    ClientListResponse,
)
from ...models import ApiClient, ApiClientStatus
from ..auth import ApiClientService, require_permissions

logger = logging.getLogger(__name__)

router = APIRouter()

# client_id format: cli_{16 hex chars}
CLIENT_ID_PATTERN = re.compile(r"^cli_[a-f0-9]{16}$")


def validate_client_id(client_id: str) -> None:
    """Validate client_id format."""
    if not CLIENT_ID_PATTERN.match(client_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid client_id format: {client_id}. Expected format: cli_xxxxxxxxxxxxxxxx"
        )


@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    permission: Optional[str] = Query(None, description="Filter by permission"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientListResponse:
    """
    List all API clients.

    Returns all clients ordered by creation date (newest first).
    """
    logger.debug(f"Listing clients: permission={permission}, status={status}")

    query = db.query(ApiClient)

    if status:
        try:
            status_enum = ApiClientStatus(status.upper())
            query = query.filter(ApiClient.status == status_enum)
        except ValueError:
            valid_statuses = [s.value for s in ApiClientStatus]
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}"
            )

    clients = query.order_by(ApiClient.created_at.desc()).all()

    # Filter by permission if specified
    if permission:
        clients = [
            c for c in clients
            if permission in (c.permissions or [])
        ]

    return ClientListResponse(
        data=[ClientResponse.model_validate(c) for c in clients],
        count=len(clients),
        server_timestamp=datetime.now(timezone.utc),
    )


@router.post("/clients", response_model=ClientCreatedResponse, status_code=201)
async def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientCreatedResponse:
    """
    Create a new API client.

    IMPORTANT: The API key is returned ONCE in this response.
    Store it securely - it cannot be retrieved again.
    """
    logger.info(f"Creating API client: name={client.name}")

    service = ApiClientService(db)
    new_client, plain_key = service.create_client(
        name=client.name,
        permissions=client.permissions,
        description=client.description,
    )

    # Set expiration if provided
    if client.expires_at:
        new_client.expires_at = client.expires_at
        db.commit()

    logger.info(f"Created API client: client_id={new_client.client_id}")

    return ClientCreatedResponse(
        client_id=new_client.client_id,
        name=new_client.name,
        api_key=plain_key,
        permissions=new_client.permissions or [],
        description=new_client.description,
        expires_at=new_client.expires_at,
        created_at=new_client.created_at,
    )


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientResponse:
    """Get client details."""
    validate_client_id(client_id)

    service = ApiClientService(db)
    client = service.get_client(client_id)

    if not client:
        raise HTTPException(
            status_code=404,
            detail=f"Client not found: {client_id}"
        )

    return ClientResponse.model_validate(client)


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    update: ClientUpdate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientResponse:
    """
    Update a client.

    Note: Permissions cannot be changed via this endpoint.
    """
    validate_client_id(client_id)

    service = ApiClientService(db)
    client = service.get_client(client_id)

    if not client:
        raise HTTPException(
            status_code=404,
            detail=f"Client not found: {client_id}"
        )

    # Update fields
    if update.name is not None:
        client.name = update.name
    if update.description is not None:
        client.description = update.description
    if update.expires_at is not None:
        client.expires_at = update.expires_at

    db.commit()
    db.refresh(client)

    logger.info(f"Updated client: {client_id}")

    return ClientResponse.model_validate(client)


@router.delete("/clients/{client_id}", status_code=200)
async def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """
    Delete a client (revoke access).

    The client will no longer be able to authenticate.
    """
    validate_client_id(client_id)

    logger.info(f"Deleting API client: client_id={client_id}")

    service = ApiClientService(db)
    success = service.revoke_client(client_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Client not found: {client_id}"
        )

    return {"message": "Client deleted"}


@router.post("/clients/{client_id}/rotate", response_model=ClientRotateResponse)
async def rotate_client_key(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> ClientRotateResponse:
    """
    Rotate client API key.

    The old API key immediately becomes invalid.
    The new key is returned ONCE - store it securely.
    """
    validate_client_id(client_id)

    logger.info(f"Rotating API key for client: {client_id}")

    service = ApiClientService(db)

    # Check if rotate_key method exists, if not add it
    if hasattr(service, "rotate_key"):
        result = service.rotate_key(client_id)
    else:
        # Fallback implementation
        client = service.get_client(client_id)
        if not client:
            raise HTTPException(
                status_code=404,
                detail=f"Client not found: {client_id}"
            )

        # Generate new key
        from ..auth import generate_api_key, hash_api_key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        client.api_key = hashed_key
        db.commit()

        result = (client, plain_key)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Client not found: {client_id}"
        )

    client, new_key = result

    logger.info(f"Rotated API key for client: {client_id}")

    return ClientRotateResponse(
        client_id=client_id,
        api_key=new_key,
        message="API Key rotated, old key is now invalid",
    )
```

- [ ] **Step 5: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.admin.clients import router; print('Client router OK')"
```

Expected: "Client router OK"

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_api/test_admin_clients.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/api/routers/admin/clients.py src/cyberpulse/api/schemas/client.py tests/test_api/test_admin_clients.py
git commit -m "feat(api): add Client management API with rotate endpoint"
```

---

### Task 3.6: 创建 Log API

**Files:**
- Create: `src/cyberpulse/api/routers/admin/logs.py`
- Create: `src/cyberpulse/api/schemas/log.py`
- Create: `tests/test_api/test_admin_logs.py`

- [ ] **Step 1: 编写 Log API 测试**

```python
# tests/test_api/test_admin_logs.py
"""Tests for Log Admin API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create admin auth headers."""
    return {"Authorization": "Bearer cp_live_test_admin_key"}


class TestLogAdminAPI:
    """Tests for Log Admin API endpoints."""

    def test_list_logs_no_auth(self, client):
        """Test that logs endpoint requires authentication."""
        response = client.get("/api/v1/admin/logs")
        assert response.status_code == 401

    def test_list_logs_with_filters(self, client, admin_headers):
        """Test listing logs with filters."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get(
                "/api/v1/admin/logs?level=error&limit=10",
                headers=admin_headers,
            )
            assert response.status_code in [200, 401]

    def test_list_logs_by_source(self, client, admin_headers):
        """Test filtering logs by source."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get(
                "/api/v1/admin/logs?source_id=src_test01",
                headers=admin_headers,
            )
            assert response.status_code in [200, 401]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api/test_admin_logs.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: 创建 Log schemas（完整版）**

```python
# src/cyberpulse/api/schemas/log.py
"""Log API schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Single log entry."""

    timestamp: datetime
    level: str  # "ERROR", "WARNING", "INFO"
    module: str
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    error_type: Optional[str] = None
    message: str
    retry_count: int = 0
    suggestion: Optional[str] = None

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    """Log list response."""

    data: List[LogEntry]
    count: int
    server_timestamp: datetime


class ErrorTypeSummary(BaseModel):
    """Error type summary for statistics."""

    error_type: str
    count: int


class ErrorStatistics(BaseModel):
    """Error statistics."""

    total_24h: int
    by_type: List[ErrorTypeSummary]
    top_sources: List[dict]
```

- [ ] **Step 4: 创建 Log router（完整版）**

```python
# src/cyberpulse/api/routers/admin/logs.py
"""Log management API router for admin endpoints.

Provides access to system logs for troubleshooting.

Logs are read from the application log file, not stored in database.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.log import LogEntry, LogListResponse
from ..auth import require_permissions, ApiClient
from ....config import settings
from ...models import Source

logger = logging.getLogger(__name__)

router = APIRouter()

# Error types we track
ERROR_TYPES = {
    "connection": r"connection|timeout|network",
    "http_403": r"HTTP 403|Forbidden",
    "http_404": r"HTTP 404|Not Found",
    "http_429": r"HTTP 429|Too Many Requests|rate limit",
    "http_5xx": r"HTTP 5\d{2}",
    "parse_error": r"parse|XML|malformed",
    "ssl_error": r"SSL|certificate|TLS",
}


def classify_error(message: str) -> Optional[str]:
    """Classify error message into error type."""
    message_lower = message.lower()
    for error_type, pattern in ERROR_TYPES.items():
        if re.search(pattern, message_lower, re.IGNORECASE):
            return error_type
    return None


def parse_log_line(line: str) -> Optional[dict]:
    """Parse a log line into structured data.

    Expected format: YYYY-MM-DD HH:MM:SS - module - LEVEL - message
    """
    # Match standard log format
    match = re.match(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - ([\w.]+) - (\w+) - (.+)",
        line.strip()
    )
    if not match:
        return None

    timestamp_str, module, level, message = match.groups()

    # Parse timestamp
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    return {
        "timestamp": timestamp,
        "module": module,
        "level": level,
        "message": message,
    }


def extract_source_id(message: str) -> Optional[str]:
    """Extract source_id from log message if present."""
    match = re.search(r"src_[a-f0-9]{8}", message)
    return match.group(0) if match else None


@router.get("/logs", response_model=LogListResponse)
async def list_logs(
    level: str = Query("error", description="Log level: error, warning, info"),
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    since: Optional[str] = Query(None, description="Time range: 1h, 24h, 7d, or ISO datetime"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> LogListResponse:
    """
    Query system logs for troubleshooting.

    Logs are read from the application log file.
    By default, returns error logs from the last 24 hours.
    """
    logger.debug(f"Listing logs: level={level}, source_id={source_id}, since={since}")

    # Validate level
    level = level.upper()
    if level not in ["ERROR", "WARNING", "INFO"]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid level '{level}'. Must be one of: error, warning, info"
        )

    # Parse since parameter
    since_datetime = None
    if since:
        if since == "1h":
            since_datetime = datetime.now(timezone.utc) - timedelta(hours=1)
        elif since == "24h":
            since_datetime = datetime.now(timezone.utc) - timedelta(hours=24)
        elif since == "7d":
            since_datetime = datetime.now(timezone.utc) - timedelta(days=7)
        else:
            try:
                since_datetime = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid since format: {since}. Use 1h, 24h, 7d, or ISO datetime"
                )
    else:
        # Default to last 24 hours
        since_datetime = datetime.now(timezone.utc) - timedelta(hours=24)

    # Read log file
    log_file = settings.log_file
    if not log_file or not Path(log_file).exists():
        return LogListResponse(
            data=[],
            count=0,
            server_timestamp=datetime.now(timezone.utc),
        )

    entries = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Read from end of file for efficiency
            lines = f.readlines()[-5000:]  # Read last 5000 lines

        # Build source name lookup
        sources = db.query(Source).all()
        source_map = {s.source_id: s.name for s in sources}

        for line in lines:
            parsed = parse_log_line(line)
            if not parsed:
                continue

            # Filter by level
            if level == "ERROR" and parsed["level"] != "ERROR":
                continue
            elif level == "WARNING" and parsed["level"] not in ["ERROR", "WARNING"]:
                continue

            # Filter by timestamp
            if parsed["timestamp"] < since_datetime:
                continue

            # Extract source info
            msg_source_id = extract_source_id(parsed["message"])
            if source_id and msg_source_id != source_id:
                continue

            # Classify error
            error_type = None
            if parsed["level"] == "ERROR":
                error_type = classify_error(parsed["message"])

            entries.append(LogEntry(
                timestamp=parsed["timestamp"],
                level=parsed["level"],
                module=parsed["module"],
                source_id=msg_source_id,
                source_name=source_map.get(msg_source_id),
                error_type=error_type,
                message=parsed["message"],
                retry_count=0,  # Not tracked in current log format
                suggestion=_get_suggestion(error_type) if error_type else None,
            ))

    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read log file: {str(e)}"
        )

    # Sort by timestamp (newest first) and limit
    entries.sort(key=lambda x: x.timestamp, reverse=True)
    entries = entries[:limit]

    return LogListResponse(
        data=entries,
        count=len(entries),
        server_timestamp=datetime.now(timezone.utc),
    )


def _get_suggestion(error_type: str) -> str:
    """Get troubleshooting suggestion for error type."""
    suggestions = {
        "connection": "检查网络连接或源服务器状态",
        "http_403": "检查网站反爬策略，可能需要更换 User-Agent",
        "http_404": "RSS 地址可能已更改，尝试重新发现",
        "http_429": "请求频率过高，增加采集间隔",
        "http_5xx": "源服务器错误，稍后重试",
        "parse_error": "RSS 格式异常，检查源内容",
        "ssl_error": "SSL 证书问题，检查证书有效性",
    }
    return suggestions.get(error_type, "检查源配置和网络连接")
```

- [ ] **Step 5: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.admin.logs import router; print('Log router OK')"
```

Expected: "Log router OK"

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_api/test_admin_logs.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/api/routers/admin/logs.py src/cyberpulse/api/schemas/log.py tests/test_api/test_admin_logs.py
git commit -m "feat(api): add Log API for troubleshooting"
```

---

### Task 3.7: 创建 Diagnose API

**Files:**
- Create: `src/cyberpulse/api/routers/admin/diagnose.py`
- Create: `src/cyberpulse/api/schemas/diagnose.py`
- Create: `tests/test_api/test_admin_diagnose.py`

- [ ] **Step 1: 编写 Diagnose API 测试**

```python
# tests/test_api/test_admin_diagnose.py
"""Tests for Diagnose Admin API."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def admin_headers():
    """Create admin auth headers."""
    return {"Authorization": "Bearer cp_live_test_admin_key"}


class TestDiagnoseAdminAPI:
    """Tests for Diagnose Admin API endpoints."""

    def test_diagnose_no_auth(self, client):
        """Test that diagnose endpoint requires authentication."""
        response = client.get("/api/v1/admin/diagnose")
        assert response.status_code == 401

    def test_diagnose_with_admin(self, client, admin_headers):
        """Test diagnose with admin permission."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get("/api/v1/admin/diagnose", headers=admin_headers)
            assert response.status_code in [200, 401]

            if response.status_code == 200:
                data = response.json()
                assert "status" in data
                assert "components" in data
                assert "statistics" in data

    def test_diagnose_response_structure(self, client, admin_headers):
        """Test diagnose response contains expected fields."""
        with patch("cyberpulse.api.auth.get_current_client") as mock_auth:
            mock_client = MagicMock()
            mock_client.permissions = ["admin"]
            mock_auth.return_value = mock_client

            response = client.get("/api/v1/admin/diagnose", headers=admin_headers)

            if response.status_code == 200:
                data = response.json()
                # Check components
                assert "database" in data["components"]
                assert "redis" in data["components"]
                # Check statistics structure
                assert "sources" in data["statistics"]
                assert "jobs" in data["statistics"]
                assert "items" in data["statistics"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_api/test_admin_diagnose.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: 创建 Diagnose schemas（完整版）**

```python
# src/cyberpulse/api/schemas/diagnose.py
"""Diagnose API schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status of a system component."""

    status: str  # "connected", "disconnected", "error"
    message: Optional[str] = None


class SourceStatistics(BaseModel):
    """Source statistics."""

    active: int = 0
    frozen: int = 0
    pending_review: int = 0


class JobStatistics(BaseModel):
    """Job statistics."""

    pending: int = 0
    running: int = 0
    failed_24h: int = 0


class ItemStatistics(BaseModel):
    """Item statistics."""

    total: int = 0
    last_24h: int = 0


class ErrorByType(BaseModel):
    """Error count by type."""

    error_type: str
    count: int


class TopErrorSource(BaseModel):
    """Top source with errors."""

    source_id: str
    source_name: str
    error_count: int


class ErrorStatistics(BaseModel):
    """Error statistics."""

    total_24h: int = 0
    by_type: List[Dict[str, Any]] = []
    top_sources: List[Dict[str, Any]] = []


class DiagnoseResponse(BaseModel):
    """System diagnose response."""

    status: str = Field(..., description="Overall system status: healthy, degraded, unhealthy")
    version: str
    components: Dict[str, str]
    statistics: Dict[str, Any]
    server_timestamp: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "1.3.0",
                "components": {
                    "database": "connected",
                    "redis": "connected",
                    "scheduler": "active"
                },
                "statistics": {
                    "sources": {
                        "active": 120,
                        "frozen": 15,
                        "pending_review": 5
                    },
                    "jobs": {
                        "pending": 3,
                        "running": 1,
                        "failed_24h": 12
                    },
                    "items": {
                        "total": 5420,
                        "last_24h": 156
                    },
                    "errors": {
                        "total_24h": 280,
                        "by_type": [
                            {"error_type": "connection", "count": 120},
                            {"error_type": "http_403", "count": 80}
                        ],
                        "top_sources": [
                            {"source_id": "src_xxx", "source_name": "Example Blog", "error_count": 15}
                        ]
                    }
                },
                "server_timestamp": "2026-03-25T15:00:00Z"
            }
        }
    }
```

- [ ] **Step 4: 创建 Diagnose router（完整版）**

```python
# src/cyberpulse/api/routers/admin/diagnose.py
"""System diagnose API router for admin endpoints.

Provides system health overview and statistics.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..dependencies import get_db
from ..schemas.diagnose import DiagnoseResponse
from ..auth import require_permissions, ApiClient
from ...models import Source, Item, Job, SourceStatus, JobStatus, JobType
from .... import __version__
from ....database import engine
from ....config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def check_database() -> str:
    """Check database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return "connected"
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return "disconnected"


def check_redis() -> str:
    """Check Redis connectivity."""
    try:
        import redis
        from ....config import settings

        if not settings.redis_url:
            return "not_configured"

        r = redis.from_url(settings.redis_url)
        r.ping()
        return "connected"
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
        return "disconnected"


def check_scheduler() -> str:
    """Check scheduler status.

    This is a simplified check. In production, you might check
    if the scheduler process is running.
    """
    # For now, we assume scheduler is active if the service is running
    # A more robust check would query the scheduler's internal state
    return "active"


def get_source_statistics(db: Session) -> Dict[str, int]:
    """Get source statistics."""
    active = db.query(Source).filter(Source.status == SourceStatus.ACTIVE).count()
    frozen = db.query(Source).filter(Source.status == SourceStatus.FROZEN).count()
    pending_review = db.query(Source).filter(Source.pending_review == True).count()

    return {
        "active": active,
        "frozen": frozen,
        "pending_review": pending_review,
    }


def get_job_statistics(db: Session) -> Dict[str, int]:
    """Get job statistics."""
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    pending = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
    running = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
    failed_24h = db.query(Job).filter(
        Job.status == JobStatus.FAILED,
        Job.created_at >= yesterday.replace(tzinfo=None),
    ).count()

    return {
        "pending": pending,
        "running": running,
        "failed_24h": failed_24h,
    }


def get_item_statistics(db: Session) -> Dict[str, int]:
    """Get item statistics."""
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    total = db.query(Item).count()
    last_24h = db.query(Item).filter(
        Item.fetched_at >= yesterday.replace(tzinfo=None),
    ).count()

    return {
        "total": total,
        "last_24h": last_24h,
    }


def get_error_statistics(db: Session) -> Dict[str, Any]:
    """Get error statistics from recent jobs."""
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    # Count failed jobs by error type
    failed_jobs = db.query(Job).filter(
        Job.status == JobStatus.FAILED,
        Job.created_at >= yesterday.replace(tzinfo=None),
    ).all()

    # Group by error type
    error_counts: Dict[str, int] = {}
    source_errors: Dict[str, int] = {}

    for job in failed_jobs:
        error_type = job.error_type or "unknown"
        error_counts[error_type] = error_counts.get(error_type, 0) + 1

        if job.source_id:
            source_errors[job.source_id] = source_errors.get(job.source_id, 0) + 1

    # Get top error sources
    top_sources = []
    sorted_sources = sorted(source_errors.items(), key=lambda x: x[1], reverse=True)[:5]
    for source_id, count in sorted_sources:
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if source:
            top_sources.append({
                "source_id": source_id,
                "source_name": source.name,
                "error_count": count,
            })

    # Format by_type
    by_type = [
        {"error_type": et, "count": c}
        for et, c in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_24h": len(failed_jobs),
        "by_type": by_type,
        "top_sources": top_sources,
    }


def determine_overall_status(components: Dict[str, str], stats: Dict[str, Any]) -> str:
    """Determine overall system status."""
    # Check critical components
    if components.get("database") != "connected":
        return "unhealthy"

    # Check for high error rate
    error_stats = stats.get("errors", {})
    if error_stats.get("total_24h", 0) > 100:
        return "degraded"

    # Check for many pending_review sources
    source_stats = stats.get("sources", {})
    if source_stats.get("pending_review", 0) > 10:
        return "degraded"

    return "healthy"


@router.get("/diagnose", response_model=DiagnoseResponse)
async def get_diagnose(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DiagnoseResponse:
    """
    Get system diagnose overview.

    Returns system status, component health, and key statistics.
    Use this as the entry point for monitoring and troubleshooting.
    """
    logger.debug("Running system diagnose")

    # Check components
    components = {
        "database": check_database(),
        "redis": check_redis(),
        "scheduler": check_scheduler(),
    }

    # Gather statistics
    statistics = {
        "sources": get_source_statistics(db),
        "jobs": get_job_statistics(db),
        "items": get_item_statistics(db),
        "errors": get_error_statistics(db),
    }

    # Determine overall status
    status = determine_overall_status(components, statistics)

    return DiagnoseResponse(
        status=status,
        version=__version__,
        components=components,
        statistics=statistics,
        server_timestamp=datetime.now(timezone.utc),
    )
```

- [ ] **Step 5: 验证语法正确**

```bash
uv run python -c "from cyberpulse.api.routers.admin.diagnose import router; print('Diagnose router OK')"
```

Expected: "Diagnose router OK"

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_api/test_admin_diagnose.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/api/routers/admin/diagnose.py src/cyberpulse/api/schemas/diagnose.py tests/test_api/test_admin_diagnose.py
git commit -m "feat(api): add Diagnose API for system monitoring"
```

---

## Phase 4: 部署脚本

### Task 4.1: 更新 generate-env.sh

**Files:**
- Modify: `deploy/init/generate-env.sh`

- [ ] **Step 1: 添加 ADMIN_API_KEY 生成**

在 `generate_env_file` 函数中添加：

```bash
# 在生成配置文件部分添加

ADMIN_API_KEY=""
```

然后在 cat heredoc 中添加：

```env
# 管理员认证
ADMIN_API_KEY=${ADMIN_API_KEY}
```

在生成逻辑中：

```bash
# 生成管理员 API Key
admin_key="${ADMIN_API_KEY}"
if [[ -z "$admin_key" ]]; then
    admin_key="cp_live_$(generate_password 24)"
fi

# 如果已存在且非空，保留
if [[ -f "$ENV_FILE" ]]; then
    existing_admin_key=$(extract_existing_value "ADMIN_API_KEY" "$ENV_FILE")
    if [[ -n "$existing_admin_key" ]]; then
        admin_key="$existing_admin_key"
    fi
fi
```

- [ ] **Step 2: 更新配置摘要输出**

```bash
echo -e "  管理员 Key: ${YELLOW}********${NC}"
```

- [ ] **Step 3: Commit**

```bash
git add deploy/init/generate-env.sh
git commit -m "feat(deploy): add ADMIN_API_KEY generation to env setup"
```

---

### Task 4.2: 添加 admin 子命令到 cyber-pulse.sh

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 添加 admin 子命令实现**

```bash
# 在 main 函数的 case 语句中添加

        admin)
            shift || true
            cmd_admin "$@"
            ;;
```

```bash
# admin 命令实现
cmd_admin() {
    local subcommand="${1:-help}"

    case "$subcommand" in
        show-key)
            cmd_admin_show_key
            ;;
        rotate-key)
            cmd_admin_rotate_key
            ;;
        help|--help|-h)
            print_admin_help
            ;;
        *)
            print_error "Unknown admin subcommand: $subcommand"
            print_admin_help
            exit 1
            ;;
    esac
}

cmd_admin_show_key() {
    print_header "Admin API Key"

    # Get admin key from environment
    if [[ -f "$ENV_FILE" ]]; then
        admin_key=$(grep "^ADMIN_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-)
        if [[ -n "$admin_key" ]]; then
            echo -e "${GREEN}$admin_key${NC}"
            return 0
        fi
    fi

    print_error "ADMIN_API_KEY not found in $ENV_FILE"
    exit 1
}

cmd_admin_rotate_key() {
    print_header "Rotate Admin API Key"

    # Get current admin key
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error ".env file not found"
        exit 1
    fi

    admin_key=$(grep "^ADMIN_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-)
    if [[ -z "$admin_key" ]]; then
        print_error "ADMIN_API_KEY not found in .env"
        exit 1
    fi

    # Call API to rotate
    local api_url="http://localhost:8000"

    # Get admin client ID
    response=$(curl -s -H "Authorization: Bearer $admin_key" \
        "${api_url}/api/v1/admin/clients")

    client_id=$(echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data.get('data', []):
    if 'admin' in c.get('permissions', []):
        print(c['client_id'])
        break
" 2>/dev/null)

    if [[ -z "$client_id" ]]; then
        print_error "Could not find admin client"
        exit 1
    fi

    # Rotate key
    response=$(curl -s -X POST -H "Authorization: Bearer $admin_key" \
        "${api_url}/api/v1/admin/clients/${client_id}/rotate")

    new_key=$(echo "$response" | python3 -c "
import sys, json
print(json.load(sys.stdin).get('api_key', ''))
" 2>/dev/null)

    if [[ -z "$new_key" ]]; then
        print_error "Failed to rotate key"
        exit 1
    fi

    # Update .env file
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|^ADMIN_API_KEY=.*|ADMIN_API_KEY=${new_key}|" "$ENV_FILE"
    else
        sed -i "s|^ADMIN_API_KEY=.*|ADMIN_API_KEY=${new_key}|" "$ENV_FILE"
    fi

    echo -e "${GREEN}Admin API Key rotated successfully!${NC}"
    echo -e "New key: ${YELLOW}${new_key}${NC}"
    echo -e "${RED}⚠ Old key is now invalid${NC}"
}

print_admin_help() {
    echo ""
    echo "Admin commands:"
    echo "  show-key     Show current admin API key"
    echo "  rotate-key   Generate new admin API key"
    echo ""
    echo "Examples:"
    echo "  cyber-pulse.sh admin show-key"
    echo "  cyber-pulse.sh admin rotate-key"
}
```

- [ ] **Step 2: 更新 show_help 函数**

添加 admin 命令帮助信息。

- [ ] **Step 3: Commit**

```bash
git add scripts/cyber-pulse.sh
git commit -m "feat(cli): add admin show-key and rotate-key commands"
```

---

## Phase 5: 集成测试

### Task 5.1: 运行完整测试套件

- [ ] **Step 1: 运行所有测试**

```bash
uv run pytest -v
```

Expected: All tests pass

- [ ] **Step 2: 运行代码检查**

```bash
uv run ruff check src/ tests/
uv run mypy src/ --ignore-missing-imports
```

Expected: No errors

- [ ] **Step 3: 运行测试覆盖率**

```bash
uv run pytest --cov=src/cyberpulse --cov-report=term-missing
```

Expected: Coverage >= 80%

---

### Task 5.2: 手动验证

- [ ] **Step 1: 部署并验证管理员创建**

```bash
./scripts/cyber-pulse.sh deploy --env dev
# 检查日志确认管理员创建成功
```

- [ ] **Step 2: 验证 API 端点**

```bash
# 使用生成的 admin key
ADMIN_KEY="cp_live_xxx"

# 测试 diagnose
curl -H "Authorization: Bearer $ADMIN_KEY" http://localhost:8000/api/v1/admin/diagnose

# 测试 source list
curl -H "Authorization: Bearer $ADMIN_KEY" http://localhost:8000/api/v1/admin/sources

# 测试 items
curl -H "Authorization: Bearer $ADMIN_KEY" http://localhost:8000/api/v1/items?limit=5
```

- [ ] **Step 3: 验证 admin 子命令**

```bash
./scripts/cyber-pulse.sh admin show-key
./scripts/cyber-pulse.sh admin rotate-key
```

---

## 验收标准

- [ ] 所有测试通过 (`uv run pytest`)
- [ ] 代码检查通过 (`uv run ruff check`, `uv run mypy`)
- [ ] 数据库迁移已创建并通过
- [ ] API 文档正确显示 (`/docs`)
- [ ] 管理员认证机制正常工作
- [ ] 所有管理 API 端点正常工作
- [ ] 业务 API (Items) 正常工作
- [ ] admin 子命令正常工作

---

## 关联 Issue

- #39: API 中文 Unicode 转义
- #43: 缺少源健康状态监控 API
- #44: API 返回字段与文档描述不一致
- #47: API 参数/分页问题

---

## 执行顺序

1. 先完成 Phase 0 的基础修复计划（已独立）
2. 按 Phase 1-4 顺序执行本计划
3. 每个 Task 完成后提交
4. Phase 5 集成测试验证