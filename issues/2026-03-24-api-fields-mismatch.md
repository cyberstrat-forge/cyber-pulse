# Issue: API 返回字段与文档描述不一致

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P2（影响下游系统集成）
**影响范围**: `/api/v1/contents` 和 `/api/v1/sources` 端点

## 问题详情

### 文档描述 vs 实际返回

#### 内容 API (`/api/v1/contents`)

| 字段 | 文档描述 | 实际返回 | 状态 |
|------|----------|----------|------|
| `id` / `content_id` | 内容唯一标识 | ✅ `content_id` | 字段名不同 |
| `title` / `normalized_title` | 标题 | ✅ `normalized_title` | 字段名不同 |
| `url` | 原始 URL | ❌ 缺失 | 需补充 |
| `content` / `normalized_body` | 正文 | ✅ `normalized_body` | 字段名不同 |
| `content_html` | HTML 格式正文 | ❌ 缺失 | 需补充 |
| `author` | 作者 | ❌ 缺失 | 需补充 |
| `tags` | 标签列表 | ❌ 缺失 | 需补充 |
| `published_at` | 发布时间 | ❌ 缺失 | 需补充 |
| `fetched_at` | 采集时间 | ❌ 缺失 | 需补充 |
| `source` | 情报源对象 | ❌ 只有 `source_count` | 需补充 |
| `quality_score` | 质量评分 | ❌ 缺失 | 需补充 |
| `canonical_hash` | 内容哈希 | ✅ 存在 | 正常 |

#### 源 API (`/api/v1/sources`)

| 字段 | 文档描述 | 实际返回 | 状态 |
|------|----------|----------|------|
| `id` / `source_id` | 源唯一标识 | ✅ `source_id` | 字段名不同 |
| `name` | 源名称 | ✅ 存在 | 正常 |
| `type` / `connector_type` | 类型 | ✅ `connector_type` | 字段名不同 |
| `url` | 源 URL | ❌ 缺失 | 需补充 |
| `tier` | 分级 | ✅ 存在 | 正常 |
| `status` | 状态 | ✅ 存在 | 正常 |
| `score` | 综合评分 | ✅ 存在 | 正常 |
| `schedule` | 调度表达式 | ❌ 缺失（为 null） | 需实现 |
| `stats` | 统计信息 | ✅ `total_items`, `total_contents` | 部分实现 |
| `last_fetched_at` | 最后采集时间 | ✅ 存在 | 正常 |

## 实际 API 响应示例

### 内容列表响应

```json
{
    "data": [
        {
            "content_id": "cnt_20260324142629_3d832ffd",
            "canonical_hash": "a2e1792c8dac1a263e56911c10b8d898",
            "normalized_title": "7AI Named to Fast Company's...",
            "normalized_body": "*Reflections from RSA on innovation...*",
            "first_seen_at": "2026-03-24T14:26:29.970821",
            "last_seen_at": "2026-03-24T14:26:29.970821",
            "source_count": 1,
            "status": "ACTIVE"
        }
    ],
    "next_cursor": "cnt_20260324140142_f9f98011",
    "has_more": true,
    "count": 3,
    "server_timestamp": "2026-03-24T14:34:51.022470Z"
}
```

### 源详情响应

```json
{
    "source_id": "src_834b7f3f",
    "name": "Itamar Gilad",
    "connector_type": "rss",
    "tier": "T2",
    "score": 50.0,
    "status": "ACTIVE",
    "is_in_observation": true,
    "observation_until": "2026-04-23T13:30:05.619035",
    "pending_review": false,
    "review_reason": null,
    "fetch_interval": null,
    "config": {
        "feed_url": "https://itamargilad.com/feed/"
    },
    "last_fetched_at": "2026-03-24T14:25:27.073367",
    "last_scored_at": null,
    "total_items": 10,
    "total_contents": 0,
    "created_at": "2026-03-24T13:30:05.618637",
    "updated_at": "2026-03-24T14:25:23.973389"
}
```

## 影响分析

### 对下游系统的影响

1. **字段名不一致**：下游系统需要适配两套命名
2. **缺失关键字段**：`url`, `published_at`, `author`, `tags` 对情报分析很重要
3. **缺少源关联**：无法直接知道内容来自哪个源

### 对 API 兼容性的影响

- 当前文档承诺的字段未实现，属于**功能缺失**
- 需要在不破坏现有 API 的情况下补充字段

## 解决方案建议

### 方案 1：更新 API 响应 Schema（推荐）

补充缺失字段，保持向后兼容：

```python
# src/cyberpulse/api/schemas/content.py

class ContentResponse(BaseModel):
    # 现有字段（保持不变）
    content_id: str
    canonical_hash: str
    normalized_title: str
    normalized_body: str
    first_seen_at: datetime
    last_seen_at: datetime
    source_count: int
    status: str

    # 新增字段（补充文档承诺的功能）
    url: Optional[str] = None           # 原始 URL
    content_html: Optional[str] = None  # HTML 格式正文
    author: Optional[str] = None        # 作者
    tags: List[str] = []                # 标签列表
    published_at: Optional[datetime] = None  # 发布时间
    fetched_at: Optional[datetime] = None    # 采集时间
    quality_score: Optional[int] = None      # 质量评分

    # 关联源信息
    source: Optional[SourceBrief] = None     # 来源信息
```

### 方案 2：更新文档以匹配实际实现

如果某些字段暂时不需要，更新文档说明：

```markdown
## 字段说明

| 字段 | 类型 | 说明 | 状态 |
|------|------|------|------|
| `content_id` | string | 内容唯一标识 | ✅ 已实现 |
| `url` | string | 原始 URL | 🚧 计划中 |
| `author` | string | 作者 | 🚧 计划中 |
...
```

### 方案 3：提供字段选择参数

允许客户端选择需要的字段：

```
GET /api/v1/contents?fields=id,title,url,source
```

## 优先级建议

### P0 - 立即补充

| 字段 | 原因 |
|------|------|
| `url` | 情报溯源必需 |
| `source` | 知道内容来源必需 |
| `published_at` | 时效性判断必需 |

### P1 - 尽快补充

| 字段 | 原因 |
|------|------|
| `author` | 来源可信度判断 |
| `tags` | 内容分类 |
| `quality_score` | 质量过滤 |

### P2 - 后续补充

| 字段 | 原因 |
|------|------|
| `content_html` | 格式化展示 |
| `fetched_at` | 采集时间 |

## 相关文件

- `docs/api-reference.md` - API 参考文档
- `docs/api-usage-guide.md` - API 使用指南
- `src/cyberpulse/api/schemas/content.py` - 内容 Schema
- `src/cyberpulse/api/schemas/source.py` - 源 Schema
- `src/cyberpulse/api/routers/content.py` - 内容路由
- `src/cyberpulse/api/routers/sources.py` - 源路由

---

## 补充：API 使用指南与实际实现差异

### 文档来源

开发者编写的 `docs/api-usage-guide.md` 详细描述了 API 使用方式，但与实际返回存在显著差异。

### 响应结构差异

**文档描述：**
```json
{
  "data": [...],
  "meta": {
    "next_cursor": "cnt_20260322120000_abc12345",
    "has_more": true
  }
}
```

**实际返回：**
```json
{
  "data": [...],
  "next_cursor": "cnt_20260324140142_f9f98011",
  "has_more": true,
  "count": 3,
  "server_timestamp": "2026-03-24T14:34:51.022470Z"
}
```

**差异**：
- `next_cursor` 和 `has_more` 在顶层，不在 `meta` 对象中
- 实际多了 `count` 和 `server_timestamp` 字段

### 内容字段完整对比

| 文档字段 | 实际字段 | 文档提及 | 实际返回 | 说明 |
|----------|----------|----------|----------|------|
| `id` | `content_id` | ✅ | ✅ | 字段名不同 |
| `title` | `normalized_title` | ✅ | ✅ | 字段名不同 |
| `content` | `normalized_body` | ✅ | ✅ | 字段名不同 |
| `url` | - | ✅ | ❌ | **缺失** |
| `author` | - | ✅ | ❌ | **缺失** |
| `tags` | - | ✅ | ❌ | **缺失** |
| `published_at` | - | ✅ | ❌ | **缺失** |
| `fetched_at` | - | ✅ | ❌ | **缺失** |
| `source` (对象) | `source_count` (数字) | ✅ | ✅ | **类型完全不同** |
| `quality_score` | - | ✅ | ❌ | **缺失** |
| - | `canonical_hash` | ❌ | ✅ | 文档未提及 |
| - | `first_seen_at` | ❌ | ✅ | 文档未提及 |
| - | `last_seen_at` | ❌ | ✅ | 文档未提及 |
| - | `status` | ❌ | ✅ | 文档未提及 |

### 文档中的示例代码

文档提供的 Python 示例代码：

```python
def process_content(content):
    content_id = content["id"]      # 实际是 content["content_id"]
    title = content["title"]        # 实际是 content["normalized_title"]
    url = content["url"]            # 实际不存在，会报 KeyError
    source = content["source"]      # 实际不存在，会报 KeyError
    quality_score = content["quality_score"]  # 实际不存在，会报 KeyError
```

**问题**：按文档写代码，运行时会报 `KeyError`。

### 下游开发者面临的问题

1. **代码无法运行**：示例代码直接复制粘贴会报错
2. **关键字段缺失**：`url`、`source` 对情报分析至关重要
3. **信任度问题**：文档不可靠，增加集成成本
4. **维护困难**：不知道哪些字段可用，哪些需要自己实现

### 建议处理方式

#### 选项 A：修复 API 以匹配文档（推荐）

让 API 返回文档承诺的所有字段，确保示例代码可用。

#### 选项 B：更新文档以匹配 API

如果某些字段暂时无法实现，应更新文档：

```markdown
### 内容字段

| 字段 | 类型 | 说明 | 状态 |
|------|------|------|------|
| `content_id` | string | 内容唯一标识 | ✅ 已实现 |
| `normalized_title` | string | 标准化标题 | ✅ 已实现 |
| `normalized_body` | string | 标准化正文 | ✅ 已实现 |
| `url` | string | 原始 URL | 🚧 计划中 |
| `source` | object | 来源信息 | 🚧 计划中 |
| `published_at` | datetime | 发布时间 | 🚧 计划中 |
| `author` | string | 作者 | 📋 规划中 |
| `tags` | array | 标签列表 | 📋 规划中 |
| `quality_score` | int | 质量评分 | 📋 规划中 |
| `canonical_hash` | string | 内容哈希 | ✅ 已实现 |
| `first_seen_at` | datetime | 首次发现时间 | ✅ 已实现 |
| `last_seen_at` | datetime | 最后发现时间 | ✅ 已实现 |
| `status` | string | 状态 | ✅ 已实现 |
```

同时更新示例代码：

```python
def process_content(content):
    content_id = content["content_id"]
    title = content["normalized_title"]
    body = content["normalized_body"]
    # url 和 source 暂不可用，需自行通过 items 关联查询
```

#### 选项 C：两步走

1. **短期**：更新文档标注字段状态，避免误导开发者
2. **中期**：实现缺失的关键字段（`url`, `source`, `published_at`）