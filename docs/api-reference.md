# API 参考

完整的 Cyber Pulse REST API 端点说明。

## 认证

所有 API 请求需要在请求头中包含有效的 API Key：

```
Authorization: Bearer cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 内容 API

### 获取内容列表

获取内容列表，支持增量同步。

**请求**

```
GET /api/v1/contents
```

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| cursor | string | query | 否 | 起始游标（Content ID） |
| limit | integer | query | 否 | 每页数量，默认 50，最大 100 |
| source_id | string | query | 否 | 按情报源 ID 筛选 |

**响应**

```json
{
  "data": [
    {
      "id": "cnt_20260322120000_abc12345",
      "title": "安全漏洞通告：CVE-2026-1234",
      "url": "https://example.com/advisory/123",
      "content": "## 概述\n\n这是一个安全漏洞...",
      "content_html": "<h2>概述</h2><p>这是一个安全漏洞...</p>",
      "author": "Security Team",
      "tags": ["vulnerability", "CVE"],
      "published_at": "2026-03-22T12:00:00Z",
      "fetched_at": "2026-03-22T12:05:00Z",
      "source": {
        "id": "src_a1b2c3d4",
        "name": "安全客",
        "tier": "T1",
        "type": "rss"
      },
      "quality_score": 85,
      "canonical_hash": "sha256:abc123..."
    }
  ],
  "meta": {
    "next_cursor": "cnt_20260322120100_def67890",
    "has_more": true
  }
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 内容唯一标识 |
| title | string | 标题 |
| url | string | 原始 URL |
| content | string | Markdown 格式正文 |
| content_html | string | HTML 格式正文（可选） |
| author | string | 作者（可选） |
| tags | array | 标签列表 |
| published_at | string | 发布时间（ISO 8601） |
| fetched_at | string | 采集时间（ISO 8601） |
| source | object | 情报源信息 |
| quality_score | integer | 质量评分（0-100） |
| canonical_hash | string | 内容哈希（用于去重） |

**示例**

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents?limit=10"
```

---

### 获取单个内容

根据 ID 获取内容详情。

**请求**

```
GET /api/v1/contents/{content_id}
```

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| content_id | string | path | 是 | 内容 ID |

**响应**

```json
{
  "id": "cnt_20260322120000_abc12345",
  "title": "安全漏洞通告：CVE-2026-1234",
  "url": "https://example.com/advisory/123",
  "content": "## 概述\n\n这是一个安全漏洞...",
  "content_html": "<h2>概述</h2><p>这是一个安全漏洞...</p>",
  "author": "Security Team",
  "tags": ["vulnerability", "CVE"],
  "published_at": "2026-03-22T12:00:00Z",
  "fetched_at": "2026-03-22T12:05:00Z",
  "source": {
    "id": "src_a1b2c3d4",
    "name": "安全客",
    "tier": "T1",
    "type": "rss"
  },
  "quality_score": 85,
  "canonical_hash": "sha256:abc123..."
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 内容不存在 |

**示例**

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents/cnt_20260322120000_abc12345"
```

---

## 情报源 API

### 获取情报源列表

获取所有情报源列表。

**请求**

```
GET /api/v1/sources
```

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| status | string | query | 否 | 按状态筛选：active, frozen, inactive |
| tier | string | query | 否 | 按分级筛选：T0, T1, T2, T3 |
| type | string | query | 否 | 按类型筛选：rss, api, web, media |
| limit | integer | query | 否 | 返回数量限制，默认 50 |

**响应**

```json
{
  "data": [
    {
      "id": "src_a1b2c3d4",
      "name": "安全客",
      "type": "rss",
      "url": "https://www.anquanke.com/rss.xml",
      "tier": "T1",
      "status": "active",
      "score": 75,
      "config": {
        "feed_url": "https://www.anquanke.com/rss.xml"
      },
      "schedule": "0 */6 * * *",
      "created_at": "2026-03-18T10:00:00Z",
      "updated_at": "2026-03-22T15:00:00Z",
      "last_fetched_at": "2026-03-22T12:00:00Z",
      "stats": {
        "total_items": 1500,
        "items_last_24h": 25,
        "avg_quality_score": 78
      }
    }
  ]
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 情报源唯一标识 |
| name | string | 情报源名称 |
| type | string | 类型：rss, api, web, media |
| url | string | 情报源 URL |
| tier | string | 分级：T0, T1, T2, T3 |
| status | string | 状态：active, frozen, inactive |
| score | integer | 综合评分（0-100） |
| config | object | 采集配置（敏感信息已脱敏） |
| schedule | string | 调度表达式（Cron） |
| created_at | string | 创建时间 |
| updated_at | string | 更新时间 |
| last_fetched_at | string | 最后采集时间 |
| stats | object | 统计信息 |

**示例**

```bash
# 获取所有活跃情报源
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/sources?status=active"

# 获取 T0 级别情报源
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/sources?tier=T0"
```

---

### 获取情报源详情

根据 ID 获取情报源详情。

**请求**

```
GET /api/v1/sources/{source_id}
```

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| source_id | string | path | 是 | 情报源 ID |

**响应**

返回单个情报源对象，字段同上。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 情报源不存在 |

**示例**

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/sources/src_a1b2c3d4"
```

---

## 客户端 API

> **注意**：客户端 API 需要 admin 权限。请在创建客户端时添加 `--admin` 参数。

### 创建客户端

创建新的 API 客户端。

**请求**

```
POST /api/v1/clients
```

**认证**

需要 admin 权限的 API Key。

**请求体**

```json
{
  "name": "分析系统",
  "description": "下游分析系统接入"
}
```

**参数**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 客户端名称 |
| description | string | 否 | 客户端描述 |

**响应**

```json
{
  "client_id": "cli_a1b2c3d4e5f6g7h8",
  "name": "分析系统",
  "description": "下游分析系统接入",
  "api_key": "cp_live_1234567890abcdef1234567890abcdef",
  "status": "active",
  "permissions": ["read"],
  "created_at": "2026-03-22T10:00:00Z"
}
```

**重要**：`api_key` 仅在创建时返回一次，请妥善保存。

**示例**

```bash
curl -X POST -H "Authorization: Bearer cp_live_xxx" \
     -H "Content-Type: application/json" \
     -d '{"name": "分析系统", "description": "下游分析系统接入"}' \
     "https://api.example.com/api/v1/clients"
```

---

### 获取客户端列表

获取所有客户端列表。

**请求**

```
GET /api/v1/clients
```

**认证**

需要 admin 权限的 API Key。

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| limit | integer | query | 否 | 返回数量限制，默认 50 |

**响应**

```json
{
  "data": [
    {
      "client_id": "cli_a1b2c3d4e5f6g7h8",
      "name": "分析系统",
      "description": "下游分析系统接入",
      "status": "active",
      "permissions": ["read"],
      "created_at": "2026-03-22T10:00:00Z",
      "last_used_at": "2026-03-22T15:00:00Z"
    }
  ]
}
```

**示例**

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/clients"
```

---

### 删除客户端

删除指定客户端。

**请求**

```
DELETE /api/v1/clients/{client_id}
```

**认证**

需要 admin 权限的 API Key。

**参数**

| 参数 | 类型 | 位置 | 必需 | 说明 |
|------|------|------|------|------|
| client_id | string | path | 是 | 客户端 ID |

**响应**

成功时返回 204 状态码，无响应体。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 客户端不存在 |

**示例**

```bash
curl -X DELETE -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/clients/cli_a1b2c3d4e5f6g7h8"
```

---

## 健康检查 API

### 服务健康状态

检查服务健康状态。

**请求**

```
GET /health
```

**认证**

此端点无需认证。

**响应**

```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "1.3.0"
}
```

**状态说明**

| 状态 | 说明 |
|------|------|
| healthy | 所有服务正常 |
| degraded | 部分服务异常 |
| unhealthy | 服务不可用 |

**示例**

```bash
curl "https://api.example.com/health"
```

---

## 错误响应

### 错误格式

所有错误响应使用统一格式：

```json
{
  "detail": "错误描述信息",
  "code": "ERROR_CODE"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未认证（无效或缺失 API Key） |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 请求格式错误 |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |
| 503 | 服务暂时不可用 |

### 错误码

| 错误码 | 说明 |
|--------|------|
| `UNAUTHORIZED` | 无效或缺失 API Key |
| `CLIENT_DISABLED` | 客户端已禁用 |
| `CLIENT_EXPIRED` | 客户端已过期 |
| `FORBIDDEN` | 权限不足 |
| `NOT_FOUND` | 资源不存在 |
| `RATE_LIMITED` | 请求过于频繁 |
| `VALIDATION_ERROR` | 请求参数验证失败 |
| `INTERNAL_ERROR` | 服务器内部错误 |

---

## 速率限制

API 请求受速率限制保护：

| 限制类型 | 阈值 | 窗口 |
|----------|------|------|
| 每客户端 | 100 次/分钟 | 滑动窗口 |

超出限制时返回 429 状态码：

```json
{
  "detail": "Rate limit exceeded",
  "code": "RATE_LIMITED"
}
```

建议实现指数退避重试策略。

---

## ID 格式

| 类型 | 格式 | 示例 |
|------|------|------|
| 情报源 | `src_{uuid8}` | src_a1b2c3d4 |
| 内容 | `cnt_{YYYYMMDDHHMMSS}_{uuid8}` | cnt_20260322120000_abc12345 |
| 客户端 | `cli_{uuid16}` | cli_a1b2c3d4e5f6g7h8 |
| API Key | `cp_live_{hex32}` | cp_live_1234... |

---

## 情报源分级

| 分级 | 含义 | 评分范围 |
|------|------|----------|
| T0 | 核心战略源 | ≥ 80 |
| T1 | 重要参考源 | 60 - 80 |
| T2 | 普通观察源 | 40 - 60 |
| T3 | 观察/降频源 | < 40 |

---

## 情报源状态

| 状态 | 说明 |
|------|------|
| active | 活跃，正常采集 |
| frozen | 冻结，暂停采集 |
| inactive | 失效，不再使用 |