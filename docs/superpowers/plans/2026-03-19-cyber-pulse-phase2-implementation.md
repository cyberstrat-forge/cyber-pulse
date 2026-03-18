# cyber-pulse Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 cyber-pulse Phase 2，完成数据处理管道、多源采集、API 服务、调度系统、评分系统和 CLI 工具

**Strategy:** 渐进式实施，每个子阶段独立规划、实现、测试、提交

**Architecture:** 在 Phase 1 基础上扩展服务层、API 层、调度层和 CLI 层

**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL 15, Redis, APScheduler, Dramatiq, httpx, trafilatura, Typer, Prompt Toolkit, Rich

---

## Phase 2 概览

### 阶段划分

| Phase | 名称 | 模块数 | 交付物 |
|-------|------|--------|--------|
| **2A** | 数据处理管道 | 4 | Normalization + Quality Gate + Item + Content |
| **2B** | 多源采集 | 4 | API/Web/Media Connector + Connector Factory |
| **2C** | API 服务 | 5 | FastAPI Endpoints + Auth |
| **2D** | 调度系统 | 3 | APScheduler + Dramatiq |
| **2E** | 评分系统 | 1 | Source Score Service |
| **2F** | CLI 工具 | 7 | CLI TUI |

### 依赖关系

```
Phase 2A ─┬─▶ Phase 2B (Connector 使用 Item)
          ├─▶ Phase 2C (API 使用 Content)
          └─▶ Phase 2E (Score 使用统计数据)

Phase 2A ──▶ Phase 2D (调度使用 Service)

Phase 2C ──▶ Phase 2F (CLI 使用 API)
Phase 2D ──▶ Phase 2F (CLI 使用调度)
Phase 2E ──▶ Phase 2F (CLI 显示评分)
```

---

## Phase 2A: 数据处理管道

### 目标

实现完整的数据处理管道：Item 生命周期管理 → 内容标准化 → 质量控制 → Content 管理

### 文件结构

```
src/cyberpulse/services/
├── item_service.py          # Item 生命周期管理
├── normalization_service.py # 内容标准化
├── quality_gate_service.py  # 质量控制
├── content_service.py       # Content 管理 + 去重
```

### 任务列表

#### Task 2A.1: ItemService 实现

**Files:**
- Create: `src/cyberpulse/services/item_service.py`
- Create: `tests/test_services/test_item_service.py`

**Spec:**

```python
class ItemService(BaseService):
    """Service for managing item lifecycle"""

    def create_item(
        self,
        source_id: str,
        external_id: str,
        url: str,
        title: str,
        raw_content: str,
        published_at: datetime,
        content_hash: str,
        raw_metadata: Optional[Dict] = None,  # Maps to Item.metadata column
    ) -> Item:
        """Create a new item with deduplication."""
        pass

    def get_items_by_source(
        self,
        source_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Item]:
        """List items for a source."""
        pass

    def update_item_status(
        self,
        item_id: str,
        status: str,
        quality_metrics: Optional[Dict] = None,
    ) -> Optional[Item]:
        """Update item processing status."""
        pass

    def get_pending_items(self, limit: int = 100) -> List[Item]:
        """Get items pending normalization."""
        pass
```

**Deduplication Logic:**
- Check uniqueness by `(source_id, external_id)` or `(source_id, url)`
- If exists, return existing item

**Tests:**
- test_create_item_success
- test_create_duplicate_item
- test_get_items_by_source
- test_update_item_status
- test_get_pending_items

---

#### Task 2A.2: NormalizationService 实现

**Files:**
- Create: `src/cyberpulse/services/normalization_service.py`
- Create: `tests/test_services/test_normalization_service.py`

**Spec:**

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class NormalizationResult:
    """Result of content normalization"""
    normalized_title: str
    normalized_body: str      # Markdown format
    canonical_hash: str       # For deduplication
    language: Optional[str]
    word_count: int
    extraction_method: str    # "trafilatura" | "raw"


class NormalizationService:
    """Service for content normalization"""

    def normalize(
        self,
        title: str,
        raw_content: str,
        url: Optional[str] = None,
    ) -> NormalizationResult:
        """
        Normalize content:
        1. Extract main content using trafilatura
        2. Clean HTML tags
        3. Convert to Markdown
        4. Calculate canonical_hash
        """
        pass

    def _extract_content(self, raw_content: str, url: Optional[str]) -> str:
        """Extract main content using trafilatura."""
        pass

    def _clean_html(self, content: str) -> str:
        """Remove HTML tags, ads, navigation."""
        pass

    def _to_markdown(self, content: str) -> str:
        """Convert HTML to Markdown."""
        pass

    def _calculate_canonical_hash(self, title: str, body: str) -> str:
        """Calculate hash for deduplication."""
        pass

    def _detect_language(self, content: str) -> Optional[str]:
        """Detect content language."""
        pass
```

**Normalization Pipeline:**
1. Content extraction: `trafilatura.extract()`
2. HTML cleaning: remove ads, navigation, scripts
3. Markdown conversion: headers, paragraphs, lists, code blocks
4. Hash calculation: `MD5(normalized_title + normalized_body)`

**Tests:**
- test_normalize_html_content
- test_normalize_plain_text
- test_extract_with_trafilatura
- test_canonical_hash_consistency
- test_language_detection

---

#### Task 2A.3: QualityGateService 实现

**Files:**
- Create: `src/cyberpulse/services/quality_gate_service.py`
- Create: `tests/test_services/test_quality_gate_service.py`

**Spec:**

```python
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

class QualityDecision(str, Enum):
    PASS = "pass"
    REJECT = "reject"


@dataclass
class QualityResult:
    """Result of quality check"""
    decision: QualityDecision
    warnings: List[str]
    metrics: Dict[str, float]
    rejection_reason: Optional[str] = None


class QualityGateService:
    """Service for quality control"""

    # Core field requirements
    REQUIRED_FIELDS = {
        "published_at": {"check": "valid_date", "message": "Invalid or missing date"},
        "title": {"check": "min_length_5", "message": "Title too short"},
        "normalized_body": {"check": "non_empty", "message": "Empty body"},
        "url": {"check": "valid_url", "message": "Invalid URL"},
    }

    # Optional field warnings
    OPTIONAL_FIELDS = {
        "author": {"message": "Missing author"},
    }

    def check(
        self,
        item: Item,
        normalization_result: NormalizationResult,
    ) -> QualityResult:
        """
        Check item quality.

        Returns:
            QualityResult with decision, warnings, and metrics
        """
        pass

    def _validate_required_fields(self, item: Item, norm: NormalizationResult) -> List[str]:
        """Validate required fields, return list of errors."""
        pass

    def _check_optional_fields(self, item: Item) -> List[str]:
        """Check optional fields, return list of warnings."""
        pass

    def _calculate_metrics(self, item: Item, norm: NormalizationResult) -> Dict[str, float]:
        """Calculate quality metrics."""
        pass
```

**Validation Rules:**

| Field | Requirement | Action |
|-------|-------------|--------|
| `published_at` | Valid date, reasonable range | Reject if invalid |
| `title` | Length >= 5 | Reject if too short |
| `normalized_body` | Non-empty | Reject if empty |
| `url` | Valid URL format | Reject if invalid |
| `author` | Optional | Warning if missing |

**Metrics Calculated:**
- `title_length`: Title character count
- `body_length`: Body character count
- `word_count`: Word count
- `meta_completeness`: Metadata completeness score (0-1)
  - Based on presence of: author, tags, published_at
- `content_completeness`: Content quality score (0-1)
  - body_length >= 500 chars: 1.0
  - body_length >= 200 chars: 0.7
  - body_length >= 50 chars: 0.4
  - body_length < 50 chars: 0.2
- `noise_ratio`: Estimated noise in content (0-1)
  - Calculated from raw_content BEFORE normalization
  - Formula: (estimated_html_tags + ad_markers) / total_chars
  - HTML tags estimated via regex: `<[^>]+>` matches
  - Ad markers: count occurrences of "广告", "推广", "推荐阅读", "AD", etc.
  - For clean content after normalization: typically < 0.1

**Tests:**
- test_check_pass
- test_check_reject_missing_title
- test_check_reject_empty_body
- test_check_warnings_missing_author
- test_calculate_metrics

---

#### Task 2A.4: ContentService 实现

**Files:**
- Create: `src/cyberpulse/services/content_service.py`
- Create: `tests/test_services/test_content_service.py`

**Spec:**

```python
class ContentService(BaseService):
    """Service for managing content with deduplication"""

    def create_or_get_content(
        self,
        canonical_hash: str,
        normalized_title: str,
        normalized_body: str,
        item: Item,  # Source item that triggered this content
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

        Returns:
            Tuple of (content, is_new) where is_new is True if created
        """
        pass

    def get_contents(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        source_tier: Optional[SourceTier] = None,
        limit: int = 100,
        cursor: Optional[str] = None,  # For cursor-based pagination
    ) -> List[Content]:
        """List contents with filters and cursor pagination."""
        pass

    def get_content_by_id(self, content_id: str) -> Optional[Content]:
        """Get content by ID."""
        pass

    def get_content_statistics(self) -> Dict[str, Any]:
        """Get content statistics."""
        pass

    def generate_content_id(self) -> str:
        """
        Generate unique content ID with timestamp prefix for ordering.

        Format: cnt_{YYYYMMDDHHMMSS}_{uuid8}
        Example: cnt_20260319143052_a1b2c3d4

        The timestamp prefix ensures lexicographic ordering matches creation time,
        enabling efficient cursor-based pagination.
        """
        pass
```

**Deduplication Logic:**
1. Check if `canonical_hash` exists
2. If exists: increment `source_count`, update `last_seen_at`
3. If not: create new Content with `source_count=1`

**Tests:**
- test_create_content_new
- test_create_content_duplicate
- test_get_contents_with_filters
- test_get_content_by_id
- test_content_statistics

---

### Phase 2A 验收标准

- [ ] 所有 4 个服务实现完成
- [ ] 所有测试通过（覆盖率 >= 80%）
- [ ] 代码通过 ruff 和 mypy 检查
- [ ] 提交到 git

---

## Phase 2B: 多源采集

### 目标

实现 API Connector、Web Scraper Connector、Media API Connector

### 文件结构

```
src/cyberpulse/services/
├── api_connector.py         # API Connector
├── web_connector.py         # Web Scraper Connector
├── media_connector.py       # Media API Connector
```

### 任务列表

#### Task 2B.1: API Connector 实现

**Files:**
- Create: `src/cyberpulse/services/api_connector.py`
- Create: `tests/test_services/test_api_connector.py`

**Spec:**

```python
class APIConnector(BaseConnector):
    """Connector for REST APIs"""

    REQUIRED_CONFIG_KEYS = ["base_url"]

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from API with pagination support."""
        pass

    def _build_request(self, page: int) -> Dict:
        """Build request with auth headers."""
        pass

    def _parse_response(self, data: Dict) -> List[Dict[str, Any]]:
        """Parse API response to standard format."""
        pass
```

**Supported Auth Types:**
- `none`: No authentication
- `bearer`: Bearer token in header
- `api_key`: API key in query param or header
- `basic`: Basic auth

**Pagination Types:**
- `page`: Page-based pagination
- `offset`: Offset-based pagination
- `cursor`: Cursor-based pagination

**Tests:**
- test_fetch_no_auth
- test_fetch_bearer_auth
- test_fetch_with_pagination
- test_validate_config

---

#### Task 2B.2: Web Scraper Connector 实现

**Files:**
- Create: `src/cyberpulse/services/web_connector.py`
- Create: `tests/test_services/test_web_connector.py`

**Spec:**

```python
class WebScraperConnector(BaseConnector):
    """Connector for web scraping"""

    REQUIRED_CONFIG_KEYS = ["base_url"]

    async def fetch(self) -> List[Dict[str, Any]]:
        """Scrape web pages and extract content."""
        pass

    def _fetch_page(self, url: str) -> str:
        """Fetch page HTML."""
        pass

    def _extract_links(self, html: str) -> List[str]:
        """Extract article links from page."""
        pass

    def _extract_content(self, html: str, url: str) -> Dict:
        """Extract content from article page using trafilatura."""
        pass
```

**Extraction Modes:**
- `auto`: Auto-detect using trafilatura
- `manual`: Use XPath/CSS selectors from config

**Tests:**
- test_fetch_auto_mode
- test_extract_links
- test_extract_content
- test_handle_pagination

---

#### Task 2B.3: Media API Connector 实现

**Files:**
- Create: `src/cyberpulse/services/media_connector.py`
- Create: `tests/test_services/test_media_connector.py`

**Spec:**

```python
class MediaAPIConnector(BaseConnector):
    """Connector for media platforms (YouTube)"""

    REQUIRED_CONFIG_KEYS = ["platform", "api_key"]

    async def fetch(self) -> List[Dict[str, Any]]:
        """Fetch items from media API."""
        pass

    def _fetch_youtube_videos(self, channel_id: str) -> List[Dict]:
        """Fetch videos from YouTube channel."""
        pass

    def _check_captions(self, video_id: str) -> bool:
        """Check if video has captions."""
        pass
```

**Supported Platforms:**
- `youtube`: YouTube Data API v3

**Tests:**
- test_fetch_youtube
- test_check_captions
- test_validate_config

---

---

#### Task 2B.4: Connector Factory

**Files:**
- Create: `src/cyberpulse/services/connector_factory.py`
- Update: `src/cyberpulse/services/__init__.py`
- Create: `tests/test_services/test_connector_factory.py`

**Spec:**

```python
# connector_factory.py
from typing import Dict, Type
from .connector_service import BaseConnector
from .rss_connector import RSSConnector
from .api_connector import APIConnector
from .web_connector import WebScraperConnector
from .media_connector import MediaAPIConnector

# Connector type registry
CONNECTOR_REGISTRY: Dict[str, Type[BaseConnector]] = {
    "rss": RSSConnector,
    "api": APIConnector,
    "web": WebScraperConnector,
    "media": MediaAPIConnector,
}


def get_connector(connector_type: str, config: Dict) -> BaseConnector:
    """
    Get appropriate connector instance for a source.

    Args:
        connector_type: Type string (rss, api, web, media)
        config: Connector configuration dict

    Returns:
        Connector instance

    Raises:
        ValueError: If connector_type is unknown
    """
    connector_class = CONNECTOR_REGISTRY.get(connector_type)
    if not connector_class:
        raise ValueError(
            f"Unknown connector type: {connector_type}. "
            f"Available types: {list(CONNECTOR_REGISTRY.keys())}"
        )
    return connector_class(config)


def get_connector_for_source(source: Source) -> BaseConnector:
    """
    Get connector instance for a Source model.

    Args:
        source: Source model instance

    Returns:
        Connector instance configured from source.config
    """
    return get_connector(source.connector_type, source.config)
```

**Tests:**
- test_get_connector_rss
- test_get_connector_api
- test_get_connector_web
- test_get_connector_media
- test_get_connector_unknown_type
- test_get_connector_for_source

---

### Phase 2B 验收标准

- [ ] 所有 3 个 Connector 实现完成
- [ ] 所有测试通过（覆盖率 >= 80%）
- [ ] 代码通过 ruff 和 mypy 检查
- [ ] 提交到 git

---

## Phase 2C: API 服务

### 目标

实现 FastAPI REST API，提供 Content/Source/Client 管理接口

### 文件结构

```
src/cyberpulse/api/
├── __init__.py
├── main.py                  # FastAPI app
├── dependencies.py          # Dependency injection
├── auth.py                  # API Key authentication
├── routers/
│   ├── __init__.py
│   ├── content.py           # Content API
│   ├── sources.py           # Source API
│   ├── clients.py           # API Client management
│   └── health.py            # Health check
├── schemas/
│   ├── __init__.py
│   ├── content.py
│   ├── source.py
│   └── client.py
```

### 任务列表

#### Task 2C.1: FastAPI 应用初始化 + Health API

**Files:**
- Create: `src/cyberpulse/api/__init__.py`
- Create: `src/cyberpulse/api/main.py`
- Create: `src/cyberpulse/api/dependencies.py`
- Create: `src/cyberpulse/api/routers/__init__.py`
- Create: `src/cyberpulse/api/routers/health.py`
- Create: `tests/test_api/__init__.py`
- Create: `tests/test_api/test_health_api.py`

**Spec:**

```python
# main.py
from fastapi import FastAPI
from .routers import content, sources, clients, health

app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(content.router, prefix="/api/v1", tags=["content"])
app.include_router(sources.router, prefix="/api/v1", tags=["sources"])
app.include_router(clients.router, prefix="/api/v1", tags=["clients"])
```

```python
# routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from ...database import get_db

router = APIRouter()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)) -> dict:
    """
    Health check endpoint.

    Returns:
        Status of API, database, and Redis connections
    """
    # Check database
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": "0.1.0",
        "components": {
            "database": db_status,
            "api": "healthy",
        }
    }
```

**Tests:**
- test_health_check_healthy
- test_health_check_database_unavailable

---

#### Task 2C.2: API Key 认证

**Files:**
- Create: `src/cyberpulse/api/auth.py`
- Create: `tests/test_api/test_auth.py`

**Spec:**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> ApiClient:
    """Validate API key and return client."""
    pass

async def require_permissions(permissions: List[str]):
    """Dependency for permission checking."""
    pass
```

---

#### Task 2C.3: Content API

**Files:**
- Create: `src/cyberpulse/api/routers/content.py`
- Create: `src/cyberpulse/api/schemas/content.py`
- Create: `tests/test_api/test_content_api.py`

**Spec:**

```python
# routers/content.py
@router.get("/content")
async def list_content(
    cursor: Optional[str] = None,  # Cursor is the last content_id seen (string, e.g., "cnt_abc123")
    since: Optional[datetime] = None,
    limit: int = 100,
    source_tier: Optional[str] = None,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> ContentListResponse:
    """
    List content with cursor-based pagination.

    Cursor pagination: cursor is the last content_id the client has seen.
    Server returns content where content_id > cursor (lexicographic comparison), ordered by content_id.
    If cursor is None, returns from the beginning.

    Note: content_id is a string (e.g., "cnt_abc123"), so cursor comparison is lexicographic.
    For consistent ordering, content_id is generated with a timestamp prefix.
    """
    pass

@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> ContentResponse:
    """Get content by ID."""
    pass
```

**Response Format:**

```json
{
  "data": [...],
  "next_cursor": "cnt_20260319_abc456",
  "has_more": true,
  "count": 100,
  "server_timestamp": "2026-03-19T10:00:00Z"
}
```

**Note:** `next_cursor` is a string matching the `content_id` type.

---

#### Task 2C.4: Source API

**Files:**
- Create: `src/cyberpulse/api/routers/sources.py`
- Create: `src/cyberpulse/api/schemas/source.py`
- Create: `tests/test_api/test_source_api.py`

**Spec:**

```python
# routers/sources.py
@router.get("/sources")
async def list_sources(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceListResponse:
    """List sources."""
    pass

@router.post("/sources")
async def create_source(
    source: SourceCreate,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Create a new source."""
    pass

@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Get source by ID."""
    pass

@router.patch("/sources/{source_id}")
async def update_source(
    source_id: str,
    source: SourceUpdate,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Update source."""
    pass

@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    client: ApiClient = Depends(get_current_client),
    db: Session = Depends(get_db),
) -> None:
    """Delete source."""
    pass
```

---

#### Task 2C.5: Client API

**Files:**
- Create: `src/cyberpulse/api/routers/clients.py`
- Create: `src/cyberpulse/api/schemas/client.py`
- Create: `tests/test_api/test_client_api.py`

**Spec:**

```python
# routers/clients.py
@router.post("/clients")
async def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
) -> ClientResponse:
    """Create API client."""
    pass

@router.get("/clients")
async def list_clients(
    db: Session = Depends(get_db),
) -> ClientListResponse:
    """List API clients."""
    pass

@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete API client."""
    pass
```

---

### Phase 2C 验收标准

- [ ] FastAPI 应用可启动
- [ ] 所有 API 端点实现完成
- [ ] API Key 认证工作正常
- [ ] 所有测试通过
- [ ] 提交到 git

---

## Phase 2D: 调度系统

### 目标

实现 APScheduler 定时调度和 Dramatiq 异步任务处理

### 文件结构

```
src/cyberpulse/
├── scheduler/
│   ├── __init__.py
│   ├── scheduler.py          # APScheduler 配置
│   └── jobs.py               # Job 定义
├── tasks/
│   ├── __init__.py
│   ├── worker.py             # Dramatiq Worker
│   ├── ingestion_tasks.py    # 采集任务
│   ├── normalization_tasks.py # 标准化任务
│   └── quality_tasks.py      # 质量控制任务
```

### 任务列表

#### Task 2D.1: APScheduler 配置

**Files:**
- Create: `src/cyberpulse/scheduler/__init__.py`
- Create: `src/cyberpulse/scheduler/scheduler.py`
- Create: `src/cyberpulse/scheduler/jobs.py`
- Create: `tests/test_scheduler/`

**Spec:**

```python
# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

class SchedulerService:
    """APScheduler service for periodic jobs"""

    def __init__(self, database_url: str):
        jobstores = {
            'default': SQLAlchemyJobStore(url=database_url)
        }
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)

    def start(self):
        """Start the scheduler."""
        pass

    def stop(self):
        """Stop the scheduler."""
        pass

    def schedule_source_collection(self, source_id: str, interval: int = 3600):
        """Schedule periodic collection for a source."""
        pass
```

---

#### Task 2D.2: Dramatiq Worker 配置

**Files:**
- Create: `src/cyberpulse/tasks/__init__.py`
- Create: `src/cyberpulse/tasks/worker.py`
- Create: `tests/test_tasks/`

**Spec:**

```python
# worker.py
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

redis_url = settings.redis_url
broker = RedisBroker(url=redis_url)
result_backend = RedisBackend(url=redis_url)
broker.add_middleware(Results(backend=result_backend))
dramatiq.set_broker(broker)
```

---

#### Task 2D.3: 异步任务实现

**Files:**
- Create: `src/cyberpulse/tasks/ingestion_tasks.py`
- Create: `src/cyberpulse/tasks/normalization_tasks.py`
- Create: `src/cyberpulse/tasks/quality_tasks.py`
- Create: `tests/test_tasks/__init__.py`
- Create: `tests/test_tasks/test_ingestion_tasks.py`
- Create: `tests/test_tasks/test_normalization_tasks.py`
- Create: `tests/test_tasks/test_quality_tasks.py`

**Spec:**

```python
# ingestion_tasks.py
import dramatiq
from .worker import broker

@dramatiq.actor(max_retries=3)
def ingest_source(source_id: str):
    """Ingest items from a source.

    1. Get source from database
    2. Use connector_factory.get_connector_for_source() to create appropriate connector
    3. Call connector.fetch() to get items
    4. Create Item records via ItemService
    5. Queue normalize_item for each new item
    """
    pass
```

```python
# normalization_tasks.py
import dramatiq
from .worker import broker

@dramatiq.actor(max_retries=3)
def normalize_item(item_id: str):
    """Normalize an item.

    1. Get item from database
    2. Run NormalizationService
    3. Update item with normalized content
    4. Queue quality check
    """
    pass
```

```python
# quality_tasks.py
import dramatiq
from .worker import broker

@dramatiq.actor(max_retries=3)
def quality_check_item(item_id: str):
    """Run quality check on an item.

    1. Get item and normalization result
    2. Run QualityGateService
    3. If pass: create/update Content via ContentService
    4. If reject: mark item as rejected
    """
    pass
```

**Tests:**
- test_ingest_source_success
- test_ingest_source_failure
- test_normalize_item_success
- test_normalize_item_failure
- test_quality_check_pass
- test_quality_check_reject

---

### Phase 2D 验收标准

- [ ] APScheduler 可启动和停止
- [ ] Dramatiq Worker 可运行
- [ ] 任务队列工作正常
- [ ] 所有测试通过
- [ ] 提交到 git

---

## Phase 2E: 评分系统

### 目标

实现 Source Score Service，包含采集健康度（C 维度）和战略价值预留（V 维度）

### 文件结构

```
src/cyberpulse/services/
├── source_score_service.py   # Source Score 计算
```

### 任务列表

#### Task 2E.1: Source Score Service 实现

**Files:**
- Create: `src/cyberpulse/services/source_score_service.py`
- Create: `tests/test_services/test_source_score_service.py`

**Spec:**

```python
@dataclass
class ScoreComponents:
    """Score components"""
    stability: float      # Cs: Source stability
    activity: float       # Cf: Update frequency
    quality: float        # Cq: Content quality
    strategic_value: float = 0.5  # V: Strategic value (default)


class SourceScoreService(BaseService):
    """Service for calculating and updating source scores"""

    # Weight configuration
    WEIGHTS = {
        "stability": 0.30,
        "activity": 0.30,
        "quality": 0.40,
    }

    def calculate_score(self, source_id: str) -> float:
        """Calculate comprehensive score for a source."""
        pass

    def calculate_stability(self, source_id: str) -> float:
        """Calculate source stability (Cs)."""
        pass

    def calculate_activity(self, source_id: str) -> float:
        """Calculate update activity (Cf)."""
        pass

    def calculate_quality(self, source_id: str) -> float:
        """Calculate content quality (Cq)."""
        pass

    def update_tier(self, source_id: str) -> SourceTier:
        """Update tier based on score."""
        pass

    def check_tier_evolution(self, source_id: str) -> Dict:
        """Check if source should be promoted/demoted."""
        pass
```

**Score Formula:**
```
C = 0.30 * Cs + 0.30 * Cf + 0.40 * Cq
Score = 0.60 * C + 0.40 * V

Where:
- Cs (Stability): min(1.0, updates_in_past_30_days / 30)
- Cf (Activity): min(1.0, weekly_items / REFERENCE_VALUE)
  - REFERENCE_VALUE = 7 (assuming 1 item/day as baseline)
- Cq (Quality): meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
- V (Strategic Value): Default 0.5 (reserved for cyber-nexus feedback)

Final Score = Score * 100 (scale 0-100)
```

**Tier Mapping:**
- T0: Score >= 80
- T1: 60 <= Score < 80
- T2: 40 <= Score < 60
- T3: Score < 40

**Tests:**
- test_calculate_stability
- test_calculate_activity
- test_calculate_quality
- test_calculate_score
- test_update_tier
- test_tier_evolution

---

### Phase 2E 验收标准

- [ ] Source Score Service 实现完成
- [ ] 所有测试通过
- [ ] 提交到 git

---

## Phase 2F: CLI 工具

### 目标

实现完整的 CLI TUI，支持交互式和脚本模式

### 文件结构

```
src/cyberpulse/cli/
├── __init__.py
├── app.py                    # CLI 主入口
├── tui.py                    # TUI 应用
├── commands/
│   ├── __init__.py
│   ├── source.py             # Source 命令
│   ├── job.py                # Job 命令
│   ├── content.py            # Content 命令
│   ├── client.py             # Client 命令
│   ├── config.py             # Config 命令
│   ├── log.py                # Log 命令
│   └── diagnose.py           # Diagnose 命令
```

### 任务列表

#### Task 2F.1: CLI 主入口 + TUI 实现

**Files:**
- Create: `src/cyberpulse/cli/__init__.py`
- Create: `src/cyberpulse/cli/app.py`
- Create: `src/cyberpulse/cli/tui.py`
- Create: `tests/test_cli/__init__.py`
- Create: `tests/test_cli/test_cli_main.py`

**Spec:**

```python
# app.py
import typer
from typing import Optional
from .commands import source, job, content, client, config, log, diagnose

app = typer.Typer(
    name="cyber-pulse",
    help="Security Intelligence Collection System",
)

# Register command modules
app.add_typer(source.app, name="source")
app.add_typer(job.app, name="job")
app.add_typer(content.app, name="content")
app.add_typer(client.app, name="client")
app.add_typer(config.app, name="config")
app.add_typer(log.app, name="log")
app.add_typer(diagnose.app, name="diagnose")

@app.command()
def shell():
    """Start interactive TUI."""
    from .tui import run_tui
    run_tui()

@app.command()
def version():
    """Show version."""
    from ... import __version__
    typer.echo(f"cyber-pulse version {__version__}")

@app.command()
def server(
    action: str = typer.Argument(..., help="start|stop|restart|status"),
    port: int = typer.Option(8000, "--port", "-p"),
):
    """Manage API server."""
    pass
```

```python
# tui.py
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit
from prompt_toolkit.widgets import Box, Label
from rich.console import Console

console = Console()

def run_tui():
    """
    Start interactive TUI mode.

    Layout:
    ┌─────────────────────────────────────────┐
    │  🚀 cyber-pulse CLI                     │
    │  Type '/help' for commands              │
    ├─────────────────────────────────────────┤
    │  [Output Area]                          │
    │                                         │
    ├─────────────────────────────────────────┤
    │  cyber-pulse> [Input]                   │
    ├─────────────────────────────────────────┤
    │  Status: Running | DB: Connected        │
    └─────────────────────────────────────────┘

    Features:
    - Command history (up/down arrows)
    - Tab completion for commands
    - Rich output formatting (tables, colors)
    - Real-time status bar
    """
    pass
```

**Tests:**
- test_cli_version
- test_cli_help
- test_tui_start

---

---

#### Task 2F.2: Source 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/__init__.py`
- Create: `src/cyberpulse/cli/commands/source.py`
- Create: `tests/test_cli/test_source_commands.py`

**Spec:**

```python
# commands/source.py
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="source", help="Manage sources")
console = Console()

@app.command("list")
def list_sources(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
):
    """List all sources."""
    pass

@app.command("add")
def add_source(
    name: str,
    connector: str,
    url: str,
    tier: str = "T2",
):
    """Add a new source."""
    pass

@app.command("update")
def update_source(
    source_id: str,
    tier: Optional[str] = None,
    status: Optional[str] = None,
):
    """Update a source."""
    pass

@app.command("remove")
def remove_source(source_id: str):
    """Remove a source."""
    pass

@app.command("test")
def test_source(source_id: str):
    """Test source connectivity."""
    pass

@app.command("stats")
def source_stats():
    """Show source statistics."""
    pass
```

**Tests:**
- test_source_list
- test_source_add
- test_source_update
- test_source_remove
- test_source_test

---

#### Task 2F.3: Job 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/job.py`
- Create: `tests/test_cli/test_job_commands.py`

**Spec:**

```python
# commands/job.py
app = typer.Typer(name="job", help="Manage jobs")

@app.command("list")
def list_jobs(status: Optional[str] = None):
    """List jobs."""
    pass

@app.command("run")
def run_job(source_id: str):
    """Run job for a source."""
    pass

@app.command("cancel")
def cancel_job(job_id: str):
    """Cancel a job."""
    pass

@app.command("status")
def job_status(job_id: str):
    """Get job status."""
    pass
```

**Tests:**
- test_job_list
- test_job_run
- test_job_cancel
- test_job_status

---

#### Task 2F.4: Content 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/content.py`
- Create: `tests/test_cli/test_content_commands.py`

**Spec:**

```python
# commands/content.py
app = typer.Typer(name="content", help="Manage content")

@app.command("list")
def list_content(
    since: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = 100,
):
    """List content."""
    pass

@app.command("get")
def get_content(
    content_id: Optional[str] = None,
    since: Optional[str] = None,
    tier: Optional[str] = None,
    format: str = "json",
):
    """Get content by ID or filter."""
    pass

@app.command("stats")
def content_stats():
    """Show content statistics."""
    pass
```

**Tests:**
- test_content_list
- test_content_get
- test_content_stats

---

#### Task 2F.5: Client 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/client.py`
- Create: `tests/test_cli/test_client_commands.py`

**Spec:**

```python
# commands/client.py
app = typer.Typer(name="client", help="Manage API clients")

@app.command("create")
def create_client(name: str):
    """Create API client."""
    pass

@app.command("list")
def list_clients():
    """List API clients."""
    pass

@app.command("disable")
def disable_client(client_id: str):
    """Disable API client."""
    pass

@app.command("enable")
def enable_client(client_id: str):
    """Enable API client."""
    pass

@app.command("delete")
def delete_client(client_id: str):
    """Delete API client."""
    pass
```

**Tests:**
- test_client_create
- test_client_list
- test_client_disable
- test_client_enable
- test_client_delete

---

#### Task 2F.6: Config 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/config.py`
- Create: `tests/test_cli/test_config_commands.py`

**Spec:**

```python
# commands/config.py
app = typer.Typer(name="config", help="Manage configuration")

@app.command("get")
def get_config(key: str):
    """Get config value."""
    pass

@app.command("set")
def set_config(key: str, value: str):
    """Set config value."""
    pass

@app.command("list")
def list_config():
    """List all config."""
    pass

@app.command("reset")
def reset_config():
    """Reset to defaults."""
    pass
```

**Tests:**
- test_config_get
- test_config_set
- test_config_list
- test_config_reset

---

#### Task 2F.7: Log 和 Diagnose 命令模块

**Files:**
- Create: `src/cyberpulse/cli/commands/log.py`
- Create: `src/cyberpulse/cli/commands/diagnose.py`
- Create: `tests/test_cli/test_log_commands.py`
- Create: `tests/test_cli/test_diagnose_commands.py`

**Spec:**

```python
# commands/log.py
app = typer.Typer(name="log", help="View logs")

@app.command("tail")
def tail_logs(n: int = 50, follow: bool = False):
    """Tail logs."""
    pass

@app.command("errors")
def error_logs(since: Optional[str] = None, source: Optional[str] = None):
    """Show error logs."""
    pass

@app.command("search")
def search_logs(text: str):
    """Search logs."""
    pass

@app.command("stats")
def log_stats():
    """Show log statistics."""
    pass
```

```python
# commands/diagnose.py
app = typer.Typer(name="diagnose", help="System diagnostics")

@app.command("system")
def diagnose_system():
    """Check system health."""
    pass

@app.command("sources")
def diagnose_sources(pending: bool = False):
    """Diagnose sources."""
    pass

@app.command("errors")
def diagnose_errors():
    """Analyze errors."""
    pass
```

**Tests:**
- test_log_tail
- test_log_errors
- test_log_search
- test_diagnose_system
- test_diagnose_sources
- test_diagnose_errors

---

### Phase 2F 验收标准

- [ ] CLI 可启动
- [ ] 所有命令工作正常
- [ ] TUI 交互正常
- [ ] 提交到 git

---

## 执行顺序

1. **Phase 2A** → 数据处理管道（基础）
2. **Phase 2B** → 多源采集（依赖 Item）
3. **Phase 2C** → API 服务（依赖 Content）
4. **Phase 2D** → 调度系统（依赖 Service）
5. **Phase 2E** → 评分系统（依赖统计数据）
6. **Phase 2F** → CLI 工具（依赖所有组件）

---

## 验收标准总览

| Phase | 模块数 | 测试数 | 提交数 |
|-------|--------|--------|--------|
| 2A | 4 | ~20 | 1 |
| 2B | 4 | ~18 | 1 |
| 2C | 5 | ~22 | 1 |
| 2D | 3 | ~10 | 1 |
| 2E | 1 | ~6 | 1 |
| 2F | 7 | ~25 | 1 |

**总计：** 24 个模块，~100 个测试，6 次提交

---

## 文档

**计划保存到:** `docs/superpowers/plans/2026-03-19-cyber-pulse-phase2-implementation.md`

**下一步:** 使用 superpowers:subagent-driven-development 执行 Phase 2A