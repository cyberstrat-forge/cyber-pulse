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

### Sources Management

情报源管理端点，用于添加、配置、调度和监控情报源。

#### GET /api/v1/admin/sources

列出所有情报源，支持按状态、层级、调度状态过滤。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| status | string | query | 否 | 按状态过滤：ACTIVE, FROZEN, REMOVED |
| tier | string | query | 否 | 按层级过滤：T0, T1, T2, T3 |
| scheduled | boolean | query | 否 | 按调度状态过滤 |

**api.sh:**
```bash
./scripts/api.sh sources list [--status STATUS] [--tier TIER] [--scheduled BOOL]
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/sources" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "data": [
    {
      "source_id": "src_a1b2c3d4",
      "name": "Security Weekly RSS",
      "connector_type": "rss",
      "tier": "T1",
      "score": 70.0,
      "status": "ACTIVE",
      "pending_review": false,
      "review_reason": null,
      "config": {},
      "last_scored_at": null,
      "total_items": 0,
      "schedule_interval": 3600,
      "next_ingest_at": null,
      "last_ingested_at": null,
      "last_ingest_result": null,
      "items_last_7d": 0,
      "consecutive_failures": 0,
      "last_error_at": null,
      "last_error_message": null,
      "last_job_id": null,
      "needs_full_fetch": false,
      "full_fetch_threshold": null,
      "content_type": null,
      "avg_content_length": null,
      "quality_score": null,
      "full_fetch_success_count": 0,
      "full_fetch_failure_count": 0,
      "warnings": [],
      "created_at": "2026-03-19T08:00:00Z",
      "updated_at": "2026-03-19T08:00:00Z"
    }
  ],
  "count": 1,
  "offset": 0,
  "limit": 100,
  "server_timestamp": "2026-03-19T16:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足（需要 admin 权限） |
| 422 | 参数格式无效 |

---

#### POST /api/v1/admin/sources

创建新的情报源。创建时会自动触发初始采集任务。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 情报源名称（唯一） |
| connector_type | string | 是 | 连接器类型：rss, api, web_scraper, media_api |
| tier | string | 否 | 层级：T0, T1, T2, T3（默认 T2） |
| score | float | 否 | 质量评分 0-100（默认根据 tier 推导） |
| config | object | 否 | 连接器配置 |

**api.sh:**
```bash
./scripts/api.sh sources create --name "Security Weekly" --type rss --url "https://example.com/feed.xml" --tier T1
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Security Weekly RSS",
    "connector_type": "rss",
    "tier": "T1",
    "score": 70.0,
    "config": {
      "feed_url": "https://example.com/feed.xml"
    }
  }'
```

**响应示例：**
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

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足（需要 admin 权限） |
| 409 | 情报源名称已存在 |
| 422 | 参数验证失败 |

---

#### GET /api/v1/admin/sources/{source_id}

获取情报源详细信息。

**api.sh:**
```bash
./scripts/api.sh sources get src_a1b2c3d4
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：** 同 POST /sources 响应

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |

---

#### PUT /api/v1/admin/sources/{source_id}

更新情报源配置。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 情报源名称 |
| tier | string | 否 | 层级：T0, T1, T2, T3 |
| score | float | 否 | 质量评分 0-100 |
| status | string | 否 | 状态：ACTIVE, FROZEN, REMOVED |
| config | object | 否 | 连接器配置 |
| schedule_interval | int | 否 | 采集间隔（秒），最小 300 |
| pending_review | boolean | 否 | 是否待审核 |
| review_reason | string | 否 | 审核原因 |

**api.sh:**
```bash
./scripts/api.sh sources update src_a1b2c3d4 --tier T0 --score 85
```

**curl:**
```bash
curl -X PUT "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "tier": "T0",
    "score": 85.0
  }'
```

**响应示例：** 同 GET /sources/{source_id} 响应

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |
| 422 | 参数验证失败 |

---

#### DELETE /api/v1/admin/sources/{source_id}

删除情报源（软删除，设置状态为 REMOVED）。

**api.sh:**
```bash
./scripts/api.sh sources delete src_a1b2c3d4
```

**curl:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "message": "Source src_a1b2c3d4 deleted"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |

---

#### POST /api/v1/admin/sources/{source_id}/test

测试情报源连接性。对 RSS 源执行连接测试，返回响应时间和发现的条目数。

**api.sh:**
```bash
./scripts/api.sh sources test src_a1b2c3d4
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4/test" \
  -H "Authorization: Bearer cp_live_xxx"
```

**成功响应示例：**
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

**失败响应示例：**
```json
{
  "source_id": "src_a1b2c3d4",
  "test_result": "failed",
  "response_time_ms": null,
  "items_found": null,
  "last_modified": null,
  "error_type": "connection",
  "error_message": "Connection timeout after 30s",
  "suggestion": "检查网络连接或增加超时时间",
  "warnings": []
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |

---

#### POST /api/v1/admin/sources/{source_id}/validate

验证情报源质量。对 RSS 源执行质量验证，检查内容完整性。

**api.sh:**
```bash
./scripts/api.sh sources validate src_a1b2c3d4
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4/validate" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
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

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |

---

#### POST /api/v1/admin/sources/{source_id}/schedule

设置情报源采集调度。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| interval | int | 是 | 采集间隔（秒），最小 300（5分钟） |

**api.sh:**
```bash
./scripts/api.sh sources schedule src_a1b2c3d4 --interval 3600
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4/schedule" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"interval": 3600}'
```

**响应示例：**
```json
{
  "source_id": "src_a1b2c3d4",
  "schedule_interval": 3600,
  "next_ingest_at": "2026-03-30T11:00:00Z",
  "message": "Schedule updated"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |
| 422 | interval 小于 300 |

---

#### DELETE /api/v1/admin/sources/{source_id}/schedule

取消情报源采集调度。

**api.sh:**
```bash
./scripts/api.sh sources unschedule src_a1b2c3d4
```

**curl:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/admin/sources/src_a1b2c3d4/schedule" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "source_id": "src_a1b2c3d4",
  "schedule_interval": null,
  "next_ingest_at": null,
  "message": "Schedule removed"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | source_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |

---

#### GET /api/v1/admin/sources/defaults

获取源默认配置。

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/sources/defaults" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "default_fetch_interval": 3600,
  "updated_at": "2026-03-19T08:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |

---

#### PATCH /api/v1/admin/sources/defaults

更新源默认配置。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| default_fetch_interval | int | 是 | 默认采集间隔（秒），最小 300 |

**curl:**
```bash
curl -X PATCH "http://localhost:8000/api/v1/admin/sources/defaults" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"default_fetch_interval": 1800}'
```

**响应示例：** 同 GET /sources/defaults

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数验证失败 |

---

#### POST /api/v1/admin/sources/import

批量导入情报源（OPML 格式）。

**FormData 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | OPML 文件 |
| force | boolean | 否 | 跳过质量验证（默认 false） |
| skip_invalid | boolean | 否 | 跳过无效源继续导入（默认 true） |

**api.sh:**
```bash
./scripts/api.sh sources import --file feeds.opml [--skip-invalid]
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources/import" \
  -H "Authorization: Bearer cp_live_xxx" \
  -F "file=@feeds.opml" \
  -F "skip_invalid=true"
```

**响应示例：**
```json
{
  "job_id": "job_a1b2c3d4e5f67890",
  "status": "pending",
  "message": "Import job created with 25 feeds. Check status at /api/v1/admin/jobs/job_a1b2c3d4e5f67890"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | OPML 文件格式无效或无有效 RSS 源 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 500 | 导入任务创建失败 |

---

#### GET /api/v1/admin/sources/export

导出情报源为 OPML 格式。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| status | string | query | 否 | 按状态过滤：ACTIVE, FROZEN |
| tier | string | query | 否 | 按层级过滤：T0, T1, T2, T3 |

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/sources/export" \
  -H "Authorization: Bearer cp_live_xxx" \
  -o cyberpulse-sources.opml
```

**响应示例：**
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

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数格式无效 |

---

#### POST /api/v1/admin/sources/cleanup

清理已删除的情报源（物理删除）。删除所有状态为 REMOVED 的源及其关联的条目和任务。

**api.sh:**
```bash
./scripts/api.sh sources cleanup
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/sources/cleanup" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "deleted_sources": 5,
  "deleted_items": 150,
  "deleted_jobs": 20
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |

### Jobs Management

任务管理端点，用于创建采集任务、监控任务状态、重试失败任务和清理历史任务。

#### GET /api/v1/admin/jobs

列出任务，支持按类型、状态、源 ID 过滤。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| type | string | query | 否 | 按类型过滤：INGEST, IMPORT |
| status | string | query | 否 | 按状态过滤：PENDING, RUNNING, COMPLETED, FAILED |
| source_id | string | query | 否 | 按源 ID 过滤 |
| since | datetime | query | 否 | 创建时间起点（ISO 8601） |
| limit | int | query | 否 | 最大结果数（1-100，默认 50） |

**api.sh:**
```bash
./scripts/api.sh jobs list [--type TYPE] [--status STATUS] [--source SOURCE_ID]
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/jobs?status=FAILED&limit=20" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "data": [
    {
      "job_id": "job_a1b2c3d4e5f67890",
      "type": "INGEST",
      "status": "COMPLETED",
      "source_id": "src_abc12345",
      "source_name": "Security Weekly",
      "file_name": null,
      "result": {"items_ingested": 25},
      "error": null,
      "retry_count": 0,
      "created_at": "2026-03-30T10:00:00Z",
      "started_at": "2026-03-30T10:00:05Z",
      "completed_at": "2026-03-30T10:00:30Z",
      "duration_seconds": 25
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-30T12:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数格式无效 |

---

#### POST /api/v1/admin/jobs

创建采集任务。手动触发指定源的采集任务。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_id | string | 是 | 要采集的源 ID |

**api.sh:**
```bash
./scripts/api.sh jobs run src_abc12345
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/jobs" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{"source_id": "src_abc12345"}'
```

**响应示例：**
```json
{
  "job_id": "job_a1b2c3d4e5f67890",
  "type": "INGEST",
  "status": "PENDING",
  "source_id": "src_abc12345",
  "source_name": "Security Weekly",
  "message": "Job created and queued"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 情报源不存在 |
| 422 | 参数验证失败 |

---

#### GET /api/v1/admin/jobs/{job_id}

获取任务详情。

**api.sh:**
```bash
./scripts/api.sh jobs get job_a1b2c3d4e5f67890
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/jobs/job_a1b2c3d4e5f67890" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "job_id": "job_a1b2c3d4e5f67890",
  "type": "INGEST",
  "status": "FAILED",
  "source_id": "src_abc12345",
  "source_name": "Security Weekly",
  "file_name": null,
  "result": null,
  "error": {
    "type": "connection",
    "message": "Connection timeout after 30s"
  },
  "retry_count": 1,
  "created_at": "2026-03-30T10:00:00Z",
  "started_at": "2026-03-30T10:00:05Z",
  "completed_at": "2026-03-30T10:00:35Z",
  "duration_seconds": 30
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | job_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 任务不存在 |

---

#### DELETE /api/v1/admin/jobs/{job_id}

删除失败任务。只能删除状态为 FAILED 的任务。

**api.sh:**
```bash
./scripts/api.sh jobs delete job_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/admin/jobs/job_a1b2c3d4e5f67890" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "deleted": "job_a1b2c3d4e5f67890",
  "message": "Job deleted successfully"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | job_id 格式无效或任务状态不允许删除 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 任务不存在 |

---

#### POST /api/v1/admin/jobs/{job_id}/retry

重试失败任务。重置任务状态并重新执行。每个任务最多重试 3 次。

**api.sh:**
```bash
./scripts/api.sh jobs retry job_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/jobs/job_a1b2c3d4e5f67890/retry" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "job_id": "job_a1b2c3d4e5f67890",
  "status": "PENDING",
  "retry_count": 1,
  "message": "Job queued for retry"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | job_id 格式无效、任务状态不允许重试或已达到最大重试次数 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 任务不存在 |

---

#### POST /api/v1/admin/jobs/cleanup

清理历史任务。删除指定状态的旧任务。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| days | int | query | 否 | 保留天数阈值（默认 30） |
| status | string | query | 否 | 要清理的任务状态（默认 COMPLETED） |

**api.sh:**
```bash
./scripts/api.sh jobs cleanup [--days 30]
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/jobs/cleanup?days=30&status=COMPLETED" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "deleted_count": 50,
  "threshold_days": 30,
  "message": "Jobs cleaned up successfully"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数格式无效 |

### Clients Management

客户端管理端点，用于创建、管理 API Key，包括密钥轮换、挂起和撤销操作。

#### GET /api/v1/admin/clients

列出所有 API 客户端。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| status | string | query | 否 | 按状态过滤：ACTIVE, SUSPENDED, REVOKED |

**api.sh:**
```bash
./scripts/api.sh clients list [--status STATUS]
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/clients" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "data": [
    {
      "client_id": "cli_a1b2c3d4e5f67890",
      "name": "Analytics Service",
      "status": "ACTIVE",
      "permissions": ["read"],
      "description": "Client for analytics dashboard",
      "expires_at": null,
      "last_used_at": "2026-03-19T10:00:00Z",
      "created_at": "2026-03-19T08:00:00Z",
      "updated_at": "2026-03-19T08:00:00Z"
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-19T16:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数格式无效 |

---

#### POST /api/v1/admin/clients

创建新的 API 客户端。

**请求体参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 客户端名称（用于标识） |
| permissions | array | 否 | 权限列表，如 ["read"] |
| description | string | 否 | 客户端描述 |
| expires_at | datetime | 否 | 过期时间（null 表示永不过期） |

**api.sh:**
```bash
./scripts/api.sh clients create --name "Analytics Service" --permissions read --description "Analytics dashboard"
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/clients" \
  -H "Authorization: Bearer cp_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Analytics Service",
    "permissions": ["read"],
    "description": "Client for analytics dashboard"
  }'
```

**响应示例：**
```json
{
  "client": {
    "client_id": "cli_a1b2c3d4e5f67890",
    "name": "Analytics Service",
    "status": "ACTIVE",
    "permissions": ["read"],
    "description": "Client for analytics dashboard",
    "expires_at": null,
    "last_used_at": null,
    "created_at": "2026-03-19T08:00:00Z",
    "updated_at": "2026-03-19T08:00:00Z"
  },
  "api_key": "cp_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "warning": "This API key will only be shown once. Store it securely immediately."
}
```

> **重要提示：** API Key 仅在创建时显示一次，请立即安全存储。

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数验证失败 |

---

#### GET /api/v1/admin/clients/{client_id}

获取客户端详情。

**api.sh:**
```bash
./scripts/api.sh clients get cli_a1b2c3d4e5f67890
```

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/clients/cli_a1b2c3d4e5f67890" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "client_id": "cli_a1b2c3d4e5f67890",
  "name": "Analytics Service",
  "status": "ACTIVE",
  "permissions": ["read"],
  "description": "Client for analytics dashboard",
  "expires_at": null,
  "last_used_at": "2026-03-19T10:00:00Z",
  "created_at": "2026-03-19T08:00:00Z",
  "updated_at": "2026-03-19T08:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | client_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 客户端不存在 |

---

#### POST /api/v1/admin/clients/{client_id}/rotate

轮换客户端密钥。生成新的 API Key，旧 Key 立即失效。

**api.sh:**
```bash
./scripts/api.sh clients rotate cli_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/clients/cli_a1b2c3d4e5f67890/rotate" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "client": {
    "client_id": "cli_a1b2c3d4e5f67890",
    "name": "Analytics Service",
    "status": "ACTIVE",
    "permissions": ["read"],
    "description": "Client for analytics dashboard",
    "expires_at": null,
    "last_used_at": "2026-03-19T10:00:00Z",
    "created_at": "2026-03-19T08:00:00Z",
    "updated_at": "2026-03-19T12:00:00Z"
  },
  "api_key": "cp_live_newkey12345678901234567890abcdef",
  "warning": "The new API key will only be shown once. Store it securely immediately."
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | client_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 客户端不存在 |

---

#### POST /api/v1/admin/clients/{client_id}/suspend

挂起客户端。客户端将无法访问 API，但可以被重新激活。

**api.sh:**
```bash
./scripts/api.sh clients suspend cli_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/clients/cli_a1b2c3d4e5f67890/suspend" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "client_id": "cli_a1b2c3d4e5f67890",
  "name": "Analytics Service",
  "status": "SUSPENDED",
  "permissions": ["read"],
  "description": "Client for analytics dashboard",
  "expires_at": null,
  "last_used_at": "2026-03-19T10:00:00Z",
  "created_at": "2026-03-19T08:00:00Z",
  "updated_at": "2026-03-19T12:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | client_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 客户端不存在 |

---

#### POST /api/v1/admin/clients/{client_id}/activate

激活客户端。将已挂起的客户端重新激活。

**api.sh:**
```bash
./scripts/api.sh clients activate cli_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/admin/clients/cli_a1b2c3d4e5f67890/activate" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "client_id": "cli_a1b2c3d4e5f67890",
  "name": "Analytics Service",
  "status": "ACTIVE",
  "permissions": ["read"],
  "description": "Client for analytics dashboard",
  "expires_at": null,
  "last_used_at": "2026-03-19T10:00:00Z",
  "created_at": "2026-03-19T08:00:00Z",
  "updated_at": "2026-03-19T12:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | client_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 客户端不存在 |

---

#### DELETE /api/v1/admin/clients/{client_id}

撤销客户端（软删除）。客户端将无法访问 API，且无法恢复。

**api.sh:**
```bash
./scripts/api.sh clients delete cli_a1b2c3d4e5f67890
```

**curl:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/admin/clients/cli_a1b2c3d4e5f67890" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "message": "Client cli_a1b2c3d4e5f67890 revoked"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | client_id 格式无效 |
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 404 | 客户端不存在 |

### Logs & Diagnose

日志查询和系统诊断端点，用于故障排查和系统健康监控。

#### GET /api/v1/admin/logs

查询系统日志。用于故障排查和错误诊断。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| level | string | query | 否 | 日志级别：error, warning, info（默认 error） |
| source_id | string | query | 否 | 按源 ID 过滤 |
| since | string | query | 否 | 时间范围：1h, 24h, 7d, 或 ISO 日期时间 |
| limit | int | query | 否 | 最大结果数（1-200，默认 50） |

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/logs?level=error&since=24h&limit=20" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "data": [
    {
      "timestamp": "2026-03-30T10:30:00Z",
      "level": "ERROR",
      "module": "cyberpulse.tasks.ingestion_tasks",
      "source_id": "src_abc12345",
      "source_name": "Security Weekly",
      "error_type": "connection",
      "message": "Failed to fetch feed for src_abc12345: Connection timeout after 30s",
      "retry_count": 0,
      "suggestion": "检查网络连接或源服务器状态"
    }
  ],
  "count": 1,
  "server_timestamp": "2026-03-30T12:00:00Z"
}
```

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |
| 422 | 参数格式无效 |
| 500 | 读取日志文件失败 |

---

#### GET /api/v1/admin/diagnose

获取系统诊断概览。返回系统状态、组件健康状态和关键统计信息。

**curl:**
```bash
curl "http://localhost:8000/api/v1/admin/diagnose" \
  -H "Authorization: Bearer cp_live_xxx"
```

**响应示例：**
```json
{
  "status": "healthy",
  "version": "1.6.0",
  "components": {
    "database": "connected",
    "redis": "connected",
    "scheduler": "active"
  },
  "statistics": {
    "sources": {
      "active": 120,
      "frozen": 15,
      "pending_review": 5,
      "unhealthy": 3,
      "unhealthy_sources": [
        {
          "source_id": "src_xxx",
          "source_name": "Example Blog",
          "consecutive_failures": 5,
          "last_error_message": "Connection timeout",
          "last_error_at": "2026-03-30T10:00:00Z"
        }
      ]
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
      "top_error_sources": [
        {
          "source_id": "src_xxx",
          "source_name": "Example Blog",
          "error_count": 15
        }
      ]
    }
  },
  "server_timestamp": "2026-03-30T12:00:00Z"
}
```

**系统状态说明：**

| 状态 | 说明 |
|------|------|
| healthy | 所有组件正常，错误率低 |
| degraded | 部分组件异常或错误率较高 |
| unhealthy | 关键组件故障或错误率过高 |

**错误：**

| 状态码 | 说明 |
|--------|------|
| 401 | API Key 无效或已过期 |
| 403 | 权限不足 |

<!-- 后续章节将在后续任务中填充 -->

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