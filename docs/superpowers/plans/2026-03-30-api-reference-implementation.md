# API 参考手册实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编写两份 API 参考手册：管理 API 文档和业务 API 文档

**Architecture:** 基于设计文档结构，从代码和 schema 文件提取准确信息，编写完整的参考文档

**Tech Stack:** Markdown, Python (FastAPI), Bash

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `docs/admin-api-reference.md` | Create | 管理 API 参考手册 |
| `docs/business-api-reference.md` | Create | 业务 API 参考手册 |

---

## 参考源文件

**Schemas（响应字段）：**
- `src/cyberpulse/api/schemas/item.py`
- `src/cyberpulse/api/schemas/source.py`
- `src/cyberpulse/api/schemas/job.py`
- `src/cyberpulse/api/schemas/client.py`
- `src/cyberpulse/api/schemas/diagnose.py`
- `src/cyberpulse/api/schemas/log.py`

**Routers（端点参数和错误码）：**
- `src/cyberpulse/api/routers/admin/sources.py`
- `src/cyberpulse/api/routers/admin/jobs.py`
- `src/cyberpulse/api/routers/admin/clients.py`
- `src/cyberpulse/api/routers/admin/logs.py`
- `src/cyberpulse/api/routers/admin/diagnose.py`
- `src/cyberpulse/api/routers/items.py`

**脚本（api.sh 命令）：**
- `scripts/api.sh`

---

## Task 1: 创建管理 API 文档框架

**Files:**
- Create: `docs/admin-api-reference.md`

- [ ] **Step 1: 创建文档框架**

创建 `docs/admin-api-reference.md` 文件，包含以下框架内容：

```markdown
# 管理 API 参考手册

## Overview

### 定位

管理 API 供运维人员管理 cyber-pulse 系统，包括：

- 情报源管理（添加、配置、调度）
- 任务管理（触发采集、监控状态）
- 客户端管理（API Key 管理）
- 系统监控（日志、诊断）

### 版本信息

- API 版本：v1
- 服务版本：见 `/health` 端点返回

### 基础 URL

```
http://localhost:8000/api/v1/admin
```

## Authentication

### Admin API Key 获取

Admin API Key 在首次部署时自动生成。如需重置或重新获取，请参考：
- [运维者部署指南 - 获取 Admin API Key](./ops-deployment-guide.md#获取-admin-api-key)

### API Key 格式

```
cp_live_{32_hex_chars}
```

示例：`cp_live_a1b2c3d4e5f6789012345678abcdef01`

### 认证方式

所有管理 API 请求需在 Header 中携带 Bearer Token：

```
Authorization: Bearer cp_live_xxx
```

### 权限类型

| 权限 | 说明 | 适用范围 |
|------|------|----------|
| `admin` | 管理员权限 | 管理 API 所有端点 |
| `read` | 只读权限 | 业务 API（/api/v1/items） |

### 客户端管理

运维人员可通过 Clients API 管理客户端，详见 [Clients Management](#clients-management) 章节。

常用操作：
- 创建客户端：为下游应用创建业务 API Key
- 密钥轮换：定期更换 API Key
- 挂起/撤销：控制客户端访问权限

## Common Concepts

### ID 格式

| 类型 | 格式 | 示例 |
|------|------|------|
| source_id | `src_{8位hex}` | `src_a1b2c3d4` |
| job_id | `job_{16位hex}` | `job_a1b2c3d4e5f67890` |
| client_id | `cli_{16位hex}` | `cli_a1b2c3d4e5f67890` |

### 时间格式

所有时间字段使用 ISO 8601 格式（UTC 时区）：

```
2026-03-30T10:00:00Z
```

## Endpoints

<!-- 端点内容将在后续任务中填充 -->

## Error Responses

### 通用错误码

| 状态码 | 说明 | 常见原因 |
|--------|------|----------|
| 400 | Bad Request | 参数格式错误、ID 格式无效 |
| 401 | Unauthorized | API Key 无效或已过期 |
| 403 | Forbidden | 权限不足（需要 admin 权限） |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如名称重复） |
| 422 | Unprocessable Entity | 参数验证失败 |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | 服务不可用 |

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```
```

---

## Task 2: 编写 Sources Management 端点文档

**Files:**
- Modify: `docs/admin-api-reference.md`

**参考 Schema 文件:** `src/cyberpulse/api/schemas/source.py`

> **响应示例来源**: 每个响应示例使用 schema 文件中 `model_config["json_schema_extra"]["example"]` 的内容。

- [ ] **Step 1: 添加 Sources Management 章节**

在 `## Endpoints` 下添加 Sources Management 章节。响应示例从 schema 文件的 example 字段提取。

内容包括：

1. **GET /api/v1/admin/sources** - 列出情报源
   - 参数表格：status, tier, scheduled
   - api.sh: `./scripts/api.sh sources list [--status STATUS] [--tier TIER] [--scheduled BOOL]`
   - curl 示例
   - 完整响应示例（使用 SourceListResponse.model_config example）
   - 错误：401/403/422

2. **POST /api/v1/admin/sources** - 创建情报源
   - 请求体参数：name, connector_type, tier, score, config
   - api.sh: `./scripts/api.sh sources create --name NAME --type TYPE --url URL [--tier TIER]`
   - curl 示例
   - 完整响应示例（使用 SourceResponse.model_config example）:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "name": "Security Weekly RSS",
     "connector_type": "rss",
     "tier": "T1",
     "score": 70.0,
     "status": "ACTIVE",
     "pending_review": false,
     "review_reason": null,
     "config": {
       "feed_url": "https://example.com/feed.xml"
     },
     "last_scored_at": "2026-03-19T12:00:00Z",
     "total_items": 150,
     "schedule_interval": 3600,
     "next_ingest_at": "2026-03-19T11:00:00Z",
     "last_ingested_at": "2026-03-19T10:00:00Z",
     "last_ingest_result": "success",
     "items_last_7d": 25,
     "consecutive_failures": 0,
     "last_error_at": null,
     "last_error_message": null,
     "last_job_id": null,
     "needs_full_fetch": true,
     "full_fetch_threshold": 0.7,
     "content_type": "summary",
     "avg_content_length": 150,
     "quality_score": 75.0,
     "full_fetch_success_count": 10,
     "full_fetch_failure_count": 2,
     "warnings": [],
     "created_at": "2026-03-19T08:00:00Z",
     "updated_at": "2026-03-19T12:00:00Z"
   }
   ```
   - 错误：401/403/409/422

3. **GET /api/v1/admin/sources/{source_id}** - 查看详情
   - api.sh: `./scripts/api.sh sources get <source_id>`
   - curl 示例
   - 完整响应示例（同上 SourceResponse）
   - 错误：400/401/403/404

4. **PUT /api/v1/admin/sources/{source_id}** - 更新情报源
   - 请求体参数：name, tier, score, status, config, schedule_interval
   - api.sh: `./scripts/api.sh sources update <source_id> [options]`
   - curl 示例
   - 完整响应示例（SourceResponse）
   - 错误：400/401/403/404/422

5. **DELETE /api/v1/admin/sources/{source_id}** - 删除情报源（软删除）
   - api.sh: `./scripts/api.sh sources delete <source_id>`
   - curl 示例
   - 响应示例：
   ```json
   {
     "message": "Source src_a1b2c3d4 deleted"
   }
   ```
   - 错误：400/401/403/404

6. **POST /api/v1/admin/sources/{source_id}/test** - 测试连接
   - api.sh: `./scripts/api.sh sources test <source_id>`
   - curl 示例
   - 成功响应示例（TestResult）:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "test_result": "success",
     "response_time_ms": 250,
     "items_found": 25,
     "last_modified": null,
     "error_type": null,
     "error_message": null,
     "suggestion": null,
     "warnings": []
   }
   ```
   - 失败响应示例:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "test_result": "failed",
     "response_time_ms": null,
     "items_found": null,
     "last_modified": null,
     "error_type": "connection",
     "error_message": "Connection timeout after 30s",
     "suggestion": "检查网络连接或源服务器状态",
     "warnings": []
   }
   ```
   - 错误：400/401/403/404

7. **POST /api/v1/admin/sources/{source_id}/validate** - 验证质量
   - api.sh: `./scripts/api.sh sources validate <source_id>`
   - curl 示例
   - 完整响应示例（ValidationResponse）:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "is_valid": true,
     "content_type": "article",
     "sample_completeness": 0.85,
     "avg_content_length": 1250,
     "rejection_reason": null,
     "samples_analyzed": 5
   }
   ```
   - 错误：400/401/403/404

8. **POST /api/v1/admin/sources/{source_id}/schedule** - 设置调度
   - 请求体参数：interval（最小 300 秒）
   - api.sh: `./scripts/api.sh sources schedule <source_id> --interval SECONDS`
   - curl 示例
   - 完整响应示例（ScheduleResponse）:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "schedule_interval": 3600,
     "next_ingest_at": "2026-03-30T11:00:00Z",
     "message": "Schedule updated"
   }
   ```
   - 错误：400/401/403/404/422

9. **DELETE /api/v1/admin/sources/{source_id}/schedule** - 取消调度
   - api.sh: `./scripts/api.sh sources unschedule <source_id>`
   - curl 示例
   - 响应示例:
   ```json
   {
     "source_id": "src_a1b2c3d4",
     "schedule_interval": null,
     "next_ingest_at": null,
     "message": "Schedule removed"
   }
   ```
   - 错误：400/401/403/404

10. **GET /api/v1/admin/sources/defaults** - 获取默认配置
    - curl 示例
    - 响应示例（DefaultsResponse）:
    ```json
    {
      "default_fetch_interval": 3600,
      "updated_at": "2026-03-19T08:00:00Z"
    }
    ```
    - 错误：401/403

11. **PATCH /api/v1/admin/sources/defaults** - 更新默认配置
    - 请求体参数：default_fetch_interval
    - curl 示例
    - 响应示例（DefaultsResponse）
    - 错误：401/403/422

12. **POST /api/v1/admin/sources/import** - 批量导入（OPML）
    - FormData 参数：file, force, skip_invalid
    - api.sh: `./scripts/api.sh sources import --file FILE.opml [--skip-invalid]`
    - curl 示例
    - 完整响应示例（ImportResponse）:
    ```json
    {
      "job_id": "job_a1b2c3d4e5f67890",
      "status": "pending",
      "message": "Import job created with 25 feeds. Check status at /api/v1/admin/jobs/job_a1b2c3d4e5f67890"
    }
    ```
    - 错误：400/401/403/500

13. **GET /api/v1/admin/sources/export** - 导出（OPML）
    - 参数：status, tier
    - curl 示例
    - 响应（OPML XML）:
    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <opml version="2.0">
      <head>
        <title>CyberPulse Sources Export</title>
        <dateCreated>2026-03-30T10:00:00Z</dateCreated>
      </head>
      <body>
        <outline type="rss" title="Security Weekly" text="Security Weekly" xmlUrl="https://example.com/feed.xml" htmlUrl="https://example.com"/>
      </body>
    </opml>
    ```
    - 错误：401/403/422

14. **POST /api/v1/admin/sources/cleanup** - 清理已删除源
    - api.sh: `./scripts/api.sh sources cleanup`
    - curl 示例
    - 完整响应示例（SourceCleanupResponse）:
    ```json
    {
      "deleted_sources": 5,
      "deleted_items": 150,
      "deleted_jobs": 20,
      "message": "REMOVED sources cleaned up successfully"
    }
    ```
    - 错误：401/403

---

## Task 3: 编写 Jobs Management 端点文档

**Files:**
- Modify: `docs/admin-api-reference.md`

- [ ] **Step 1: 添加 Jobs Management 章节**

从 `src/cyberpulse/api/schemas/job.py` 和 `src/cyberpulse/api/routers/admin/jobs.py` 提取信息。

内容包括：

1. **GET /api/v1/admin/jobs** - 列出任务
   - 参数表格：type, status, source_id, since, limit
   - api.sh: `./scripts/api.sh jobs list [--type TYPE] [--status STATUS] [--source SOURCE_ID]`
   - curl 示例
   - 完整响应示例（JobListResponse）
   - 错误：401/403/422

2. **POST /api/v1/admin/jobs** - 创建采集任务
   - 请求体参数：source_id
   - api.sh: `./scripts/api.sh jobs run <source_id>`
   - curl 示例
   - 完整响应示例（JobCreatedResponse）
   - 错误：401/403/404/422

3. **GET /api/v1/admin/jobs/{job_id}** - 查看任务详情
   - api.sh: `./scripts/api.sh jobs get <job_id>`
   - curl 示例
   - 完整响应示例（JobResponse）
   - 错误：400/401/403/404

4. **DELETE /api/v1/admin/jobs/{job_id}** - 删除失败任务
   - api.sh: `./scripts/api.sh jobs delete <job_id>`
   - curl 示例
   - 响应示例（JobDeleteResponse）
   - 错误：400/401/403/404

5. **POST /api/v1/admin/jobs/{job_id}/retry** - 重试失败任务
   - api.sh: `./scripts/api.sh jobs retry <job_id>`
   - curl 示例
   - 完整响应示例（JobRetryResponse）
   - 错误：400/401/403/404

6. **POST /api/v1/admin/jobs/cleanup** - 清理历史任务
   - 参数：days, status
   - api.sh: `./scripts/api.sh jobs cleanup [--days 30]`
   - curl 示例
   - 完整响应示例（JobCleanupResponse）
   - 错误：401/403/422

---

## Task 4: 编写 Clients Management 端点文档

**Files:**
- Modify: `docs/admin-api-reference.md`

- [ ] **Step 1: 添加 Clients Management 章节**

从 `src/cyberpulse/api/schemas/client.py` 和 `src/cyberpulse/api/routers/admin/clients.py` 提取信息。

内容包括：

1. **GET /api/v1/admin/clients** - 列出客户端
   - 参数：status
   - api.sh: `./scripts/api.sh clients list [--status STATUS]`
   - curl 示例
   - 完整响应示例（ClientListResponse）
   - 错误：401/403/422

2. **POST /api/v1/admin/clients** - 创建客户端
   - 请求体参数：name, permissions, description, expires_at
   - api.sh: `./scripts/api.sh clients create --name NAME [--permissions PERMS] [--description DESC]`
   - curl 示例
   - 完整响应示例（ClientCreatedResponse，包含 api_key 和警告）
   - 错误：401/403/422

3. **GET /api/v1/admin/clients/{client_id}** - 查看详情
   - api.sh: `./scripts/api.sh clients get <client_id>`
   - curl 示例
   - 完整响应示例（ClientResponse）
   - 错误：400/401/403/404

4. **POST /api/v1/admin/clients/{client_id}/rotate** - 轮换密钥
   - api.sh: `./scripts/api.sh clients rotate <client_id>`
   - curl 示例
   - 完整响应示例（包含新 api_key）
   - 错误：400/401/403/404

5. **POST /api/v1/admin/clients/{client_id}/suspend** - 挂起客户端
   - api.sh: `./scripts/api.sh clients suspend <client_id>`
   - curl 示例
   - 完整响应示例
   - 错误：400/401/403/404

6. **POST /api/v1/admin/clients/{client_id}/activate** - 激活客户端
   - api.sh: `./scripts/api.sh clients activate <client_id>`
   - curl 示例
   - 完整响应示例
   - 错误：400/401/403/404

7. **DELETE /api/v1/admin/clients/{client_id}** - 撤销客户端
   - api.sh: `./scripts/api.sh clients delete <client_id>`
   - curl 示例
   - 响应示例
   - 错误：400/401/403/404

---

## Task 5: 编写 Logs & Diagnose 端点文档

**Files:**
- Modify: `docs/admin-api-reference.md`

- [ ] **Step 1: 添加 Logs & Diagnose 章节**

从 `src/cyberpulse/api/schemas/log.py`、`src/cyberpulse/api/schemas/diagnose.py` 和对应路由文件提取信息。

内容包括：

1. **GET /api/v1/admin/logs** - 查询系统日志
   - 参数表格：level, source_id, since, limit
   - curl 示例
   - 完整响应示例（LogListResponse）
   - 错误：401/403/422/500

2. **GET /api/v1/admin/diagnose** - 系统诊断概览
   - curl 示例
   - 完整响应示例（DiagnoseResponse，包含 statistics 子对象）
   - 错误：401/403

---

## Task 6: 创建业务 API 文档

**Files:**
- Create: `docs/business-api-reference.md`

- [ ] **Step 1: 创建完整业务 API 文档**

创建 `docs/business-api-reference.md` 文件，包含以下内容：

```markdown
# 业务 API 参考手册

## Overview

### 定位

业务 API 供下游应用获取已处理的情报数据。特性：

- Pull 模式：下游主动拉取数据
- Cursor 分页：支持增量同步
- At-least-once：需下游实现幂等处理

### 数据流

```
Source → cyber-pulse → 业务 API → 下游系统
```

### 版本信息

- API 版本：v1
- 服务版本：见 `/health` 端点返回

### 基础 URL

```
http://localhost:8000/api/v1
```

## Authentication

### API Key 获取

业务 API Key 由运维人员通过管理 API 创建。创建示例：

```bash
curl -X POST "http://localhost:8000/api/v1/admin/clients" \
  -H "Authorization: Bearer <admin_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "下游应用名称",
    "permissions": ["read"]
  }'
```

> 注意：需要 admin 权限的客户端才能创建新客户端。

### API Key 格式

```
cp_live_{32_hex_chars}
```

示例：`cp_live_a1b2c3d4e5f6789012345678abcdef01`

### 认证方式

所有业务 API 请求需在 Header 中携带 Bearer Token：

```
Authorization: Bearer cp_live_xxx
```

### 权限要求

业务 API 需要 `read` 权限，仅能访问 `/api/v1/items` 端点。

## Pagination & Filtering

### 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cursor | string | - | 游标位置，格式 `item_{8位hex}` |
| from | string | `latest` | 起始方向：`latest` 或 `beginning` |
| limit | int | 50 | 每页数量，范围 1-100 |

### 时间过滤参数

| 参数 | 类型 | 说明 |
|------|------|------|
| since | datetime | 发布时间起点（ISO 8601） |
| until | datetime | 发布时间终点（ISO 8601） |

### 获取方式示例

#### 方式一：获取最新数据（默认）

适用场景：首次获取、查看最新情报

**TypeScript:**
```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/items?limit=50",
  {
    headers: { Authorization: "Bearer cp_live_xxx" },
  }
);
const data = await response.json();
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

#### 方式二：增量同步（使用 cursor）

适用场景：持续同步、断点续传

**TypeScript:**
```typescript
const response = await fetch(
  `http://localhost:8000/api/v1/items?cursor=${lastCursor}&limit=50`,
  {
    headers: { Authorization: "Bearer cp_live_xxx" },
  }
);
const data = await response.json();
// 保存 data.next_cursor 用于下次请求
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?cursor=item_abc12345&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

#### 方式三：从头遍历（from=beginning）

适用场景：全量同步、数据迁移

**TypeScript:**
```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/items?from=beginning&limit=50",
  {
    headers: { Authorization: "Bearer cp_live_xxx" },
  }
);
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?from=beginning&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

#### 方式四：按时间范围获取

适用场景：获取特定时间段数据

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?since=2026-03-01T00:00:00Z&until=2026-03-15T00:00:00Z&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

#### 方式五：时间范围 + 增量同步

适用场景：时间段内的分页获取

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?since=2026-03-01T00:00:00Z&cursor=item_abc12345&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

### 注意事项

- `cursor` 和 `from` 不能同时使用
- `cursor` 格式必须为 `item_{8位hex}`
- 时间过滤基于 `published_at` 字段

## Endpoints

### Items

#### GET /api/v1/items

获取情报列表。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| cursor | string | query | 否 | 游标位置 |
| since | datetime | query | 否 | 发布时间起点 |
| until | datetime | query | 否 | 发布时间终点 |
| from | string | query | 否 | 起始方向 |
| limit | int | query | 否 | 每页数量（1-100，默认 50） |

**响应示例：**
```json
{
  "data": [
    {
      "id": "item_a1b2c3d4",
      "title": "某APT组织近期攻击活动分析",
      "author": "安全研究员",
      "published_at": "2026-03-30T08:00:00Z",
      "body": "本文分析了某APT组织近期的攻击活动...",
      "url": "https://example.com/article/123",
      "completeness_score": 0.85,
      "tags": ["APT", "威胁情报", "攻击分析"],
      "word_count": 1500,
      "fetched_at": "2026-03-30T09:00:00Z",
      "source": {
        "source_id": "src_abc12345",
        "source_name": "Security Weekly",
        "source_url": "https://example.com/feed.xml",
        "source_tier": "T1",
        "source_score": 75.0
      },
      "full_fetch_attempted": true,
      "full_fetch_succeeded": true
    }
  ],
  "next_cursor": "item_b2c3d4e5",
  "has_more": true,
  "count": 1,
  "server_timestamp": "2026-03-30T10:00:00Z"
}
```

**响应字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| data | array | 情报列表 |
| next_cursor | string | 下一页游标（null 表示无更多数据） |
| has_more | boolean | 是否有更多数据 |
| count | int | 当前页数据数量 |
| server_timestamp | datetime | 服务器时间戳 |

**data 数组元素字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 情报唯一标识（item_{8位hex}） |
| title | string | 标题（已标准化） |
| author | string | 作者（可能为 null） |
| published_at | datetime | 发布时间（ISO 8601） |
| body | string | 正文内容（可能为 null） |
| url | string | 原文链接 |
| completeness_score | float | 完整度评分（0-1） |
| tags | array | 标签列表 |
| word_count | int | 正文字数 |
| fetched_at | datetime | 采集时间 |
| source | object | 来源信息 |
| full_fetch_attempted | boolean | 是否尝试了全文采集 |
| full_fetch_succeeded | boolean | 全文采集是否成功 |

**source 对象字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| source_id | string | 来源 ID（src_{8位hex}） |
| source_name | string | 来源名称 |
| source_url | string | 来源 URL |
| source_tier | string | 来源层级（T1/T2/T3） |
| source_score | float | 来源评分 |

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | cursor 和 from 同时使用，或 cursor 格式无效 |
| 401 | API Key 无效或权限不足 |
| 404 | cursor 指定的 item 不存在 |

### Health Check

#### GET /health

健康检查端点，无需认证。

**响应示例：**
```json
{
  "status": "healthy",
  "version": "1.6.0",
  "components": {
    "database": "healthy",
    "api": "healthy"
  }
}
```

## Error Responses

| 状态码 | 说明 |
|--------|------|
| 400 | Bad Request - 参数错误 |
| 401 | Unauthorized - API Key 无效 |
| 500 | Internal Server Error |
| 503 | Service Unavailable |
```

---

## Task 7: 验证文档完整性

**Files:**
- Test: `docs/admin-api-reference.md`
- Test: `docs/business-api-reference.md`

- [ ] **Step 1: 验证文档格式正确**

```bash
# 检查文档是否存在
ls -la docs/admin-api-reference.md docs/business-api-reference.md
```

- [ ] **Step 2: 验证链接正确**

```bash
# 检查交叉引用链接
grep -o '\[.*\](.*\.md.*)' docs/admin-api-reference.md
grep -o '\[.*\](.*\.md.*)' docs/business-api-reference.md
```

- [ ] **Step 3: 验证 API 端点数量**

管理 API 文档应包含：
- Sources: 14 个端点
- Jobs: 6 个端点
- Clients: 7 个端点
- Logs & Diagnose: 2 个端点

业务 API 文档应包含：
- Items: 1 个端点
- Health: 1 个端点

---

## Task 8: 提交文档

**Files:**
- Commit: `docs/admin-api-reference.md`
- Commit: `docs/business-api-reference.md`

- [ ] **Step 1: 提交文档**

```bash
git add docs/admin-api-reference.md docs/business-api-reference.md
git commit -m "$(cat <<'EOF'
docs: add API reference documentation

- Add admin-api-reference.md for operations team
- Add business-api-reference.md for downstream developers
- Cover all endpoints with examples and error codes

EOF
)"
```

---

## 自审清单

- [ ] **Spec coverage:** 所有设计文档要求的端点都已覆盖
- [ ] **Placeholder scan:** 无 TBD/TODO
- [ ] **Type consistency:** 响应字段与 schema 文件一致
- [ ] **示例完整性:** 每个端点都有 api.sh/curl 示例和响应示例
- [ ] **错误码完整性:** 每个端点都列出可能的错误码