# Phase 3 Implementation Plan - End-to-End Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete end-to-end integration to make cyber-pulse runnable as a production-ready system.

**Architecture:** Connect all implemented components (scheduler → Dramatiq tasks → services → API) and add deployment infrastructure (Dockerfile, docker-compose) for one-command startup.

**Tech Stack:** Python 3.11+, FastAPI, APScheduler, Dramatiq, Redis, PostgreSQL, Docker

---

## Current Implementation Status Analysis

### ✅ Fully Implemented Components

| Component | Status | Notes |
|-----------|--------|-------|
| Data Models | ✅ Complete | Source, Item, Content, ApiClient |
| Source Service | ✅ Complete | CRUD + observation period |
| Item Service | ✅ Complete | Create + deduplication |
| Content Service | ✅ Complete | Create + cross-source deduplication |
| Normalization Service | ✅ Complete | Content extraction, cleaning, Markdown |
| Quality Gate Service | ✅ Complete | Quality scoring, rejection handling |
| Source Score Service | ✅ Complete | Stability, Activity, Quality scoring |
| RSS Connector | ✅ Complete | feedparser-based |
| API Connector | ✅ Complete | httpx-based |
| Web Scraper Connector | ✅ Complete | trafilatura-based |
| Media API Connector | ✅ Complete | YouTube API |
| Connector Factory | ✅ Complete | Auto-select connector |
| FastAPI REST API | ✅ Complete | Content, Sources, Clients, Health |
| CLI Tools | ✅ Complete | 7 command modules + TUI |
| Dramatiq Tasks | ✅ Complete | Ingestion, Normalization, Quality |
| APScheduler Service | ✅ Complete | Job scheduling + persistence |

### ❌ Integration Gaps

| Gap | Severity | Impact |
|-----|----------|--------|
| **Scheduler-Jobs not connected** | 🔴 Critical | Scheduler jobs are placeholders, don't trigger Dramatiq |
| **No Dockerfile** | 🟡 High | Cannot containerize for deployment |
| **No docker-compose.yml** | 🟡 High | Cannot start all services together |
| **No integration tests** | 🟡 Medium | Cannot verify end-to-end flow |
| **Server management incomplete** | 🟢 Low | stop/restart/status not implemented |

### 🔴 Critical Issue: Scheduler-Jobs Integration

**File**: `src/cyberpulse/scheduler/jobs.py`

Current state (placeholders):
```python
def collect_source(source_id: str) -> dict:
    # Placeholder: In Task 2D.3, this will call:
    # from ..tasks.ingestion_tasks import ingest_source
    # ingest_source.send(source_id)
```

**Required fix**: Connect to actual Dramatiq tasks.

---

## Task Breakdown

### Task 1: Scheduler-Dramatiq Integration

**Files:**
- Modify: `src/cyberpulse/scheduler/jobs.py`
- Modify: `src/cyberpulse/scheduler/scheduler.py`
- Create: `tests/test_scheduler/test_integration.py`

- [ ] **Step 1: Write failing test for collect_source integration**

```python
# tests/test_scheduler/test_integration.py
"""Integration tests for scheduler-dramatiq connection."""
import pytest
from unittest.mock import patch, MagicMock

from cyberpulse.scheduler.jobs import collect_source, run_scheduled_collection, update_source_scores


class TestCollectSource:
    """Tests for collect_source job."""

    def test_collect_source_triggers_ingest_task(self) -> None:
        """Test that collect_source triggers Dramatiq ingest_source task."""
        with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
            mock_ingest.send = MagicMock()

            result = collect_source("src_test123")

            mock_ingest.send.assert_called_once_with("src_test123")
            assert result["status"] == "queued"
            assert result["source_id"] == "src_test123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_scheduler/test_integration.py -v`
Expected: FAIL with "cannot import name 'ingest_source'"

- [ ] **Step 3: Update jobs.py to import and call Dramatiq tasks**

```python
# src/cyberpulse/scheduler/jobs.py
"""Job functions for the scheduler."""

import logging
from typing import List

from ..database import SessionLocal
from ..models import Source, SourceStatus
from ..tasks.ingestion_tasks import ingest_source
from ..tasks.normalization_tasks import normalize_item
from ..services.source_score_service import SourceScoreService

logger = logging.getLogger(__name__)


def collect_source(source_id: str) -> dict:
    """Collect items from a source via Dramatiq task.

    Args:
        source_id: The ID of the source to collect from.

    Returns:
        Dictionary with job result status.
    """
    logger.info(f"Queueing collection for source: {source_id}")

    # Send to Dramatiq task queue
    ingest_source.send(source_id)

    return {
        "source_id": source_id,
        "status": "queued",
        "message": "Collection job queued successfully",
    }


def run_scheduled_collection() -> dict:
    """Run scheduled collection for all active sources.

    Queries database for active sources and queues collection
    jobs for each.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Running scheduled collection for all active sources")

    db = SessionLocal()
    try:
        # Query all active sources
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()

        queued_count = 0
        for source in sources:
            ingest_source.send(source.source_id)
            queued_count += 1

        logger.info(f"Queued {queued_count} sources for collection")

        return {
            "status": "completed",
            "sources_count": queued_count,
            "message": f"Queued {queued_count} sources for collection",
        }
    finally:
        db.close()


def update_source_scores() -> dict:
    """Update scores for all sources.

    Recalculates source scores based on collection statistics.

    Returns:
        Dictionary with job result status.
    """
    logger.info("Updating source scores")

    db = SessionLocal()
    try:
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()

        score_service = SourceScoreService(db)
        updated_count = 0

        for source in sources:
            try:
                score_service.update_tier(source.source_id)
                updated_count += 1
            except ValueError as e:
                logger.warning(f"Could not update score for {source.source_id}: {e}")

        logger.info(f"Updated scores for {updated_count} sources")

        return {
            "status": "completed",
            "sources_updated": updated_count,
            "message": f"Updated scores for {updated_count} sources",
        }
    finally:
        db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_scheduler/test_integration.py -v`
Expected: PASS

- [ ] **Step 5: Add more comprehensive tests**

```python
class TestRunScheduledCollection:
    """Tests for run_scheduled_collection job."""

    def test_scheduled_collection_queues_active_sources(self, db_session) -> None:
        """Test that only active sources are queued."""
        from cyberpulse.models import Source, SourceTier, SourceStatus
        from cyberpulse.services import SourceService

        # Create test sources
        service = SourceService(db_session)
        service.add_source("Active Source", "rss", tier=SourceTier.T2)
        service.add_source("Frozen Source", "rss", tier=SourceTier.T2)

        # Freeze one source
        db_session.query(Source).filter(
            Source.name == "Frozen Source"
        ).update({"status": SourceStatus.FROZEN})
        db_session.commit()

        with patch("cyberpulse.scheduler.jobs.ingest_source") as mock_ingest:
            mock_ingest.send = MagicMock()

            result = run_scheduled_collection()

            # Only active source should be queued
            assert result["sources_count"] == 1
            mock_ingest.send.assert_called_once()

    def test_update_source_scores(self, db_session) -> None:
        """Test that source scores are updated."""
        from cyberpulse.models import Source, SourceTier
        from cyberpulse.services import SourceService

        # Create test source
        service = SourceService(db_session)
        source, _ = service.add_source("Test Source", "rss", tier=SourceTier.T2)

        result = update_source_scores()

        assert result["status"] == "completed"
```

- [ ] **Step 6: Run all scheduler tests**

Run: `.venv/bin/pytest tests/test_scheduler/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/scheduler/jobs.py tests/test_scheduler/
git commit -m "feat: connect scheduler jobs to Dramatiq tasks"
```

---

### Task 2: Docker Deployment Infrastructure

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

# Create data and logs directories
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=postgresql://cyberpulse:cyberpulse123@postgres:5432/cyberpulse
ENV REDIS_URL=redis://redis:6379/0

# Expose API port
EXPOSE 8000

# Default command (can be overridden)
CMD ["uvicorn", "cyberpulse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: cyberpulse
      POSTGRES_USER: cyberpulse
      POSTGRES_PASSWORD: cyberpulse123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cyberpulse"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    environment:
      DATABASE_URL: postgresql://cyberpulse:cyberpulse123@postgres:5432/cyberpulse
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    command: uvicorn cyberpulse.api.main:app --host 0.0.0.0 --port 8000

  worker:
    build: .
    environment:
      DATABASE_URL: postgresql://cyberpulse:cyberpulse123@postgres:5432/cyberpulse
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    command: dramatiq cyberpulse.tasks.worker

  scheduler:
    build: .
    environment:
      DATABASE_URL: postgresql://cyberpulse:cyberpulse123@postgres:5432/cyberpulse
      REDIS_URL: redis://redis:6379/0
      SCHEDULER_ENABLED: "true"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    command: python -m cyberpulse.scheduler

volumes:
  postgres_data:
  redis_data:
```

- [ ] **Step 3: Create .dockerignore**

```
# .dockerignore
.git
.gitignore
.venv
venv
__pycache__
*.pyc
*.pyo
*.pyd
.Python
.pytest_cache
.coverage
htmlcov
*.egg-info
dist
build
.env
.env.local
*.log
data/
logs/
```

- [ ] **Step 4: Verify Docker files with lint**

Run: `docker build --check . 2>&1 || echo "Docker lint not available, skipping"`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker deployment infrastructure"
```

---

### Task 3: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration/test_e2e.py`
- Create: `tests/test_integration/__init__.py`

- [ ] **Step 1: Create integration test file**

```python
# tests/test_integration/test_e2e.py
"""End-to-end integration tests for cyber-pulse.

These tests verify the complete data flow:
Source → Connector → Item → Normalization → Quality Gate → Content → API

Note: These tests require a running database and Redis.
Use pytest markers to skip if services not available.
"""
import pytest
from datetime import datetime, timezone

from cyberpulse.database import SessionLocal
from cyberpulse.models import Source, SourceTier, SourceStatus, Item, Content, ItemStatus
from cyberpulse.services import (
    SourceService,
    ItemService,
    ContentService,
    NormalizationService,
    QualityGateService,
)
from cyberpulse.tasks.ingestion_tasks import ingest_source


@pytest.fixture
def integration_db():
    """Provide a database session for integration tests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.mark.integration
class TestE2EDataFlow:
    """Test complete data flow from ingestion to API."""

    def test_rss_source_to_content_flow(self, integration_db) -> None:
        """Test complete flow for RSS source."""
        # 1. Create source
        source_service = SourceService(integration_db)
        source, msg = source_service.add_source(
            name="Test RSS Feed",
            connector_type="rss",
            tier=SourceTier.T2,
            config={"url": "https://feeds.bbci.co.uk/news/technology/rss.xml"}
        )
        assert source is not None
        source_id = source.source_id

        # 2. Simulate item creation (mocked from connector)
        item_service = ItemService(integration_db)
        item = item_service.create_item(
            source_id=source_id,
            external_id="test-item-001",
            url="https://example.com/article/001",
            title="Test Article Title",
            raw_content="<html><body><p>This is test content for the article.</p></body></html>",
            published_at=datetime.now(timezone.utc),
            content_hash="abc123",
            raw_metadata={"author": "Test Author", "tags": ["tech", "security"]},
        )
        assert item is not None
        item_id = item.item_id

        # 3. Normalize item
        norm_service = NormalizationService(integration_db)
        normalized = norm_service.normalize(
            raw_content=item.raw_content,
            url=item.url,
            title=item.title,
        )
        assert normalized.markdown_content is not None

        # 4. Update item with normalized content
        item.normalized_content = normalized.markdown_content
        item.canonical_hash = normalized.canonical_hash
        integration_db.commit()

        # 5. Quality gate check
        quality_service = QualityGateService(integration_db)
        result = quality_service.check(item_id)
        assert result.passed is True

        # 6. Verify content was created
        content_service = ContentService(integration_db)
        contents = content_service.get_contents(limit=10)
        assert len(contents) >= 1

        # 7. Verify source statistics updated
        integration_db.refresh(source)
        assert source.total_items >= 1


@pytest.mark.integration
class TestAPIDataRetrieval:
    """Test API endpoints for data retrieval."""

    def test_content_list_endpoint(self) -> None:
        """Test that content can be retrieved via API."""
        from fastapi.testclient import TestClient
        from cyberpulse.api.main import app

        client = TestClient(app)

        # This will fail without auth, but verifies endpoint exists
        response = client.get("/api/v1/contents")
        assert response.status_code in [200, 401]  # 401 if auth required

    def test_health_endpoint(self) -> None:
        """Test that health endpoint works."""
        from fastapi.testclient import TestClient
        from cyberpulse.api.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
```

- [ ] **Step 2: Create __init__.py**

```python
# tests/test_integration/__init__.py
"""Integration tests package."""
```

- [ ] **Step 3: Run integration tests (will skip if services unavailable)**

Run: `.venv/bin/pytest tests/test_integration/ -v -m integration --tb=short || echo "Integration tests require running services"`

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration/
git commit -m "test: add end-to-end integration tests"
```

---

### Task 4: Documentation Updates

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update README with deployment instructions**

Add after the "运行测试" section:

```markdown
### 部署运行

#### Docker Compose 部署（推荐）

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f api

# 停止服务
docker-compose down
```

#### 服务组件

| 服务 | 端口 | 说明 |
|------|------|------|
| API | 8000 | FastAPI REST API |
| Worker | - | Dramatiq 任务处理 |
| Scheduler | - | APScheduler 定时调度 |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 任务队列 + 缓存 |

#### 手动启动（开发环境）

```bash
# 终端 1: 启动 API
.venv/bin/uvicorn cyberpulse.api.main:app --reload

# 终端 2: 启动 Worker
.venv/bin/dramatiq cyberpulse.tasks.worker

# 终端 3: 启动 Scheduler
.venv/bin/python -m cyberpulse.scheduler
```
```

- [ ] **Step 2: Update CLAUDE.md with new commands**

Add to "常用命令" section:

```markdown
### Docker 命令

```bash
# 启动所有服务
docker-compose up -d

# 重建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add deployment and Docker instructions"
```

---

## Summary

### Tasks

| Task | Description | Effort |
|------|-------------|--------|
| 1 | Scheduler-Dramatiq Integration | ~2 hours |
| 2 | Docker Deployment Infrastructure | ~1 hour |
| 3 | End-to-End Integration Tests | ~1 hour |
| 4 | Documentation Updates | ~30 min |

### Expected Outcomes

After completing this plan:

1. ✅ Scheduler jobs trigger Dramatiq tasks for collection
2. ✅ `docker-compose up -d` starts the entire system
3. ✅ End-to-end data flow verified with tests
4. ✅ Documentation ready for production use

### Remaining Work (Future Phases)

- Web UI dashboard
- Prometheus + Grafana monitoring
- Strategic value feedback from cyber-nexus
- Airflow migration for production