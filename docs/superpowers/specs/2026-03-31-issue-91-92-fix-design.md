# Issue #91 & #92 修复设计

## 概述

本文档描述以下问题的修复方案：

| Issue | 问题 | 修复方案 |
|-------|------|----------|
| #91 | Client 删除语义不一致 | 改为物理删除 |
| #92 | Scheduler 缺少审计追踪 | 统一创建 Job 记录 |
| - | 遗留代码清理 | 删除未使用文件、移除内部字段、优化部署包 |

## 问题分析

### Issue #91: Client 删除语义不一致

| 问题 | 说明 |
|------|------|
| 当前行为 | `DELETE /clients/{id}` 执行软删除（status → REVOKED） |
| 文档描述 | "客户端将无法访问 API，且无法恢复" |
| 不一致点 | 软删除可恢复（通过 activate 端点），与文档矛盾 |
| 数据残留 | 已删除客户端永久残留在数据库中 |

### Issue #92: Scheduler 缺少审计追踪

| 触发方式 | 当前行为 | job 记录 |
|----------|----------|----------|
| 手动触发 `POST /jobs` | 创建 job 记录 | ✅ 有 |
| 创建源自动采集 | 不创建 job 记录 | ❌ 无 |
| Scheduler 定时触发 | 不创建 job 记录 | ❌ 无 |

**影响**：无法追踪定时采集的执行历史，问题排查困难，监控盲区。

## 设计方案

### 方案一：Client 物理删除

**理由**：
1. 行为与文档"无法恢复"一致
2. API Key 泄露后应立即彻底删除
3. ApiClient 无外键关联，无级联删除问题

**改动**：
- `DELETE /clients/{id}` 直接执行 `DELETE FROM api_clients`
- 删除不再需要的 `revoke_client()` 方法

### 方案二：统一创建 Job 记录

**新增 `JobTrigger` 枚举**：

| 值 | 说明 | 触发来源 |
|----|------|----------|
| `manual` | 手动触发 | `POST /jobs` |
| `scheduler` | 定时触发 | APScheduler |
| `create` | 创建源自动触发 | `POST /sources` |

**理由**：
1. 所有采集行为都有审计追踪
2. 用户可以看到首次采集是否成功
3. `diagnose` 统计数据完整

## 数据模型

### Job 模型扩展

```python
# src/cyberpulse/models/job.py

class JobTrigger(StrEnum):
    """Job trigger source enumeration."""
    MANUAL = "manual"
    SCHEDULER = "scheduler"
    CREATE = "create"

class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    # ... 现有字段 ...

    # 新增：触发来源
    trigger: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=JobTrigger.MANUAL
    )
```

### Schema 扩展

```python
# src/cyberpulse/api/schemas/job.py

class JobResponse(BaseModel):
    job_id: str
    type: str
    status: str
    source_id: str | None = None
    source_name: str | None = None
    trigger: str | None = None  # 新增
    # ... 其他字段 ...
```

## API 改动

### Client 删除端点

**文件**: `src/cyberpulse/api/routers/admin/clients.py`

**现有导入**：
```python
from sqlalchemy.orm import Session
from ....models import ApiClientStatus
from ...auth import ApiClient, ApiClientService, require_permissions
```

**需新增导入**：
```python
from sqlalchemy import delete  # 物理删除
from ....models import ApiClient  # 模型（当前只有 ApiClientStatus）
```

**改动代码**：

```python
@router.delete("/clients/{client_id}", status_code=200)
async def delete_client(
    client_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Delete an API client (permanent deletion)."""
    validate_client_id(client_id)

    logger.info(f"Deleting API client: {client_id}")

    result = db.execute(
        delete(ApiClient).where(ApiClient.client_id == client_id)
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")

    db.commit()

    return {"message": f"Client {client_id} deleted"}
```

### Job 创建端点

**文件**: `src/cyberpulse/api/routers/admin/jobs.py`

```python
from ....models import Job, JobStatus, JobType, JobTrigger

def build_job_response(job: Job, source_name: str | None = None) -> JobResponse:
    return JobResponse(
        # ... 现有字段 ...
        trigger=job.trigger,  # 新增
    )

@router.post("/jobs", response_model=JobCreatedResponse, status_code=201)
async def create_job(request: JobCreate, db: Session = Depends(get_db), ...):
    job = Job(
        job_id=f"job_{secrets.token_hex(8)}",
        type=JobType.INGEST,
        status=JobStatus.PENDING,
        source_id=request.source_id,
        trigger=JobTrigger.MANUAL,  # 新增
    )
    # ... 后续逻辑 ...
```

### Source 创建端点

**文件**: `src/cyberpulse/api/routers/admin/sources.py`

**现有导入**（无需修改）：
```python
import secrets
from ....models import Job, JobStatus, JobType
```

**需新增导入**：
```python
from ....models import JobTrigger  # 或 from ....models.job import JobTrigger
```

**改动代码**：

```python
@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(source: SourceCreate, db: Session = Depends(get_db), ...):
    # ... 创建 source 逻辑 ...

    # Trigger initial ingestion with job tracking
    warnings: list[str] = []
    try:
        job = Job(
            job_id=f"job_{secrets.token_hex(8)}",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id=new_source.source_id,
            trigger=JobTrigger.CREATE,
        )
        db.add(job)
        db.commit()

        ingest_source.send(new_source.source_id, job_id=job.job_id)
        logger.info(f"Triggered initial ingestion for source: {new_source.source_id}, job: {job.job_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to trigger initial ingestion: {e}", exc_info=True)
        warnings.append("源已创建，但初始采集任务触发失败，请手动检查")

    return build_source_response(new_source, warnings if warnings else None)
```

## Scheduler 改动

**文件**: `src/cyberpulse/scheduler/jobs.py`

```python
"""Job functions for the scheduler.

Import order note:
- ingest_source import triggers worker.py which configures the broker
- Job model imports are safe as they don't depend on broker configuration
"""

import logging
import secrets
from typing import Any

from ..database import SessionLocal
from ..models import Job, JobStatus, JobType, Item, ItemStatus, Source, SourceStatus
from ..models.job import JobTrigger
from ..services.source_score_service import SourceScoreService
from ..tasks.ingestion_tasks import ingest_source

logger = logging.getLogger(__name__)


def collect_source(source_id: str) -> dict[str, Any]:
    """Collect items from a source via Dramatiq task."""
    db = SessionLocal()
    try:
        job = Job(
            job_id=f"job_{secrets.token_hex(8)}",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
            source_id=source_id,
            trigger=JobTrigger.SCHEDULER,
        )
        db.add(job)
        db.commit()

        ingest_source.send(source_id, job_id=job.job_id)

        logger.info(f"Created scheduler job {job.job_id} for source {source_id}")

        return {
            "source_id": source_id,
            "job_id": job.job_id,
            "status": "queued",
            "message": "Collection job queued successfully",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create job for source {source_id}: {e}")
        raise
    finally:
        db.close()


def run_scheduled_collection() -> dict[str, Any]:
    """Run scheduled collection for all active sources."""
    db = SessionLocal()
    try:
        sources = db.query(Source).filter(
            Source.status == SourceStatus.ACTIVE
        ).all()

        queued_count = 0
        failed_count = 0
        job_ids = []

        for source in sources:
            try:
                job = Job(
                    job_id=f"job_{secrets.token_hex(8)}",
                    type=JobType.INGEST,
                    status=JobStatus.PENDING,
                    source_id=source.source_id,
                    trigger=JobTrigger.SCHEDULER,
                )
                db.add(job)
                db.flush()

                ingest_source.send(source.source_id, job_id=job.job_id)
                job_ids.append(job.job_id)
                queued_count += 1
            except Exception as e:
                logger.error(f"Failed to queue source {source.source_id}: {e}")
                failed_count += 1
                continue

        db.commit()

        logger.info(f"Queued {queued_count} sources for collection ({failed_count} failed)")

        return {
            "status": "completed",
            "sources_count": queued_count,
            "failed_count": failed_count,
            "job_ids": job_ids,
            "message": f"Queued {queued_count} sources for collection ({failed_count} failed)",
        }
    finally:
        db.close()
```

## 数据库迁移

**文件**: `alembic/versions/xxx_add_job_trigger_field.py`

```python
"""add job trigger field

Revision ID: <auto_generated>
Revises: a1b2c3d4e5f6
Create Date: 2026-03-31
"""

from alembic import op
import sqlalchemy as sa

revision = '<auto_generated>'
down_revision = 'a1b2c3d4e5f6'

def upgrade() -> None:
    op.add_column('jobs', sa.Column('trigger', sa.String(20), nullable=True))
    op.execute("UPDATE jobs SET trigger = 'manual' WHERE trigger IS NULL")

def downgrade() -> None:
    op.drop_column('jobs', 'trigger')
```

## Items API 改动

### Schema 修改

**文件**: `src/cyberpulse/api/schemas/item.py`

```python
class ItemResponse(BaseModel):
    """Single item response."""
    id: str = Field(..., description="Item unique identifier")
    title: str = Field(..., description="Normalized title (with fallback to raw title)")
    author: str | None = None
    published_at: datetime | None = None
    body: str | None = None
    url: str | None = None
    completeness_score: float | None = Field(None, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    word_count: int | None = Field(None, description="Word count of normalized body")
    fetched_at: datetime | None = None
    source: SourceInItem | None = None
    # 移除 full_fetch_attempted 和 full_fetch_succeeded
```

### 路由修改

**文件**: `src/cyberpulse/api/routers/items.py`

```python
# 构建响应时移除内部字段
data.append(ItemResponse(
    id=item.item_id,
    title=item.normalized_title or item.title,
    author=item.raw_metadata.get("author") if item.raw_metadata else None,
    published_at=item.published_at,
    body=item.normalized_body,
    url=item.url,
    completeness_score=calculate_completeness_score(item),
    tags=item.raw_metadata.get("tags", []) if item.raw_metadata else [],
    word_count=item.word_count,
    fetched_at=item.fetched_at,
    source=source_info,
    # 移除 full_fetch_attempted=item.full_fetch_attempted,
    # 移除 full_fetch_succeeded=item.full_fetch_succeeded,
))
```

## 部署包改动

**文件**: `scripts/build-deploy-package.sh`

```python
# 部署包包含的文件（移除 sources.yaml）
DEPLOY_FILES=(
    "scripts/cyber-pulse.sh"
    "scripts/api.sh"
    "deploy/"
    # "sources.yaml"  # 移除：用户不需要预置配置
    "install-ops.sh"
)

# copy_files() 函数中，创建空示例文件
# 创建 sources.yaml 示例文件（空配置）
cat > "$TEMP_DIR/cyber-pulse/sources.yaml" << 'EOF'
# Cyber Pulse 情报源配置
# 
# 配置方式：
#   1. 通过 API 导入: ./scripts/api.sh sources import < opml_file
#   2. 手动配置: 参考 docs/source-config-examples.md
#
# 示例格式：
# sources:
#   - name: "示例 RSS 源"
#     connector_type: rss
#     config:
#       feed_url: "https://example.com/feed.xml"

sources: []
EOF
```

## 删除的代码

| 文件 | 删除内容 |
|------|----------|
| `src/cyberpulse/api/auth.py` | `ApiClientService.revoke_client()` 方法 |
| `src/cyberpulse/api/routers/admin/clients.py` | 原软删除逻辑 |

## 遗留代码清理

### 1. 删除未使用的 `routers/clients.py`

发现 `src/cyberpulse/api/routers/clients.py`（151行）是未使用的遗留文件：

| 文件 | 状态 | 说明 |
|------|------|------|
| `routers/clients.py` | ⚠️ 未使用 | 被 `routers/__init__.py` 导入但 `main.py` 未引用 |
| `routers/admin/clients.py` | ✅ 使用中 | 注册到 `/api/v1/admin` |

**处理**：删除未使用的 `routers/clients.py` 文件。

### 2. Items API 移除内部字段

下游应用不需要 `full_fetch_attempted` / `full_fetch_succeeded` 这两个内部状态字段。

**涉及文件**：
- `src/cyberpulse/api/schemas/item.py` - 移除 `ItemResponse` 中的这两个字段
- `src/cyberpulse/api/routers/items.py` - 移除构建响应时的字段赋值

### 3. 部署包移除 `sources.yaml`

运维用户不需要预置的 `sources.yaml`，应自行配置或通过 API 导入。

**涉及文件**：
- `scripts/build-deploy-package.sh` - 从 `DEPLOY_FILES` 中移除 `sources.yaml`
- 创建空的示例文件替代（仅包含格式说明）

## 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/cyberpulse/models/job.py` | 修改 | 添加 `JobTrigger` 枚举和 `trigger` 字段 |
| `src/cyberpulse/models/__init__.py` | 修改 | 导出 `JobTrigger` |
| `src/cyberpulse/api/schemas/job.py` | 修改 | `JobResponse` 添加 `trigger` 字段 |
| `src/cyberpulse/api/schemas/item.py` | 修改 | 移除 `full_fetch_attempted`, `full_fetch_succeeded` |
| `src/cyberpulse/api/routers/admin/jobs.py` | 修改 | ① 导入 `JobTrigger` ② `build_job_response` 添加 `trigger` ③ 创建 job 时设置 trigger |
| `src/cyberpulse/api/routers/admin/sources.py` | 修改 | ① 导入 `JobTrigger`（已有 Job, JobStatus, JobType, secrets） ② 创建源时创建 job |
| `src/cyberpulse/api/routers/admin/clients.py` | 修改 | ① 导入 `delete`, `ApiClient` ② DELETE 端点改为物理删除 |
| `src/cyberpulse/api/routers/items.py` | 修改 | 移除 `full_fetch_attempted`, `full_fetch_succeeded` 字段赋值 |
| `src/cyberpulse/api/auth.py` | 修改 | 删除 `revoke_client()` 方法 |
| `src/cyberpulse/scheduler/jobs.py` | 修改 | ① 导入 `secrets`, `Job`, `JobStatus`, `JobType`, `JobTrigger` ② 创建 job |
| `src/cyberpulse/api/routers/clients.py` | 删除 | 未使用的遗留文件 |
| `src/cyberpulse/api/routers/__init__.py` | 修改 | 移除 `clients` 导入（遗留文件清理） |
| `scripts/build-deploy-package.sh` | 修改 | 从部署包移除 `sources.yaml`，改为空示例文件 |
| `alembic/versions/xxx_add_job_trigger_field.py` | 新增 | 数据库迁移 |
| `tests/test_scheduler/test_scheduler.py` | 修改 | 更新测试 |

## 导入安全性分析

### 依赖图

```
config.py (settings)
    │
    ├──→ database.py (SessionLocal, Base)
    │        │
    │        └──→ models/ (Job, Source, etc.)
    │
    └──→ tasks/worker.py (broker = RedisBroker(url=settings.dramatiq_broker_url))
              │
              └──→ tasks/ingestion_tasks.py (@dramatiq.actor ingest_source)
                        │
                        └──→ scheduler/jobs.py (ingest_source.send())
```

### 验证结果

| 检查项 | 结果 |
|--------|------|
| `ingest_source` 导入前 broker 已配置 | ✅ `ingestion_tasks.py:21` 有 `from .worker import broker` |
| models 不依赖 broker | ✅ models 仅依赖 `database.Base` |
| 无循环依赖 | ✅ scheduler → tasks → worker，单向依赖 |
| 新增导入安全 | ✅ `secrets` 标准库无副作用，`JobTrigger` 纯枚举 |

### 各文件导入安全性检查

| 文件 | 新增导入 | 安全性 |
|------|----------|--------|
| `models/job.py` | `JobTrigger(StrEnum)` | ✅ 纯枚举，无依赖 |
| `models/__init__.py` | 导出 `JobTrigger` | ✅ 无副作用 |
| `admin/jobs.py` | `JobTrigger` | ✅ 从 models 导入，已验证安全 |
| `admin/sources.py` | `JobTrigger` | ✅ 已有 Job, secrets，仅新增枚举 |
| `admin/clients.py` | `delete`, `ApiClient` | ✅ `delete` 是 sqlalchemy 函数，`ApiClient` 是模型 |
| `scheduler/jobs.py` | `secrets`, `Job`, `JobStatus`, `JobType`, `JobTrigger` | ✅ 均无 broker 依赖 |

## 测试计划

### 单元测试

1. **Client 物理删除**
   - 删除存在的 client，验证数据库记录被删除
   - 删除不存在的 client，验证返回 404

2. **Job trigger 字段**
   - 手动创建 job，验证 trigger="manual"
   - 创建源触发 job，验证 trigger="create"
   - Scheduler 触发 job，验证 trigger="scheduler"

3. **Items API 字段移除**
   - 验证 `/api/v1/items` 响应不包含 `full_fetch_attempted`
   - 验证 `/api/v1/items` 响应不包含 `full_fetch_succeeded`

### 集成测试

1. **完整采集流程追踪**
   - 创建源 → 验证 job 记录创建 → 验证采集结果

2. **定时采集追踪**
   - 触发 scheduler → 验证 job 记录创建 → 验证 `jobs list` 可见

3. **部署包验证**
   - 构建部署包 → 验证不包含 `sources.yaml`（仅有空示例）
   - 验证 `sources.yaml` 为空配置文件