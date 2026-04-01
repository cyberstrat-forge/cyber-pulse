# 业务 API 增量同步设计

## API 设计

### 端点

```
GET /api/v1/items
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `since` | string | 否 | `beginning` 或 ISO 8601 时间戳 |
| `cursor` | string | 否 | 分页游标（`item_id`） |
| `limit` | int | 否 | 每页数量（1-100），默认 50 |

### 参数语义

| `since` 值 | 行为 | 排序方向 | 用途 |
|-----------|------|---------|------|
| 不传 | 返回最新一页 | 倒序（新→旧） | 检查最新数据 |
| `beginning` | 从最早数据开始 | 正序（旧→新） | 全量同步起点 |
| `{datetime}` | 从指定时间开始 | 正序（旧→新） | 增量同步 |

### 参数组合规则

| 参数组合 | 过滤条件 | 排序 | 用途 |
|---------|---------|------|------|
| 无参数 | 无 | 倒序 | 检查最新 |
| `since=beginning` | 无 | 正序 | 全量同步起点 |
| `since={ts}` | `fetched_at >= ts` | 正序 | 增量同步起点 |
| `since={ts}&cursor={id}` | `fetched_at >= ts` + 跳过 cursor | 正序 | 分页继续 |

**约束**：`cursor` 必须与 `since` 配合使用，不支持单独使用。

### 响应

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
  "count": 50
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | array | 情报列表 |
| `last_item_id` | string | 本页最后一条的 ID，用于 cursor 分页 |
| `last_fetched_at` | string | 本页最后一条的 fetched_at，用于增量同步 |
| `has_more` | boolean | 是否有更多数据 |
| `count` | int | 当前页数量 |

### 错误响应

| 状态码 | 说明 |
|--------|------|
| 400 | 参数错误（cursor 格式无效等） |
| 401 | API Key 无效或权限不足 |

---

## intel-pull 命令设计

### 废弃参数

| 参数 | 原用途 | 废弃原因 |
|------|--------|---------|
| `--preview` | 预览最新数据 | 场景模糊，用户应使用增量同步 |
| `--since` | 时间范围起点 | API 不再支持时间范围过滤 |
| `--until` | 时间范围终点 | API 不再支持时间范围过滤 |

### 保留参数

| 参数 | 用途 |
|------|------|
| `--init` | 全量同步 |
| `--source {name}` | 指定情报源 |
| `--output {dir}` | 指定输出目录 |
| `--list-sources` | 列出所有情报源 |
| `--add-source` | 交互式添加情报源 |
| `--remove-source {name}` | 删除情报源 |
| `--set-default {name}` | 设置默认情报源 |

### 命令与 API 映射

| 命令 | API 调用 |
|------|---------|
| `/intel-pull --init` | `GET /items?since=beginning&limit=50` |
| `/intel-pull` | `GET /items?since={last_fetched_at}&limit=50` |
| 分页继续 | `GET /items?since={ts}&cursor={last_item_id}&limit=50` |

---

## 状态管理

### 状态文件位置

```
{output_dir}/.intel/state.json
```

### 状态结构

```json
{
  "version": "3.0.0",
  "updated_at": "2026-04-02T09:00:00+08:00",

  "pulse": {
    "cursors": {
      "cyber-pulse": {
        "last_fetched_at": "2026-04-01T10:00:00.123Z",
        "last_item_id": "item_0050",
        "last_pull": "2026-04-02T09:00:00Z",
        "total_synced": 501
      }
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `last_fetched_at` | string | 最后一条数据的 fetched_at，用于 `since` 参数 |
| `last_item_id` | string | 最后一条数据的 ID，用于 `cursor` 参数 |
| `last_pull` | string | 最后同步完成时间 |
| `total_synced` | int | 累计同步数量（统计用） |

### 状态更新规则

| 场景 | 状态操作 |
|------|---------|
| `--init` | 清空状态后重建 |
| 增量同步 | 读取 → 更新 |
| 分页过程中 | 不更新（临时保存） |
| 同步完成 | 更新 `last_fetched_at` 和 `last_item_id` |

---

## 用户工作流

### 场景一：首次全量同步

```bash
/intel-pull --init
```

**执行流程**：

```
1. 清空该源的同步状态
2. GET /items?since=beginning&limit=50
3. 写入文件，保存临时 cursor
4. 如果 has_more=true:
   GET /items?since=beginning&cursor={last_item_id}&limit=50
   重复步骤 3-4
5. 同步完成，保存 last_fetched_at 和 last_item_id
```

**报告输出**：

```
════════════════════════════════════════════════════════
📡 情报拉取报告
════════════════════════════════════════════════════════

源: cyber-pulse
模式: 全量同步

【拉取统计】
• 新增情报: 501 条
• 写入位置: ./inbox/

【状态保存】
• last_fetched_at: 2026-04-01T10:00:00.123Z
• last_item_id: item_00501

════════════════════════════════════════════════════════
```

### 场景二：日常增量同步

```bash
/intel-pull
```

**执行流程**：

```
1. 读取 last_fetched_at
2. GET /items?since={last_fetched_at}&limit=50
3. 写入文件，保存临时 cursor
4. 如果 has_more=true:
   GET /items?since={ts}&cursor={last_item_id}&limit=50
   重复步骤 3-4
5. 同步完成，更新 last_fetched_at 和 last_item_id
```

**报告输出**：

```
════════════════════════════════════════════════════════
📡 情报拉取报告
════════════════════════════════════════════════════════

源: cyber-pulse
模式: 增量同步

【拉取统计】
• 新增情报: 15 条
• 写入位置: ./inbox/

【状态更新】
• last_fetched_at: 2026-04-02T08:30:00.456Z
• last_item_id: item_00516

════════════════════════════════════════════════════════
```

### 场景三：状态丢失处理

当状态文件不存在或 `last_fetched_at` 为空时：

```
⚠️  未找到同步状态

可能原因：
• 首次使用，未执行过全量同步
• 状态文件被删除或损坏

解决方案：
• 执行全量同步: /intel-pull --init
```

---

## 实现要点

### 服务端逻辑

```python
def list_items(since: str | None, cursor: str | None, limit: int):
    # cursor 必须与 since 配合使用
    if cursor and not since:
        raise HTTPException(400, "cursor must be used with since parameter")

    query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)

    # 时间过滤
    if since and since != "beginning":
        query = query.filter(Item.fetched_at >= since)

    # Cursor 跳过
    if cursor:
        cursor_item = db.query(Item).filter(Item.item_id == cursor).first()
        if cursor_item:
            query = query.filter(Item.fetched_at > cursor_item.fetched_at)

    # 排序：有 since 时正序，无 since 时倒序
    if since:
        query = query.order_by(Item.fetched_at.asc())
    else:
        query = query.order_by(Item.fetched_at.desc())

    items = query.limit(limit + 1).all()
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    return {
        "data": items,
        "last_item_id": items[-1].item_id if items else None,
        "last_fetched_at": items[-1].fetched_at if items else None,
        "has_more": has_more,
        "count": len(items)
    }
```

### 客户端逻辑

```typescript
async function sync(since: string | null): Promise<void> {
  let cursor: string | null = null;
  let totalCount = 0;
  let lastItemId: string | null = null;
  let lastFetchedAt: string | null = null;

  do {
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    if (cursor) params.set("cursor", cursor);
    params.set("limit", "50");

    const response = await fetch(`/api/v1/items?${params}`, {
      headers: { Authorization: `Bearer ${apiKey}` }
    });
    const data = await response.json();

    for (const item of data.data) {
      await writeMarkdown(item);
      totalCount++;
    }

    lastItemId = data.last_item_id;
    lastFetchedAt = data.last_fetched_at;
    cursor = data.has_more ? data.last_item_id : null;
  } while (cursor);

  // 保存状态
  saveState({ last_fetched_at: lastFetchedAt, last_item_id: lastItemId });
}
```

### 幂等性保证

1. **文件写入幂等**：文件名格式 `{YYYYMMDD}-{item_id}.md`，同一 item_id 覆盖写入
2. **API 请求幂等**：`since` 使用 `>=`，可能重复获取边界数据，通过文件覆盖去重

---

## 向后兼容

### 废弃参数

| 参数 | 替代方案 |
|------|---------|
| `from=beginning` | `since=beginning` |
| `since={datetime}`（时间范围） | 不支持时间范围过滤 |
| `until={datetime}` | 不支持时间范围过滤 |

---

## 变更影响

### cyber-pulse 变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/cyberpulse/api/routers/items.py` | 修改 | 重构参数处理逻辑 |
| `src/cyberpulse/api/schemas/item.py` | 修改 | 新增 `last_fetched_at` 字段 |
| `docs/business-api-reference.md` | 更新 | 更新 API 文档 |

### cyber-nexus 变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `plugins/market-radar/commands/intel-pull.md` | 修改 | 废弃 `--preview`、`--since`、`--until` 参数 |
| `plugins/market-radar/scripts/pulse/index.ts` | 修改 | 适配新 API |

---

## 关联 Issue

- Issue #98: 新增 `after` 参数支持增量同步