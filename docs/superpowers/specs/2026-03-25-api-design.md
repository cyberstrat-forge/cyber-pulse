# Design: API 整体设计

**Date**: 2026-03-25
**Status**: Draft

---

## 概述

本文档定义 cyber-pulse 系统的完整 API 架构，包括业务 API 和管理 API。

**设计原则**：
- 统一通过 API 管理，废弃 CLI
- 权限分级：业务 API（read）vs 管理 API（admin）
- 容器环境友好，支持远程管理

---

## API 架构总览

```
/api/v1/
│
├── /items                    # 业务 API（read 权限）
│   └── GET /                 # 拉取情报
│
├── /admin                    # 管理 API（admin 权限）
│   ├── /sources              # 情报源管理
│   ├── /jobs                 # 任务管理
│   ├── /clients              # 客户端管理
│   ├── /logs                 # 日志管理
│   └── /diagnose             # 诊断工具
│
└── /health                   # 健康检查（公开）
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
| `from` | string | - | 起始位置：`latest`（默认）或 `beginning` |
| `limit` | int | 50 | 每页数量，最大 100 |

#### 拉取模式

| 模式 | 参数 | 行为 |
|------|------|------|
| 首次拉取 | 无参数 / `from=latest` | 返回最近 N 条（默认） |
| 增量拉取 | `cursor={item_id}` | 从指定位置继续 |
| 时间范围拉取 | `since` / `since` + `until` | 按 published_at 筛选 |
| 全量拉取 | `from=beginning` | 从最早开始 |

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

---

## 管理 API

### Source API

**基础路径**：`/api/v1/admin/sources`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 源列表 |
| `/{id}` | GET | 源详情 |
| `/` | POST | 单个添加 |
| `/{id}` | PUT | 更新源 |
| `/{id}` | DELETE | 删除源 |
| `/{id}/test` | POST | 测试连接 |
| `/{id}/schedule` | POST | 设置调度 |
| `/{id}/schedule` | DELETE | 取消调度 |
| `/import` | POST | 批量导入 |
| `/export` | GET | 导出源 |

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
  "needs_full_fetch": true,
  "full_fetch_threshold": 0.7,
  "content_type": "summary",
  "warnings": [
    "URL permanently redirected: https://old-domain.com/feed.xml → https://new-domain.com/feed.xml"
  ],
  "created_at": "2026-03-25T10:00:00Z"
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
  "interval": 3600  # 间隔秒数，或使用 cron 表达式
}

DELETE /api/v1/admin/sources/{id}/schedule  # 取消调度
```

---

### Job API

**基础路径**：`/api/v1/admin/jobs`

**任务类型**：
- `ingest`：采集任务（单个源）
- `import`：导入任务（批量添加源）

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
      "completed_at": "2026-03-25T10:01:00Z",
      "result": {
        "items_fetched": 15,
        "items_created": 12,
        "items_rejected": 3
      }
    }
  ],
  "count": 1
}
```

#### 手动运行采集

```
POST /api/v1/admin/jobs
{
  "source_id": "src_xxx",
  "force": false
}
```

**响应**：

```json
{
  "job_id": "job_xyz789",
  "type": "ingest",
  "status": "pending",
  "source_id": "src_xxx",
  "message": "Job created"
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
  "completed_at": "2026-03-25T10:01:00Z",
  "retry_count": 0,
  "result": {
    "items_fetched": 15,
    "items_created": 12,
    "items_rejected": 3
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
  "completed_at": "2026-03-25T10:05:00Z",
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
| `pending` | 等待执行 |
| `running` | 执行中 |
| `completed` | 成功完成 |
| `failed` | 执行失败 |

---

### Client API

**基础路径**：`/api/v1/admin/clients`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 客户端列表 |
| `/` | POST | 创建客户端 |
| `/{id}/disable` | PUT | 禁用客户端 |
| `/{id}/enable` | PUT | 启用客户端 |
| `/{id}` | DELETE | 删除客户端 |

#### 创建客户端

```
POST /api/v1/admin/clients
{
  "name": "分析系统",
  "description": "下游分析系统",
  "permissions": ["read"],    # read 或 admin
  "expires_at": "2026-12-31T23:59:59Z"  # 可选
}
```

**响应**：

```json
{
  "client_id": "cli_a1b2c3d4e5f6g7h8",
  "name": "分析系统",
  "api_key": "cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  // 仅创建时返回
  "permissions": ["read"],
  "status": "active",
  "created_at": "2026-03-25T10:00:00Z"
}
```

---

### Log API

**基础路径**：`/api/v1/admin/logs`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 查询日志 |
| `/errors` | GET | 错误日志 |
| `/stats` | GET | 日志统计 |
| `/export` | GET | 导出日志 |

#### 查询日志

```
GET /api/v1/admin/logs?level=error&source=src_xxx&since=2026-03-25T00:00:00Z&limit=50
```

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
  "count": 1
}
```

#### 日志统计

```
GET /api/v1/admin/logs/stats?days=7
```

**响应**：

```json
{
  "total": 15420,
  "by_level": {
    "info": 14500,
    "warning": 620,
    "error": 280,
    "critical": 20
  },
  "by_module": {
    "connector.rss": 150,
    "tasks.ingestion": 80
  },
  "top_errors": [
    { "error_type": "connection", "count": 120, "message": "Connection timeout" },
    { "error_type": "http_403", "count": 80, "message": "Forbidden" }
  ]
}
```

---

### Diagnose API

**基础路径**：`/api/v1/admin/diagnose`

#### 端点列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/system` | GET | 系统诊断 |
| `/sources` | GET | 源诊断 |
| `/errors` | GET | 错误诊断 |

#### 系统诊断

```
GET /api/v1/admin/diagnose/system
```

**响应**：

```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "1.3.0",
  "scheduler": "active",
  "pending_jobs": 3,
  "recent_errors": 12
}
```

#### 源诊断

```
GET /api/v1/admin/diagnose/sources?pending=true&tier=T1
```

**响应**：

```json
{
  "summary": {
    "active": 120,
    "frozen": 15,
    "pending_review": 5
  },
  "pending_review": [
    {
      "source_id": "src_xxx",
      "source_name": "Example Blog",
      "review_reason": "连续采集失败: HTTP 403",
      "consecutive_failures": 5
    }
  ]
}
```

---

## 健康检查 API

**端点**：`GET /health`

**认证**：无需认证

**响应**：

```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "1.3.0"
}
```

---

## 统一响应格式

### 成功响应

```json
// 列表
{
  "data": [...],
  "count": 50
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