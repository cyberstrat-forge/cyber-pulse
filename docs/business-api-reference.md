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