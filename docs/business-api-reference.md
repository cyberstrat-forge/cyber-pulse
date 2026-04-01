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
| since | string | - | `beginning` 或 ISO 8601 时间戳 |
| cursor | string | - | 分页游标（`item_{8位hex}`） |
| limit | int | 50 | 每页数量，范围 1-100 |

### 参数语义

| since 值 | 行为 | 排序方向 | 用途 |
|----------|------|---------|------|
| 不传 | 返回最新一页 | 倒序（新→旧） | 检查最新数据 |
| `beginning` | 从最早数据开始 | 正序（旧→新） | 全量同步起点 |
| `{datetime}` | 从指定时间开始 | 正序（旧→新） | 增量同步 |

### 参数组合规则

| 参数组合 | 排序 | 用途 |
|---------|------|------|
| 无参数 | 倒序 | 检查最新 |
| `since=beginning` | 正序 | 全量同步起点 |
| `since={ts}` | 正序 | 增量同步起点 |
| `since={ts}&cursor={id}` | 正序 | 分页继续 |

**约束**：`cursor` 必须与 `since` 配合使用。

### 获取方式示例

#### 方式一：全量同步

适用场景：首次使用、数据迁移

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?since=beginning&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

**说明：** 返回最旧数据开始，正序排列，保存 `last_fetched_at` 和 `last_item_id` 用于增量同步。

#### 方式二：增量同步

适用场景：日常同步、获取新数据

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?since=2026-04-01T10:00:00Z&limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

**说明：** 返回指定时间之后入库的新数据。

#### 方式三：检查最新数据

适用场景：查看最新情报

**curl:**
```bash
curl "http://localhost:8000/api/v1/items?limit=50" \
  -H "Authorization: Bearer cp_live_xxx"
```

**说明：** 返回最新数据，倒序排列。

### 注意事项

- `cursor` 必须与 `since` 配合使用，不支持单独使用
- `cursor` 格式必须为 `item_{8位hex}`
- 时间过滤基于 `fetched_at` 字段（入库时间）

## Endpoints

### Items

#### GET /api/v1/items

获取情报列表。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| since | string | query | 否 | `beginning` 或 ISO 8601 时间戳 |
| cursor | string | query | 否 | 分页游标 |
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
      "body": "本文分析了...",
      "url": "https://example.com/article/123",
      "completeness_score": 0.85,
      "tags": ["APT", "威胁情报"],
      "word_count": 1500,
      "fetched_at": "2026-03-30T09:00:00Z",
      "source": {
        "source_id": "src_abc12345",
        "source_name": "Security Weekly",
        "source_url": "https://example.com/feed.xml",
        "source_tier": "T1",
        "source_score": 75.0
      }
    }
  ],
  "last_item_id": "item_b2c3d4e5",
  "last_fetched_at": "2026-03-30T10:00:00.123Z",
  "has_more": true,
  "count": 1,
  "server_timestamp": "2026-03-30T10:00:00Z"
}
```

**响应字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| data | array | 情报列表 |
| last_item_id | string | 本页最后一条的 ID，用于 cursor 分页 |
| last_fetched_at | string | 本页最后一条的 fetched_at，用于增量同步 |
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
| 400 | cursor 未配合 since 使用，或 cursor/since 格式无效 |
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