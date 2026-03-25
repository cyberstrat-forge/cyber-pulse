# Design: API 字段与参数规范修复

**Issues**: #44, #47（部分）
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

| 问题 | 详情 | 本设计覆盖 |
|------|------|-----------|
| **limit 未限制** | 文档说最大 100，代码允许 1000 | ✅ |
| **游标未校验** | 无效游标返回第一页，不报错 | ✅ |
| **分页格式不一致** | Content API 用游标，Source API 用 offset | ❌ 另行处理 |

**说明**：Source API 分页问题不在本设计范围内，将另行讨论处理。

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

#### 字段映射：数据库 → API

| API 字段 | 数据库字段 | 来源 | 说明 |
|----------|------------|------|------|
| `id` | `items.item_id` | 直接映射 | 情报唯一标识 |
| `title` | `items.normalized_title` | 新增字段 | 标准化标题 |
| `author` | `items.raw_metadata->>'author'` | JSONB 提取 | 作者 |
| `published_at` | `items.published_at` | 直接映射 | 原始发布时间 |
| `body` | `items.normalized_body` | 新增字段 | 标准化正文 |
| `url` | `items.url` | 直接映射 | 原始文章链接 |
| `completeness_score` | 计算字段 | 查询时计算 | 完整性评分 |
| `tags` | `items.raw_metadata->>'tags'` | JSONB 提取 | 标签数组 |
| `fetched_at` | `items.fetched_at` | 直接映射 | 采集时间 |

#### 情报源字段（嵌套对象）

| API 字段 | 数据库字段 | 来源 | 说明 |
|----------|------------|------|------|
| `source_id` | `sources.source_id` | 直接映射 | 来源 ID |
| `source_name` | `sources.name` | 直接映射 | 来源名称 |
| `source_url` | `sources.config->>'feed_url'` | JSONB 提取 | RSS URL |
| `source_tier` | `sources.tier` | 直接映射 | 来源等级 (T0-T3) |
| `source_score` | `sources.score` | 直接映射 | 质量评分 (0-100) |

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

### 计算时机

**查询时计算**，不存储到数据库。

### 公式

```
completeness_score = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
```

### 子指标（已存储）

| 指标 | 数据库字段 | 计算方式 | 权重 |
|------|------------|---------|------|
| `meta_completeness` | `items.meta_completeness` | 作者、标签、发布时间是否存在 | 0.4 |
| `content_completeness` | `items.content_completeness` | 正文长度（>=500字符=1.0） | 0.4 |
| `noise_ratio` | `items.noise_ratio` | HTML标签、广告标记占比 | 0.2（取反） |

---

## 向后兼容

### 旧 API 端点

保留 `/api/v1/contents` 端点，标记为 deprecated：

```
GET /api/v1/contents → 301 Redirect → GET /api/v1/items
```

**重定向行为**：
- 保留所有查询参数（cursor, limit, since, source_id）
- 返回 301 状态码
- 响应体为空或包含简短提示

响应头包含：
```
Deprecation: true
Link: </api/v1/items>; rel="successor"
Location: /api/v1/items?cursor=xxx&limit=50
```

### 迁移周期

| 阶段 | 时间 | 操作 |
|------|------|------|
| 阶段 1 | 发布后 1 个月 | 旧端点返回警告头 |
| 阶段 2 | 发布后 3 个月 | 旧端点返回 301 重定向 |
| 阶段 3 | 发布后 6 个月 | 移除旧端点 |

---

## 数据库变更

### 新增字段到 items 表

以下字段当前在 `contents` 表，需要迁移到 `items` 表：

| 字段 | 类型 | 说明 |
|------|------|------|
| `normalized_title` | VARCHAR(1024) | 标准化标题 |
| `normalized_body` | TEXT | 标准化正文（Markdown） |

**已有字段**（无需修改）：
- `meta_completeness` ✅
- `content_completeness` ✅
- `noise_ratio` ✅
- `raw_metadata` ✅（包含 author, tags）

### 迁移脚本

```sql
-- 1. 添加新字段
ALTER TABLE items ADD COLUMN normalized_title VARCHAR(1024);
ALTER TABLE items ADD COLUMN normalized_body TEXT;

-- 2. 从 contents 迁移数据（基于 content_id 关联）
UPDATE items i
SET normalized_title = c.normalized_title,
    normalized_body = c.normalized_body
FROM contents c
WHERE i.content_id = c.content_id;

-- 3. 删除外键约束
ALTER TABLE items DROP CONSTRAINT IF EXISTS items_content_id_fkey;

-- 4. 删除 content_id 列
ALTER TABLE items DROP COLUMN IF EXISTS content_id;

-- 5. 删除 contents 表
DROP TABLE IF EXISTS contents;
```

### 回滚脚本

```sql
-- 1. 重建 contents 表
CREATE TABLE contents (
    content_id VARCHAR(64) PRIMARY KEY,
    canonical_hash VARCHAR(64) NOT NULL UNIQUE,
    normalized_title VARCHAR(1024) NOT NULL,
    normalized_body TEXT NOT NULL,
    first_seen_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    source_count INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 添加 content_id 列
ALTER TABLE items ADD COLUMN content_id VARCHAR(64);

-- 3. 添加外键约束
ALTER TABLE items ADD CONSTRAINT items_content_id_fkey
    FOREIGN KEY (content_id) REFERENCES contents(content_id);

-- 4. 删除新增字段
ALTER TABLE items DROP COLUMN IF EXISTS normalized_title;
ALTER TABLE items DROP COLUMN IF EXISTS normalized_body;
```

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

## 测试策略

### 单元测试

| 测试项 | 测试内容 |
|--------|---------|
| 字段映射 | API 返回字段与数据库字段正确映射 |
| 游标校验 | 有效游标正常查询，无效游标返回 400 |
| limit 限制 | 超过 100 的 limit 被截断为 100 |
| completeness_score | 计算公式正确 |

### 集成测试

| 测试项 | 测试内容 |
|--------|---------|
| API 端到端 | 完整请求-响应流程 |
| 分页遍历 | 多页数据完整拉取 |
| 向后兼容 | 旧端点重定向正确 |
| 参数转发 | 重定向保留查询参数 |

### 手动验证

```bash
# 1. 创建 API 客户端
docker compose -f deploy/docker-compose.yml exec api cyber-pulse client create "test"

# 2. 测试新端点
curl -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/items?limit=10" | jq .

# 3. 测试游标校验
curl -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/items?cursor=invalid"
# 期望: 400 Bad Request

# 4. 测试 limit 限制
curl -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/items?limit=200" | jq '.data | length'
# 期望: 100

# 5. 测试重定向
curl -v -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/contents?limit=10"
# 期望: 301 Redirect with Deprecation header
```

---

## 实施范围

### 本设计覆盖

- ✅ Item API 字段规范（Issue #44）
- ✅ limit 参数限制（Issue #47）
- ✅ 游标格式校验（Issue #47）
- ✅ 数据模型简化（移除 Content 层）

### 不在本设计范围

- ❌ Source API 分页问题（Issue #47 部分）— 另行讨论
- ❌ 其他 API 端点

---

## 关联 Issue

- #44: API 返回字段与文档描述不一致
- #47: API 参数/分页问题（部分）