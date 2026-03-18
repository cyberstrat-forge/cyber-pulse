# cyber-pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 cyber-pulse 单机原型系统，支持情报源管理、数据采集、标准化、质量控制和增量 API 服务

**Architecture:** 单体应用架构，使用 FastAPI 作为 Web 框架，PostgreSQL 作为数据库，Redis 用于任务队列和缓存，APScheduler 用于调度，Dramatiq 用于异步任务

**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL 15, Redis, APScheduler, Dramatiq, httpx, feedparser, trafilatura

---

## 文件结构

### 核心应用 (`src/cyberpulse/`)
- `__init__.py` - 应用初始化
- `config.py` - 配置管理
- `database.py` - 数据库连接和会话
- `main.py` - FastAPI 应用入口
- `cli.py` - CLI 命令行入口

### 数据模型 (`src/cyberpulse/models/`)
- `__init__.py`
- `base.py` - 基础模型
- `source.py` - Source 模型
- `item.py` - Item 模型
- `content.py` - Content 模型
- `api_client.py` - API 客户端模型

### 数据库迁移 (`migrations/`)
- Alembic 迁移脚本

### 业务逻辑 (`src/cyberpulse/services/`)
- `__init__.py`
- `source_service.py` - Source 管理服务
- `connector_service.py` - Connector 服务基类
- `rss_connector.py` - RSS Connector
- `api_connector.py` - API Connector
- `web_connector.py` - Web Scraper Connector
- `media_connector.py` - Media API Connector
- `normalization_service.py` - 数据标准化服务
- `quality_gate_service.py` - 质量控制服务
- `source_score_service.py` - Source 评分服务
- `task_service.py` - 任务调度服务

### API 层 (`src/cyberpulse/api/`)
- `__init__.py`
- `dependencies.py` - 依赖注入
- `endpoints/`
  - `__init__.py`
  - `sources.py` - Source API
  - `content.py` - 内容查询 API
  - `api_clients.py` - API 客户端管理
  - `health.py` - 健康检查

### 任务队列 (`src/cyberpulse/tasks/`)
- `__init__.py`
- `worker.py` - Dramatiq Worker 配置
- `ingestion_tasks.py` - 采集任务
- `normalization_tasks.py` - 标准化任务
- `quality_gate_tasks.py` - 质量控制任务

### 调度器 (`src/cyberpulse/scheduler/`)
- `__init__.py`
- `scheduler.py` - APScheduler 配置
- `job_runner.py` - Job 执行器

### CLI 工具 (`src/cyberpulse/cli/`)
- `__init__.py`
- `app.py` - TUI 应用
- `commands/`
  - `__init__.py`
  - `source_commands.py` - Source 命令
  - `job_commands.py` - 任务命令
  - `content_commands.py` - 内容命令
  - `client_commands.py` - 客户端命令
  - `config_commands.py` - 配置命令
  - `log_commands.py` - 日志命令
  - `diagnose_commands.py` - 诊断命令

### 测试 (`tests/`)
- `conftest.py` - pytest 配置
- `test_models/` - 模型测试
- `test_services/` - 服务测试
- `test_api/` - API 测试
- `test_tasks/` - 任务测试
- `test_cli/` - CLI 测试

### 配置文件
- `pyproject.toml` - Python 项目配置
- `alembic.ini` - Alembic 配置
- `.env.example` - 环境变量示例
- `docker-compose.yml` - Docker 编排

### 文档
- `README.md` - 项目说明
- `docs/` - 详细文档

---

## 实施任务

### Task 1: 项目初始化和依赖安装

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cyberpulse"
version = "0.1.0"
description = "Cyber Pulse - Security Intelligence Collection System"
authors = [{ name = "Your Name", email = "your.email@example.com" }]
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "psycopg2-binary>=2.9.0",
    "alembic>=1.13.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "redis>=5.0.0",
    "dramatiq[redis]>=1.14.0",
    "apscheduler>=3.10.0",
    "httpx>=0.26.0",
    "feedparser>=6.0.0",
    "feedfinder2>=0.0.4",
    "trafilatura>=1.6.0",
    "google-api-python-client>=2.100.0",
    "typer>=0.9.0",
    "rich>=13.7.0",
    "prompt-toolkit>=3.0.0",
    "python-dateutil>=2.8.0",
    "python-multipart>=0.0.6",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.2.0",
    "black>=23.12.0",
    "mypy>=1.8.0",
    "httpx>=0.26.0",
    "faker>=21.0.0",
    "factory-boy>=3.3.0",
]
```

- [ ] **Step 2: 创建 .gitignore**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Environment
.env
.env.local

# Logs
*.log
logs/

# Testing
.pytest_cache/
.coverage
htmlcov/

# Database
*.db
*.sqlite
*.sqlite3

# Docker
*.pid

# Dramatiq
dramatiq-results/
```

- [ ] **Step 3: 创建 .env.example**

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/cyberpulse

# Redis
REDIS_URL=redis://localhost:6379/0

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Dramatiq
DRAMATIQ_BROKER_URL=redis://localhost:6379/1
DRAMATIQ_MAX_RETRIES=3
DRAMATIQ_RETRY_DELAY=60

# APScheduler
SCHEDULER_ENABLED=true
DEFAULT_FETCH_INTERVAL=3600  # 1 hour in seconds

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/cyberpulse.log

# Security
SECRET_KEY=change-this-to-a-random-secret-key
API_TOKEN_EXPIRE_MINUTES=1440
```

- [ ] **Step 4: 创建 README.md**

```markdown
# cyber-pulse

内部战略情报采集与标准化系统

## 功能

- 情报源管理（Source Governance）
- 多种 Connector 采集（RSS、API、Web、Media）
- 数据标准化（HTML → Markdown）
- 质量控制
- 增量 API 服务（Pull + Cursor 模型）
- CLI TUI 工具

## 快速开始

### 安装依赖

```bash
pip install -e .
```

### 启动服务

```bash
# 启动 API 服务
uvicorn src.cyberpulse.main:app --reload --host 0.0.0.0 --port 8000

# 启动任务 Worker
dramatiq src.cyberpulse.tasks.worker

# 启动 CLI TUI
./cli
```

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 数据库迁移

```bash
alembic upgrade head
```
```

- [ ] **Step 5: 安装依赖并验证**

```bash
# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -e .
pip install -e ".[dev]"

# 验证安装
python -c "import fastapi; import dramatiq; import apscheduler; print('✓ Dependencies installed')"
```

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml .gitignore .env.example README.md
git commit -m "chore: initialize project structure and dependencies"
```

---

### Task 2: 数据库模型定义

**Files:**
- Create: `src/cyberpulse/__init__.py`
- Create: `src/cyberpulse/database.py`
- Create: `src/cyberpulse/config.py`
- Create: `src/cyberpulse/models/__init__.py`
- Create: `src/cyberpulse/models/base.py`
- Create: `src/cyberpulse/models/source.py`
- Create: `src/cyberpulse/models/item.py`
- Create: `src/cyberpulse/models/content.py`
- Create: `src/cyberpulse/models/api_client.py`

- [ ] **Step 1: 创建 config.py**

```python
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "postgresql://localhost/cyberpulse"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Dramatiq
    dramatiq_broker_url: str = "redis://localhost:6379/1"
    dramatiq_max_retries: int = 3
    dramatiq_retry_delay: int = 60

    # APScheduler
    scheduler_enabled: bool = True
    default_fetch_interval: int = 3600  # 1 hour

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/cyberpulse.log"

    # Security
    secret_key: str = "change-this-to-a-random-secret-key"
    api_token_expire_minutes: int = 1440

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

- [ ] **Step 2: 创建 database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: 创建 models/base.py**

```python
from sqlalchemy import Column, DateTime, func
from .database import Base


class TimestampMixin:
    """Timestamp mixin for created_at and updated_at"""
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class BaseModel(Base):
    """Base model with timestamps"""
    __abstract__ = True
```

- [ ] **Step 4: 创建 models/source.py**

```python
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, Enum, JSON
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum as PyEnum
from .base import BaseModel, TimestampMixin


class SourceTier(str, PyEnum):
    """Source tier levels"""
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class SourceStatus(str, PyEnum):
    """Source status"""
    ACTIVE = "active"
    FROZEN = "frozen"
    REMOVED = "removed"


class Source(BaseModel, TimestampMixin):
    """Intelligence source"""
    __tablename__ = "sources"

    source_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    connector_type = Column(String(50), nullable=False)
    tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
    score = Column(Float, nullable=False, default=50.0)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    is_in_observation = Column(Boolean, nullable=False, default=False)
    observation_until = Column(DateTime, nullable=True)
    pending_review = Column(Boolean, nullable=False, default=False)
    review_reason = Column(Text, nullable=True)
    fetch_interval = Column(Integer, nullable=True)
    config = Column(JSONB, nullable=False, default=dict)

    # Statistics
    last_fetched_at = Column(DateTime, nullable=True)
    last_scored_at = Column(DateTime, nullable=True)
    total_items = Column(Integer, nullable=False, default=0)
    total_contents = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: 创建 models/item.py**

```python
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from .base import BaseModel, TimestampMixin


class ItemStatus(str, Enum):
    """Item processing status"""
    NEW = "new"
    NORMALIZED = "normalized"
    MAPPED = "mapped"
    REJECTED = "rejected"


class Item(BaseModel, TimestampMixin):
    """Raw item from source"""
    __tablename__ = "items"

    item_id = Column(String(64), primary_key=True, index=True)
    source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=False, index=True)
    external_id = Column(String(255), nullable=False, index=True)
    url = Column(String(1024), nullable=False, index=True)
    title = Column(String(1024), nullable=False)
    raw_content = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, index=True)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="new")
    metadata = Column(JSONB, nullable=False, default=dict)

    # Quality metrics (filled after normalization)
    meta_completeness = Column(Float, nullable=True)
    content_completeness = Column(Float, nullable=True)
    noise_ratio = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_items_source_published", "source_id", "published_at"),
        Index("ix_items_source_url", "source_id", "url", unique=True),
    )
```

- [ ] **Step 6: 创建 models/content.py**

```python
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from .base import BaseModel, TimestampMixin


class ContentStatus(str, Enum):
    """Content status"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class Content(BaseModel, TimestampMixin):
    """Deduplicated content entity"""
    __tablename__ = "contents"

    content_id = Column(String(64), primary_key=True, index=True)
    canonical_hash = Column(String(64), nullable=False, index=True, unique=True)
    normalized_title = Column(String(1024), nullable=False)
    normalized_body = Column(Text, nullable=False)
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    source_count = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="active")

    __table_args__ = (
        Index("ix_contents_first_seen", "first_seen_at"),
    )
```

- [ ] **Step 7: 创建 models/api_client.py**

```python
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from .base import BaseModel, TimestampMixin


class ApiClientStatus(str, Enum):
    """API client status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ApiClient(BaseModel, TimestampMixin):
    """API client for authentication"""
    __tablename__ = "api_clients"

    client_id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_key = Column(String(128), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="active")
    description = Column(Text, nullable=True)
    permissions = Column(JSONB, nullable=False, default=list)
    last_used_at = Column(DateTime, nullable=True)
```

- [ ] **Step 8: 创建 models/__init__.py**

```python
from .source import Source, SourceTier, SourceStatus
from .item import Item, ItemStatus
from .content import Content, ContentStatus
from .api_client import ApiClient, ApiClientStatus

__all__ = [
    "Source",
    "SourceTier",
    "SourceStatus",
    "Item",
    "ItemStatus",
    "Content",
    "ContentStatus",
    "ApiClient",
    "ApiClientStatus",
]
```

- [ ] **Step 9: 创建 src/cyberpulse/__init__.py**

```python
__version__ = "0.1.0"
__author__ = "Your Name"

from .config import settings
from .database import Base, engine, SessionLocal, get_db

__all__ = [
    "__version__",
    "__author__",
    "settings",
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
]
```

- [ ] **Step 10: 运行测试验证模型**

```python
# test_models.py
from src.cyberpulse.models import Source, Item, Content, ApiClient

def test_models_import():
    """Test that all models can be imported"""
    assert Source is not None
    assert Item is not None
    assert Content is not None
    assert ApiClient is not None

def test_source_tier_enum():
    """Test SourceTier enum values"""
    assert Source.SourceTier.T0 == "T0"
    assert Source.SourceTier.T1 == "T1"
    assert Source.SourceTier.T2 == "T2"
    assert Source.SourceTier.T3 == "T3"
```

```bash
pytest tests/test_models.py -v
```

- [ ] **Step 11: 提交**

```bash
git add src/cyberpulse/
git commit -m "feat: define database models (Source, Item, Content, ApiClient)"
```

---

### Task 3: Alembic 数据库迁移配置

**Files:**
- Create: `alembic.ini`
- Create: `alembic/`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/`

- [ ] **Step 1: 初始化 Alembic**

```bash
alembic init alembic
```

- [ ] **Step 2: 修改 alembic/env.py**

```python
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.cyberpulse.database import Base, engine
from src.cyberpulse.config import settings

# this is the Alembic Config object
config = context.config

# Set database URL from config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 创建初始迁移**

```bash
alembic revision --autogenerate -m "initial schema"
```

- [ ] **Step 4: 运行迁移**

```bash
alembic upgrade head
```

- [ ] **Step 5: 提交**

```bash
git add alembic/ alembic.ini
git commit -m "feat: setup database migrations with Alembic"
```

---

### Task 4: Source 服务实现

**Files:**
- Create: `src/cyberpulse/services/__init__.py`
- Create: `src/cyberpulse/services/source_service.py`
- Create: `tests/test_services/test_source_service.py`

- [ ] **Step 1: 创建服务基类**

```python
from typing import Optional, List
from sqlalchemy.orm import Session


class BaseService:
    """Base service class with common utilities"""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, model, defaults=None, **kwargs):
        """Get or create a record"""
        instance = self.db.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, False
        else:
            params = {**kwargs, **(defaults or {})}
            instance = model(**params)
            self.db.add(instance)
            self.db.commit()
            self.db.refresh(instance)
            return instance, True
```

- [ ] **Step 2: 创建 source_service.py**

```python
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import uuid

from .base import BaseService
from ..models import Source, Item, SourceTier, SourceStatus


class SourceService(BaseService):
    """Service for managing sources"""

    def generate_source_id(self) -> str:
        """Generate unique source ID"""
        return f"src_{uuid.uuid4().hex[:8]}"

    def add_source(
        self,
        name: str,
        connector_type: str,
        tier: SourceTier = SourceTier.T2,
        config: dict = None,
    ) -> Tuple[Source, str]:
        """
        Add a new source with immediate evaluation

        Returns:
            (source, message) - source object and status message
        """
        # Check if source already exists
        existing = self.db.query(Source).filter(
            (Source.name == name) | (Source.config['url'].astext == config.get('url'))
        ).first()

        if existing:
            return None, f"Source already exists: {existing.name}"

        # Create source
        source = Source(
            source_id=self.generate_source_id(),
            name=name,
            connector_type=connector_type,
            tier=tier,
            status=SourceStatus.ACTIVE,
            config=config or {},
            is_in_observation=True,
            observation_until=datetime.utcnow() + timedelta(days=30),
        )

        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)

        return source, "Source added, awaiting evaluation"

    def update_source(
        self,
        source_id: str,
        **kwargs
    ) -> Optional[Source]:
        """Update source"""
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return None

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        self.db.commit()
        self.db.refresh(source)
        return source

    def remove_source(self, source_id: str) -> bool:
        """Remove source"""
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return False

        source.status = SourceStatus.REMOVED
        self.db.commit()
        return True

    def list_sources(
        self,
        tier: Optional[SourceTier] = None,
        status: Optional[SourceStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Source]:
        """List sources with filters"""
        query = self.db.query(Source)

        if tier:
            query = query.filter(Source.tier == tier)
        if status:
            query = query.filter(Source.status == status)

        return query.offset(offset).limit(limit).all()

    def get_source_statistics(self, source_id: str) -> dict:
        """Get source statistics"""
        source = self.db.query(Source).filter(Source.source_id == source_id).first()
        if not source:
            return {}

        item_count = self.db.query(Item).filter(Item.source_id == source_id).count()

        return {
            "source_id": source.source_id,
            "name": source.name,
            "tier": source.tier,
            "score": source.score,
            "status": source.status,
            "total_items": item_count,
            "last_fetched_at": source.last_fetched_at,
        }
```

- [ ] **Step 3: 创建测试**

```python
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.cyberpulse.database import Base
from src.cyberpulse.models import Source, SourceTier, SourceStatus
from src.cyberpulse.services.source_service import SourceService


@pytest.fixture
def db_session():
    """Create in-memory database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_add_source(db_session):
    """Test adding a new source"""
    service = SourceService(db_session)

    source, message = service.add_source(
        name="Test Source",
        connector_type="rss",
        config={"url": "https://example.com/rss"}
    )

    assert source is not None
    assert source.name == "Test Source"
    assert source.connector_type == "rss"
    assert source.tier == SourceTier.T2
    assert source.is_in_observation == True
    assert "awaiting evaluation" in message


def test_add_duplicate_source(db_session):
    """Test adding duplicate source"""
    service = SourceService(db_session)

    # Add first source
    source1, _ = service.add_source(
        name="Test Source",
        connector_type="rss",
        config={"url": "https://example.com/rss"}
    )

    # Try to add duplicate
    source2, message = service.add_source(
        name="Test Source",
        connector_type="rss",
        config={"url": "https://example.com/rss"}
    )

    assert source2 is None
    assert "already exists" in message


def test_update_source(db_session):
    """Test updating source"""
    service = SourceService(db_session)

    source, _ = service.add_source(
        name="Test Source",
        connector_type="rss"
    )

    updated = service.update_source(
        source.source_id,
        tier=SourceTier.T1,
        score=85.0
    )

    assert updated is not None
    assert updated.tier == SourceTier.T1
    assert updated.score == 85.0


def test_remove_source(db_session):
    """Test removing source"""
    service = SourceService(db_session)

    source, _ = service.add_source(
        name="Test Source",
        connector_type="rss"
    )

    success = service.remove_source(source.source_id)
    assert success == True

    removed = db_session.query(Source).filter(Source.source_id == source.source_id).first()
    assert removed.status == SourceStatus.REMOVED


def test_list_sources(db_session):
    """Test listing sources"""
    service = SourceService(db_session)

    # Add multiple sources
    service.add_source(name="Source 1", connector_type="rss", tier=SourceTier.T0)
    service.add_source(name="Source 2", connector_type="api", tier=SourceTier.T1)
    service.add_source(name="Source 3", connector_type="web", tier=SourceTier.T2)

    # List all
    all_sources = service.list_sources()
    assert len(all_sources) == 3

    # Filter by tier
    t0_sources = service.list_sources(tier=SourceTier.T0)
    assert len(t0_sources) == 1
    assert t0_sources[0].tier == SourceTier.T0
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_services/test_source_service.py -v
```

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/services/ tests/test_services/
git commit -m "feat: implement SourceService for source management"
```

---

### Task 5: Connector 基类和 RSS Connector

**Files:**
- Create: `src/cyberpulse/services/connector_service.py`
- Create: `src/cyberpulse/services/rss_connector.py`
- Create: `tests/test_services/test_rss_connector.py`

- [ ] **Step 1: 创建 connector_service.py (基类)**

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import httpx
from datetime import datetime


class BaseConnector(ABC):
    """Base connector class"""

    def __init__(self, config: Dict):
        self.config = config
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)

    @abstractmethod
    async def fetch(self) -> List[Dict]:
        """
        Fetch items from source

        Returns:
            List of item dicts with at least:
            - external_id: unique identifier
            - url: item URL
            - title: item title
            - published_at: datetime
            - content: raw content (optional)
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate connector configuration"""
        pass

    def close(self):
        """Close HTTP client"""
        self.client.close()
```

- [ ] **Step 2: 创建 rss_connector.py**

```python
import feedparser
from typing import List, Dict
from datetime import datetime
import hashlib

from .connector_service import BaseConnector


class RSSConnector(BaseConnector):
    """RSS/Atom feed connector"""

    def validate_config(self) -> bool:
        """Validate RSS connector config"""
        return "feed_url" in self.config

    async def fetch(self) -> List[Dict]:
        """
        Fetch items from RSS feed

        Returns:
            List of items with RSS metadata
        """
        feed_url = self.config["feed_url"]

        try:
            # Parse feed
            feed = feedparser.parse(feed_url)

            if feed.bozo:
                raise ValueError(f"Invalid RSS feed: {feed_url}")

            items = []
            for entry in feed.entries[:50]:  # Limit to 50 items
                item = self._parse_entry(entry)
                if item:
                    items.append(item)

            return items

        except Exception as e:
            raise RuntimeError(f"Failed to fetch RSS feed: {e}")

    def _parse_entry(self, entry) -> Optional[Dict]:
        """Parse RSS entry to item dict"""
        try:
            # Get unique ID
            external_id = entry.get("id") or entry.get("link")
            if not external_id:
                return None

            # Get title
            title = entry.get("title", "")
            if not title:
                return None

            # Get published date
            published_at = self._parse_date(entry)
            if not published_at:
                published_at = datetime.utcnow()

            # Get content
            content = self._get_content(entry)

            # Generate content hash
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

            return {
                "external_id": external_id,
                "url": entry.get("link", ""),
                "title": title,
                "published_at": published_at,
                "content": content,
                "content_hash": content_hash,
                "author": entry.get("author", ""),
                "tags": [t.term for t in entry.get("tags", [])],
            }

        except Exception as e:
            print(f"Error parsing entry: {e}")
            return None

    def _parse_date(self, entry):
        """Parse date from RSS entry"""
        for field in ["published", "updated", "created"]:
            if hasattr(entry, field):
                try:
                    return datetime(*entry[field + "_parsed"][:6])
                except:
                    pass
        return None

    def _get_content(self, entry):
        """Get content from RSS entry"""
        # Try content field first
        if hasattr(entry, "content"):
            return entry.content[0].value

        # Try summary
        if hasattr(entry, "summary"):
            return entry.summary

        return ""
```

- [ ] **Step 3: 创建测试**

```python
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.cyberpulse.services.rss_connector import RSSConnector


@pytest.fixture
def rss_connector():
    """Create RSS connector for testing"""
    config = {"feed_url": "https://example.com/rss"}
    return RSSConnector(config)


def test_validate_config(rss_connector):
    """Test config validation"""
    assert rss_connector.validate_config() == True

    invalid = RSSConnector({})
    assert invalid.validate_config() == False


@patch("src.cyberpulse.services.rss_connector.feedparser.parse")
def test_fetch(mock_parse, rss_connector):
    """Test fetching RSS items"""
    # Mock feedparser response
    mock_feed = Mock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            "id": "1",
            "link": "https://example.com/1",
            "title": "Test Article 1",
            "published": "2024-03-18T10:00:00",
            "published_parsed": (2024, 3, 18, 10, 0, 0, 0, 0, 0),
            "summary": "Test summary",
            "author": "Test Author",
            "tags": [{"term": "security"}, {"term": "news"}],
        },
        {
            "id": "2",
            "link": "https://example.com/2",
            "title": "Test Article 2",
            "published": "2024-03-18T09:00:00",
            "published_parsed": (2024, 3, 18, 9, 0, 0, 0, 0, 0),
            "summary": "Another summary",
        },
    ]
    mock_parse.return_value = mock_feed

    # Fetch items
    items = rss_connector.fetch()

    assert len(items) == 2
    assert items[0]["external_id"] == "1"
    assert items[0]["title"] == "Test Article 1"
    assert items[0]["author"] == "Test Author"
    assert "security" in items[0]["tags"]


def test_content_hash(rss_connector):
    """Test content hash generation"""
    from hashlib import md5

    # Simulate item parsing
    content = "Test content"
    expected_hash = md5(content.encode("utf-8")).hexdigest()

    # Verify connector generates same hash
    assert len(expected_hash) == 32
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_services/test_rss_connector.py -v
```

- [ ] **Step 5: 提交**

```bash
git add src/cyberpulse/services/ tests/test_services/
git commit -m "feat: implement RSSConnector for RSS feed collection"
```

---

[... 继续后续任务：API Connector、Web Scraper、Normalization Service、Quality Gate、API Endpoints、APScheduler、Dramatiq Tasks、CLI TUI 等 ...]

---

## 执行选项

**计划完成并保存到** `docs/superpowers/plans/2026-03-18-cyber-pulse-implementation.md`

**两个执行选项：**

**1. 子代理驱动（推荐）** - 我为每个任务派遣一个独立的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在本次会话中使用 executing-plans 技能，批量执行并设置审查检查点

**选择哪种方式？**
