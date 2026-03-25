# Design: API 整体设计

**Date**: 2026-03-25
**Status**: Approved

---

## 概述

本文档定义 cyber-pulse 系统的完整 API 架构，包括业务 API 和管理 API。

**设计原则**：
- 统一通过 API 管理，废弃 CLI
- 权限分级：业务 API（read）vs 管理 API（admin）
- 容器环境友好，支持远程管理

---

## 配置管理

### 配置分工

| 类别 | 配置项 | 设置方式 | API 可管理 |
|------|--------|---------|-----------|
| **基础设施** | `database_url`, `redis_url`, `dramatiq_broker_url` | 环境变量 | ❌ |
| **服务绑定** | `api_host`, `api_port` | 环境变量 | ❌ |
| **安全** | `secret_key` | 环境变量 | ❌ |
| **环境** | `environment` | 环境变量 | ❌ |
| **业务默认值** | `default_fetch_interval` | API（`/sources/defaults`） | ✅ |

### 说明

**环境变量（部署时设置）**：
- 通过 `.env` 文件或容器环境变量配置
- 修改后需重启服务
- 不提供 API 管理

**API 运行时管理**：
- 业务相关的默认配置
- 存储在数据库 `settings` 表
- 修改后立即生效，无需重启

---

## API 架构总览

```
/api/v1/
│
├── /items                       # 业务 API（read 权限）
│   └── GET /                    # 拉取情报
│
└── /admin                       # 管理 API（admin 权限）
    ├── /diagnose                # 系统状态总览
    ├── /sources                 # 情报源管理
    ├── /jobs                    # 任务管理
    ├── /clients                 # 客户端管理
    └── /logs                    # 日志管理
```

---

## 权限模型

| 权限 | 可访问 API | 用户 |
|------|-----------|------|
| `read` | 业务 API（Items） | 下游情报分析系统 |
| `admin` | 管理 API | 系统管理员 |

**认证方式**：所有 API 请求需要在请求头中包含 API Key：

```
Authorization: Bearer cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 认证实现

**验证方式**：FastAPI Dependency 注入

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Client:
    api_key = credentials.credentials
    client = await validate_api_key(api_key)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key"
        )
    return client
```

**权限检查**：路由级别装饰器

```python
def require_permission(permission: str):
    async def checker(client: Client = Depends(get_current_client)):
        if permission not in client.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )
        return client
    return Depends(checker)
```

**认证错误响应**：

| 状态码 | 场景 | 响应 |
|--------|------|------|
| 401 | API Key 无效/过期 | `{"detail": "Invalid or expired API key"}` |
| 403 | 权限不足 | `{"detail": "Permission 'admin' required"}` |

---

## 业务 API

### Items API

**端点**：`GET /api/v1/items`

**权限**：read

**用途**：下游情报分析系统拉取情报数据

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cursor` | string | - | 增量游标（item_id） |
| `since` | datetime | - | 时间范围起始（published_at >= since） |
| `until` | datetime | - | 时间范围结束（published_at < until） |
| `from` | string | `latest` | 起始位置：`latest` 或 `beginning` |
| `limit` | int | 50 | 每页数量，最大 100 |

**参数互斥规则**：
- `cursor` 与 `from` 互斥，同时提供返回 400 错误
- `cursor` 与时间范围参数（`since`/`until`）可组合使用

#### 游标格式与校验

**格式**：`item_{YYYYMMDDHHMMSS}_{uuid8}`

**正则**：`^item_\d{14}_[a-f0-9]{8}$`

**校验逻辑**：
- 有效游标：正常查询
- 无效游标：返回 400 错误

```json
{
  "detail": "Invalid cursor format: invalid_cursor"
}
```

#### 拉取模式

| 模式 | 参数 | 行为 |
|------|------|------|
| 首次拉取 | 无参数 / `from=latest` | 返回最近 N 条（默认） |
| 增量拉取 | `cursor={item_id}` | 从指定位置继续 |
| 时间范围拉取 | `since` / `since` + `until` | 按 published_at 筛选 |
| 全量拉取 | `from=beginning` | 从最早开始 |

#### 响应字段

**Item 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 情报唯一标识（item_id） |
| `title` | string | 标题 |
| `author` | string | 作者（可能为空） |
| `published_at` | datetime | 原始发布时间 |
| `body` | string | 正文（Markdown 格式） |
| `url` | string | 原始文章链接 |
| `completeness_score` | float | 内容完整性评分 (0-1) |
| `tags` | string[] | 标签列表（可能为空） |
| `fetched_at` | datetime | 采集时间 |
| `source` | object | 情报源信息（嵌套对象） |

**嵌套 source 对象字段**：

| 字段 | 说明 | 对应 Source API 字段 |
|------|------|---------------------|
| `source_id` | 来源 ID | `source_id` |
| `source_name` | 来源名称 | `name` |
| `source_url` | RSS URL | `config.feed_url` |
| `source_tier` | 来源等级 | `tier` |
| `source_score` | 质量评分 | `score` |

**命名约定**：嵌套对象使用 `source_` 前缀，避免与外层字段冲突。

#### 响应示例

```json
{
  "data": [
    {
      "id": "item_20260325143052_a1b2c3d4",
      "title": "Critical Vulnerability Discovered",
      "author": "Security Research Team",
      "published_at": "2026-03-25T10:00:00Z",
      "body": "A critical vulnerability has been discovered...",
      "url": "https://example.com/security/critical-vulnerability",
      "completeness_score": 0.85,
      "tags": ["vulnerability", "security"],
      "fetched_at": "2026-03-25T14:30:52Z",
      "source": {
        "source_id": "src_a1b2c3d4",
        "source_name": "Security Weekly",
        "source_url": "https://securityweekly.com/feed/",
        "source_tier": "T1",
        "source_score": 75.0
      }
    }
  ],
  "next_cursor": "item_20260325140000_xyz789",
  "has_more": true,
  "count": 1,
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

#### completeness_score 计算方式

**查询时计算**，不存储到数据库。基于 Item 已有的三个质量指标：

```
completeness_score = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
```

| 子指标 | 数据库字段 | 计算方式 | 权重 |
|--------|------------|---------|------|
| `meta_completeness` | `items.meta_completeness` | author、tags、published_at 是否存在 | 0.4 |
| `content_completeness` | `items.content_completeness` | 正文长度（≥500=1.0, ≥200=0.7, ≥50=0.4, <50=0.2） | 0.4 |
| `noise_ratio` | `items.noise_ratio` | HTML 标签和广告标记占比（取反） | 0.2 |

详细计算逻辑见 [RSS Content Quality Fix](./2026-03-25-rss-content-quality-fix-design.md)。

---

## 管理 API

### Source API

**基础路径**：`/api/v1/admin/sources`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 源列表 |
| `/` | POST | 单个添加 |
| `/{id}` | GET | 源详情 |
| `/{id}` | PUT | 更新源 |
| `/{id}` | DELETE | 删除源 |
| `/{id}/test` | POST | 测试连接 |
| `/{id}/schedule` | POST | 设置调度 |
| `/{id}/schedule` | DELETE | 取消调度 |
| `/import` | POST | 批量导入 |
| `/export` | GET | 导出源 |
| `/defaults` | GET | 获取默认配置 |
| `/defaults` | PATCH | 更新默认配置 |

#### 源列表

```
GET /api/v1/admin/sources?status=active&tier=T1
```

**查询参数**：

| 参数 | 说明 |
|------|------|
| `status` | 状态：`active`、`frozen`、`pending_review` |
| `tier` | 等级：`T0`、`T1`、`T2`、`T3` |
| `scheduled` | 是否已调度：`true`、`false` |

**说明**：返回全部匹配结果，不分页。单机版源数量有限（通常 < 200），无需分页。

**响应**：

```json
{
  "data": [
    {
      "source_id": "src_a1b2c3d4",
      "name": "Example Blog",
      "tier": "T1",
      "score": 75.0,
      "status": "active",
      "needs_full_fetch": true,
      "consecutive_failures": 0,
      "schedule_interval": 3600,
      "next_ingest_at": "2026-03-25T11:00:00Z",
      "last_ingested_at": "2026-03-25T10:00:00Z"
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

#### 源详情

```
GET /api/v1/admin/sources/{id}
```

**响应**：与单个添加响应格式相同（见下文）。

#### 测试连接

```
POST /api/v1/admin/sources/{id}/test
```

**响应**：

```json
{
  "source_id": "src_a1b2c3d4",
  "test_result": "success",
  "response_time_ms": 234,
  "items_found": 15,
  "last_modified": "2026-03-25T10:00:00Z",
  "warnings": []
}
```

**失败响应**：

```json
{
  "source_id": "src_a1b2c3d4",
  "test_result": "failed",
  "error_type": "connection",
  "error_message": "Connection timeout after 30s",
  "suggestion": "检查网络连接或增加超时时间"
}
```

#### 单个添加

```
POST /api/v1/admin/sources
{
  "url": "https://example.com",       # feed_url 或 site_url
  "name": "Example Blog",             # 可选，不填则自动检测
  "tier": "T1",                       # 可选，不填则自动建议
  "needs_full_fetch": true,           # 可选，不填则自动判断
  "force": false                      # 强制添加，跳过质量验证
}
```

**处理流程**：

```
1. URL 去重检测 ──→ 已存在则返回错误
2. RSS 自动发现（如果是 site_url）
3. 处理重定向，获取最终 feed_url
4. 自动检测源信息（name, tier, needs_full_fetch）
5. 质量验证 ──→ 不通过且 force=false 则返回错误
6. 创建源
```

**响应示例**：

```json
{
  "source_id": "src_a1b2c3d4",
  "name": "Example Blog",
  "config": { "feed_url": "https://new-domain.com/feed.xml" },
  "tier": "T1",
  "score": 75.0,
  "status": "active",
  "needs_full_fetch": true,
  "full_fetch_threshold": 0.7,
  "content_type": "summary",
  "avg_content_length": 150,
  "consecutive_failures": 0,
  "last_error_at": null,
  "schedule_interval": null,
  "next_ingest_at": null,
  "last_ingested_at": null,
  "warnings": [
    "URL permanently redirected: https://old-domain.com/feed.xml → https://new-domain.com/feed.xml"
  ],
  "created_at": "2026-03-25T10:00:00Z",
  "updated_at": "2026-03-25T10:00:00Z"
}
```

#### 批量导入

```
POST /api/v1/admin/sources/import
Content-Type: multipart/form-data

file: subscriptions.opml
force: false
skip_invalid: true
```

**响应**：

```json
{
  "job_id": "job_abc123",
  "status": "pending",
  "message": "Import job created, check status at /api/v1/admin/jobs/job_abc123"
}
```

**后续查看**：
- 任务状态：`GET /api/v1/admin/jobs/{job_id}`
- 导入的源：`GET /api/v1/admin/sources`

#### 调度设置

```
POST /api/v1/admin/sources/{id}/schedule
{
  "interval": 3600
}
```

**说明**：设置源采集间隔，调度信息存储在 Source 模型中。

**字段说明**：
- `interval`: 采集间隔秒数，最小 300（5分钟），无上限

**响应**：

```json
{
  "source_id": "src_a1b2c3d4",
  "schedule_interval": 3600,
  "next_ingest_at": "2026-03-25T11:00:00Z",
  "message": "Schedule updated"
}
```

**调度机制**：
- 设置 `schedule_interval` 后，系统自动计算 `next_ingest_at`
- Scheduler 进程定期扫描 `next_ingest_at` 到期的源
- 到期后创建 Job 并触发 Dramatiq 采集任务

```
DELETE /api/v1/admin/sources/{id}/schedule  # 取消调度
```

**响应**：

```json
{
  "source_id": "src_a1b2c3d4",
  "schedule_interval": null,
  "next_ingest_at": null,
  "message": "Schedule removed"
}
```

#### 默认配置

**用途**：管理新添加源的默认采集间隔。

```
GET /api/v1/admin/sources/defaults
```

**响应**：

```json
{
  "default_fetch_interval": 3600,
  "updated_at": "2026-03-25T10:00:00Z"
}
```

```
PATCH /api/v1/admin/sources/defaults
{
  "default_fetch_interval": 7200
}
```

**响应**：

```json
{
  "default_fetch_interval": 7200,
  "updated_at": "2026-03-25T15:00:00Z"
}
```

**说明**：
- `default_fetch_interval`：新添加源未指定 interval 时使用的默认值（秒）
- 最小值：300（5分钟）
- 修改默认值不影响已调度的源

---

### Job API

**基础路径**：`/api/v1/admin/jobs`

#### 任务管理架构

```
┌─────────────────────────────────────────────────────────────────┐
│  触发入口                                                        │
│                                                                  │
│  API 手动触发：                                                   │
│  - POST /admin/jobs (采集) → 创建 Job → Dramatiq 任务            │
│  - POST /admin/sources/import → 创建 Job → Dramatiq 任务         │
│                                                                  │
│  Scheduler 定时触发（独立进程）：                                  │
│  - 扫描 next_ingest_at 到期的源 → 创建 Job → Dramatiq 任务        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Dramatiq Worker                                                │
│  - 异步执行任务                                                  │
│  - 重试、失败处理                                                │
│  - 更新 Job 状态和结果                                           │
└─────────────────────────────────────────────────────────────────┘
```

**调度存储**：Source 模型字段（`schedule_interval`、`next_ingest_at`）

**执行追踪**：Job 模型

#### 任务类型

| 类型 | 说明 | 触发方式 |
|------|------|---------|
| `ingest` | 采集任务（单个源） | API 手动 / Scheduler 定时 |
| `import` | 导入任务（批量添加源） | API 手动 |

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 任务列表 |
| `/` | POST | 手动运行采集任务 |
| `/{id}` | GET | 任务详情 |

#### 任务列表

```
GET /api/v1/admin/jobs?type=ingest&status=failed&source_id=src_xxx&limit=50
```

**查询参数**：

| 参数 | 说明 |
|------|------|
| `type` | 任务类型：`ingest` 或 `import` |
| `status` | 状态：`pending`、`running`、`completed`、`failed` |
| `source_id` | 按 source 过滤（仅 ingest 类型） |
| `since` | 创建时间起始 |
| `limit` | 每页数量，默认 50 |

**响应**：

```json
{
  "data": [
    {
      "job_id": "job_abc123",
      "type": "ingest",
      "status": "completed",
      "source_id": "src_xxx",
      "source_name": "Example Blog",
      "created_at": "2026-03-25T10:00:00Z",
      "started_at": "2026-03-25T10:00:01Z",
      "completed_at": "2026-03-25T10:01:00Z",
      "duration_seconds": 59,
      "result": {
        "items_fetched": 15,
        "items_created": 12,
        "items_rejected": 3
      }
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

#### 手动运行采集

```
POST /api/v1/admin/jobs
{
  "source_id": "src_xxx"
}
```

**响应**：

```json
{
  "job_id": "job_xyz789",
  "type": "ingest",
  "status": "pending",
  "source_id": "src_xxx",
  "source_name": "Example Blog",
  "message": "Job created and queued"
}
```

#### 任务详情

```
GET /api/v1/admin/jobs/{id}
```

**ingest 类型响应**：

```json
{
  "job_id": "job_abc123",
  "type": "ingest",
  "status": "completed",
  "source_id": "src_xxx",
  "source_name": "Example Blog",
  "created_at": "2026-03-25T10:00:00Z",
  "started_at": "2026-03-25T10:00:01Z",
  "completed_at": "2026-03-25T10:01:00Z",
  "duration_seconds": 59,
  "retry_count": 0,
  "result": {
    "items_fetched": 15,
    "items_created": 12,
    "items_rejected": 3
  }
}
```

**ingest 类型失败响应**：

```json
{
  "job_id": "job_def456",
  "type": "ingest",
  "status": "failed",
  "source_id": "src_xxx",
  "source_name": "Example Blog",
  "created_at": "2026-03-25T10:00:00Z",
  "started_at": "2026-03-25T10:00:01Z",
  "completed_at": "2026-03-25T10:00:35Z",
  "retry_count": 3,
  "error": {
    "type": "connection_timeout",
    "message": "Connection timeout after 30s",
    "suggestion": "检查网络连接或增加超时时间"
  }
}
```

**import 类型响应**：

```json
{
  "job_id": "job_xyz789",
  "type": "import",
  "status": "completed",
  "file_name": "subscriptions.opml",
  "created_at": "2026-03-25T10:00:00Z",
  "started_at": "2026-03-25T10:00:01Z",
  "completed_at": "2026-03-25T10:05:00Z",
  "duration_seconds": 299,
  "result": {
    "total": 50,
    "imported": 42,
    "skipped": 5,
    "failed": 3
  },
  "failed_sources": [
    {
      "url": "https://low-quality.com/feed.xml",
      "reason": "Content completeness too low (0.25 < 0.4)"
    },
    {
      "url": "https://no-rss.com",
      "reason": "RSS feed not found"
    }
  ]
}
```

#### 任务状态值

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行（在队列中） |
| `running` | 执行中 |
| `completed` | 成功完成 |
| `failed` | 执行失败（重试耗尽） |

---

### Job 模型

**数据库表**：`jobs`

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | VARCHAR(64) | 主键，格式：`job_{uuid}` |
| `type` | VARCHAR(20) | 任务类型：`ingest` 或 `import` |
| `status` | VARCHAR(20) | 状态：`pending`、`running`、`completed`、`failed` |
| `source_id` | VARCHAR(64) | 关联源（ingest 类型），外键 |
| `file_name` | VARCHAR(255) | 导入文件名（import 类型） |
| `result` | JSONB | 执行结果 |
| `error_type` | VARCHAR(50) | 错误类型（失败时） |
| `error_message` | TEXT | 错误信息（失败时） |
| `retry_count` | INTEGER | 重试次数，默认 0 |
| `created_at` | TIMESTAMP | 创建时间 |
| `started_at` | TIMESTAMP | 开始执行时间 |
| `completed_at` | TIMESTAMP | 完成时间 |

**索引**：
- `type`, `status`, `source_id`, `created_at`

**清理策略**：

| 保留规则 | 说明 |
|---------|------|
| 30 天内 | 全部保留 |
| 30 天外 `completed` | 自动清理 |
| 30 天外 `failed` | 保留（便于复盘） |

**实现**：Scheduler 定时任务每天凌晨执行清理。

### Settings 模型

**数据库表**：`settings`

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | VARCHAR(64) | 主键 |
| `value` | TEXT | 配置值 |
| `updated_at` | TIMESTAMP | 更新时间 |

**初始化**：数据库迁移脚本写入默认值：

```sql
INSERT INTO settings (key, value, updated_at)
VALUES ('default_fetch_interval', '3600', NOW())
ON CONFLICT (key) DO NOTHING;
```

**初始数据**：

| key | value |
|-----|-------|
| `default_fetch_interval` | `3600` |

### Source 调度字段扩展

**新增字段**（存储在 Source 模型）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `schedule_interval` | INTEGER | 采集间隔秒数，null 表示未调度 |
| `next_ingest_at` | TIMESTAMP | 下次采集时间 |
| `last_ingested_at` | TIMESTAMP | 上次采集时间 |

---

### Client API

**基础路径**：`/api/v1/admin/clients`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 客户端列表 |
| `/` | POST | 创建客户端 |
| `/{id}` | GET | 客户端详情 |
| `/{id}` | PUT | 更新客户端 |
| `/{id}` | DELETE | 删除客户端 |
| `/{id}/rotate` | POST | 重新生成 API Key |

#### 客户端列表

```
GET /api/v1/admin/clients?limit=50
```

**响应**：

```json
{
  "data": [
    {
      "client_id": "cli_a1b2c3d4e5f6g7h8",
      "name": "分析系统",
      "description": "下游分析系统",
      "permissions": ["read"],
      "expires_at": "2026-12-31T23:59:59Z",
      "last_used_at": "2026-03-25T10:00:00Z",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

#### 创建客户端

```
POST /api/v1/admin/clients
{
  "name": "分析系统",
  "description": "下游分析系统",
  "permissions": ["read"],
  "expires_at": "2026-12-31T23:59:59Z"
}
```

**响应**：

```json
{
  "client_id": "cli_a1b2c3d4e5f6g7h8",
  "name": "分析系统",
  "description": "下游分析系统",
  "api_key": "cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "permissions": ["read"],
  "expires_at": "2026-12-31T23:59:59Z",
  "created_at": "2026-03-25T10:00:00Z"
}
```

**说明**：`api_key` 仅创建时返回一次，请妥善保存。

#### 更新客户端

```
PUT /api/v1/admin/clients/{id}
{
  "name": "分析系统 v2",
  "description": "更新后的描述",
  "expires_at": "2027-12-31T23:59:59Z"
}
```

**响应**：

```json
{
  "client_id": "cli_a1b2c3d4e5f6g7h8",
  "name": "分析系统 v2",
  "description": "更新后的描述",
  "permissions": ["read"],
  "expires_at": "2027-12-31T23:59:59Z",
  "created_at": "2026-03-25T10:00:00Z"
}
```

**说明**：不可修改 `permissions`。

#### 重新生成 API Key

```
POST /api/v1/admin/clients/{id}/rotate
```

**响应**：

```json
{
  "client_id": "cli_a1b2c3d4e5f6g7h8",
  "api_key": "cp_live_yyyyyyyyyyyyyyyyyyyyyyyyyyyy",
  "message": "API Key rotated, old key is now invalid"
}
```

**说明**：旧 API Key 立即失效，新 Key 仅返回一次。

#### 删除客户端

```
DELETE /api/v1/admin/clients/{id}
```

**响应**：

```json
{
  "message": "Client deleted"
}
```

**说明**：物理删除，API Key 立即失效。

---

### Log API

**基础路径**：`/api/v1/admin/logs`

**用途**：故障排查，查询错误日志定位问题。

#### 查询日志

```
GET /api/v1/admin/logs
```

**查询参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `level` | `error` | 日志级别：`error`、`warning`、`info` |
| `source_id` | - | 按源筛选 |
| `since` | - | 时间范围起始 |
| `limit` | 50 | 每页数量 |

**示例**：

```
GET /api/v1/admin/logs                                    # 最近错误日志（默认）
GET /api/v1/admin/logs?source_id=src_xxx&since=24h       # 指定源的错误日志
GET /api/v1/admin/logs?level=warning                     # 警告日志
```

**错误类型枚举**：

| error_type | 说明 |
|------------|------|
| `connection` | 网络连接错误 |
| `timeout` | 请求超时 |
| `http_403` | 访问被拒绝 |
| `http_404` | 资源不存在 |
| `http_429` | 请求频率限制 |
| `http_5xx` | 服务器错误 |
| `parse_error` | RSS 解析失败 |
| `ssl_error` | SSL 证书错误 |

**响应**：

```json
{
  "data": [
    {
      "timestamp": "2026-03-25T10:00:00Z",
      "level": "ERROR",
      "module": "connector.rss",
      "source_id": "src_xxx",
      "source_name": "Example Blog",
      "error_type": "connection",
      "message": "HTTP 403 Forbidden",
      "retry_count": 3,
      "suggestion": "检查网站反爬策略"
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

---

### Diagnose API

**基础路径**：`/api/v1/admin/diagnose`

**用途**：系统监控入口，快速了解系统运行状况。

#### 系统诊断

```
GET /api/v1/admin/diagnose
```

**响应**：

```json
{
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
      "by_type": {
        "connection": 120,
        "http_403": 80,
        "timeout": 50,
        "parse_error": 30
      },
      "top_sources": [
        { "source_id": "src_xxx", "source_name": "Example Blog", "error_count": 15 }
      ]
    }
  },
  "server_timestamp": "2026-03-25T15:00:00Z"
}
```

**status 取值**：
- `healthy` - 所有组件正常，近期无严重错误
- `degraded` - 部分组件异常或错误率偏高
- `unhealthy` - 关键组件异常

**使用场景**：
- 日常巡检入口
- 发现 `pending_review > 0` → 进入源健康检查流程
- 发现 `failed_24h` 偏高 → 进入故障排查流程

---

## 统一响应格式

### 成功响应

```json
// 列表
{
  "data": [...],
  "count": 50,
  "server_timestamp": "2026-03-25T15:00:00Z"
}

// 分页列表（带游标）
{
  "data": [...],
  "next_cursor": "item_20260325140000_xyz789",
  "has_more": true,
  "count": 50,
  "server_timestamp": "2026-03-25T15:00:00Z"
}

// 单条
{
  "source_id": "src_xxx",
  ...
}
```

### 错误响应

```json
{
  "detail": "错误描述",
  "code": "ERROR_CODE"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 请求格式错误 |
| 500 | 服务器内部错误 |

---

## 关联设计

- [API Unicode Encoding Fix](./2026-03-25-api-unicode-encoding-design.md)
- [API Fields Fix Design](./2026-03-25-api-fields-fix-design.md)
- [RSS Ingestion Error Fix](./2026-03-25-rss-ingestion-error-fix-design.md)
- [RSS Content Quality Fix](./2026-03-25-rss-content-quality-fix-design.md)

---

## 关联 Issue

- #39: API 中文 Unicode 转义
- #44: API 返回字段与文档描述不一致
- #47: API 参数/分页问题
- #42: Worker 大量 RSS 采集错误
- #41: RSS 采集内容不完整
- #46: 部分 RSS 源只提供标题链接
- #43: 缺少源健康状态监控 API