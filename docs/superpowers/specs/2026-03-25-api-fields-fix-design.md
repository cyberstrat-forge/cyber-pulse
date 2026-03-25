# Design: API 字段与参数规范修复

**Issues**: #44, #47
**Date**: 2026-03-25
**Status**: Draft

---

## 问题概述

### Issue #44: API 返回字段与文档描述不一致

当前 `/api/v1/contents` API 返回的字段与文档承诺存在显著差异：

| 问题类型 | 详情 |
|---------|------|
| **关键字段缺失** | `url`, `source`, `published_at`, `author`, `tags`, `quality_score` 均未返回 |
| **数据模型断层** | Content 是去重实体，不直接关联 Item/Source，丢失原始来源信息 |
| **文档示例代码无法运行** | `content["url"]` 会报 `KeyError` |

### Issue #47: API 参数/分页问题

| 问题 | 详情 |
|------|------|
| **limit 未限制** | 文档说最大 100，代码允许 1000 |
| **游标未校验** | 无效游标返回第一页，不报错 |
| **分页格式不一致** | Content API 用游标，Source API 用 offset |

---

## 根因分析

### 数据模型设计问题

当前三层模型：

```
Source (情报源) → Item (原始采集记录) → Content (去重后的内容实体)
```

**问题**：
1. Content 是去重实体，一个 Content 可能对应多个 Item
2. API 只返回 Content，丢失了 Item 层的原始信息（url, author, published_at 等）
3. 去重逻辑（MD5 精确匹配）无法可靠识别"相同内容"，跨源去重价值有限

### 系统职责边界

| 层级 | 系统 | 职责 |
|------|------|------|
| 采集层 | cyber-pulse | 采集、标准化、质量控制 |
| 分析层 | cyber-nexus | 语义理解、关联分析、情报研判 |

**语义级去重**（判断不同源报道同一事件）是分析能力，属于下游 cyber-nexus。

---

## 设计决策

### 决策 1：简化数据模型

**移除 Content 层，Item 即为情报条目**

```
简化后：Source (情报源) → Item (情报条目)
```

**理由**：
1. 精确匹配去重无法识别真正的"重复内容"
2. 语义去重是分析能力，属于下游
3. 每个 Item 作为独立情报处理，下游更简单

### 决策 2：API 直接返回 Item

Item 包含完整的来源信息和内容，无需关联查询。

### 决策 3：limit 参数规范

- 默认值：50
- 最大值：100
- 与文档保持一致

### 决策 4：游标严格校验

无效游标返回 400 错误，避免静默降级导致数据重复。

### 决策 5：不提供跨源去重字段

- cursor 机制已保证增量拉取
- 下游不需要跨源去重
- 每个 Item 独立处理

---

## API 设计

### 情报内容 API

**端点**：`GET /api/v1/items`

#### 情报源字段（嵌套对象）

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | string | 来源 ID |
| `source_name` | string | 来源名称 |
| `source_url` | string | 来源 RSS/网站 URL |
| `source_tier` | string | 来源等级 (T0-T3) |
| `source_score` | float | 来源质量评分 (0-100) |

#### 情报内容字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 情报唯一标识（item_id） |
| `title` | string | 标题（标准化后） |
| `author` | string | 作者（可能为空） |
| `published_at` | datetime | 原始发布时间 |
| `body` | string | 正文（标准化后，Markdown 格式） |
| `url` | string | 原始文章链接 |
| `completeness_score` | float | 内容完整性评分 (0-1) |
| `tags` | string[] | 标签列表（可能为空） |
| `fetched_at` | datetime | 采集时间 |

#### 响应示例

```json
{
  "data": [
    {
      "id": "item_20260325143052_a1b2c3d4",
      "title": "Critical Vulnerability Discovered in Popular Library",
      "author": "Security Research Team",
      "published_at": "2026-03-25T10:00:00Z",
      "body": "A critical vulnerability has been discovered...\n\n## Impact\n\n...",
      "url": "https://example.com/security/critical-vulnerability",
      "completeness_score": 0.85,
      "tags": ["vulnerability", "security", "CVE"],
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

### 分页参数

| 参数 | 类型 | 默认值 | 最大值 | 说明 |
|------|------|--------|--------|------|
| `cursor` | string | - | - | 游标（item_id） |
| `limit` | int | 50 | 100 | 每页数量 |
| `since` | datetime | - | - | 过滤 fetched_at >= since |

### 游标校验

**游标格式**：`item_{YYYYMMDDHHMMSS}_{uuid8}`

**正则**：`^item_\d{14}_[a-f0-9]{8}$`

**校验逻辑**：
- 有效游标：正常查询
- 无效游标：返回 400 错误

```json
{
  "detail": "Invalid cursor format: invalid_cursor"
}
```

---

## 完整性评分计算

### 公式

```
completeness_score = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
```

### 子指标

| 指标 | 计算方式 | 权重 |
|------|---------|------|
| `meta_completeness` | 作者、标签、发布时间是否存在 | 0.4 |
| `content_completeness` | 正文长度（>=500字符=1.0） | 0.4 |
| `noise_ratio` | HTML标签、广告标记占比 | 0.2（取反） |

---

## 向后兼容

### 旧 API 端点

保留 `/api/v1/contents` 端点，标记为 deprecated：

```
GET /api/v1/contents → 301 Redirect → GET /api/v1/items
```

响应头包含：
```
Deprecation: true
Link: </api/v1/items>; rel="successor"
```

### 迁移周期

| 阶段 | 时间 | 操作 |
|------|------|------|
| 阶段 1 | 发布后 1 个月 | 旧端点返回警告头 |
| 阶段 2 | 发布后 3 个月 | 旧端点返回 301 重定向 |
| 阶段 3 | 发布后 6 个月 | 移除旧端点 |

---

## 数据库变更

### 移除 Content 表

**迁移脚本**：
1. 删除 `contents` 表
2. 删除 `items.content_id` 外键
3. 保留 `items` 表所有字段

### Item 表新增字段

确保以下字段存在：
- `normalized_title`（标准化标题）
- `normalized_body`（标准化正文，Markdown）
- `meta_completeness`
- `content_completeness`
- `noise_ratio`

---

## 下游兼容

### cyber-nexus intel-pull 适配

| 变更 | 影响 |
|------|------|
| API 路径变更 | `/contents` → `/items` |
| 字段映射 | `content_id` → `id`, `fetched_at` → `fetched_at` |
| 新增字段 | `source` 对象、`completeness_score` |

### cursor 兼容性

- Item ID 格式与 Content ID 相同
- cursor 机制无需修改

---

## 实施范围

本次设计仅涵盖 **情报内容 API**，不包括：
- Source API（稍后讨论）
- 其他 API 端点

---

## 关联 Issue

- #44: API 返回字段与文档描述不一致
- #47: API 参数/分页问题