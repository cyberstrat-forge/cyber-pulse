# 业务 API 增量同步实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `/api/v1/items` API 支持基于时间戳的增量同步

**Architecture:** 基于 `fetched_at` 时间戳过滤 + `cursor` 精确定位。`since` 参数支持 `beginning` 或 ISO 8601 时间戳，`cursor` 必须与 `since` 配合使用。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, PostgreSQL

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/cyberpulse/api/schemas/item.py` | 响应模型：`last_item_id`, `last_fetched_at` |
| `src/cyberpulse/api/routers/items.py` | API 逻辑：参数解析、查询构建、响应构建 |
| `docs/business-api-reference.md` | API 文档更新 |
| `tests/test_api/test_items.py` | API 测试 |

---

### Task 1: 更新响应 Schema

**Files:**
- Modify: `src/cyberpulse/api/schemas/item.py`

- [ ] **Step 1: 更新 ItemListResponse 模型**

```python
class ItemListResponse(BaseModel):
    """Item list response with pagination."""
    data: list[ItemResponse]
    last_item_id: str | None = Field(None, description="Last item ID in this page, use as cursor")
    last_fetched_at: datetime | None = Field(None, description="Last item's fetched_at, use for incremental sync")
    has_more: bool = False
    count: int
    server_timestamp: datetime
```

- [ ] **Step 2: 运行测试确认 Schema 变更不破坏现有功能**

Run: `uv run pytest tests/test_api/test_items.py -v`
Expected: 可能有测试失败，后续任务修复

- [ ] **Step 3: 提交 Schema 变更**

```bash
git add src/cyberpulse/api/schemas/item.py
git commit -m "refactor(api): rename next_cursor to last_item_id, add last_fetched_at"
```

---

### Task 2: 重构 API 参数和逻辑

**Files:**
- Modify: `src/cyberpulse/api/routers/items.py`

- [ ] **Step 1: 更新参数定义**

将现有参数替换为新设计：

```python
@router.get("/items", response_model=ItemListResponse)
async def list_items(
    since: str | None = Query(None, description="beginning or ISO 8601 datetime for incremental sync"),
    cursor: str | None = Query(None, description="Pagination cursor (item_id)"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    _client: ApiClient = Depends(require_permissions(["read"])),
) -> ItemListResponse:
```

- [ ] **Step 2: 添加参数验证逻辑**

```python
    # Validate: cursor must be used with since
    if cursor and not since:
        raise HTTPException(
            status_code=400, detail="cursor must be used with since parameter"
        )

    # Validate cursor format
    if cursor:
        validate_cursor(cursor)

    # Validate since format (beginning or ISO 8601 datetime)
    since_datetime = None
    if since and since != "beginning":
        try:
            since_datetime = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid since format: {since}. Use 'beginning' or ISO 8601 datetime."
            )
```

- [ ] **Step 3: 重构查询构建逻辑**

```python
    # Build query - only expose MAPPED items to downstream systems
    query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)

    # Apply time filter (based on fetched_at, not published_at)
    if since_datetime:
        query = query.filter(Item.fetched_at >= since_datetime)

    # Apply cursor skip
    if cursor:
        cursor_item = db.query(Item).filter(Item.item_id == cursor).first()
        if not cursor_item:
            raise HTTPException(
                status_code=404, detail=f"Cursor item not found: {cursor}"
            )
        query = query.filter(Item.fetched_at > cursor_item.fetched_at)

    # Apply ordering: ascending if since provided, descending otherwise
    if since:
        query = query.order_by(Item.fetched_at.asc())
    else:
        query = query.order_by(desc(Item.fetched_at))
```

- [ ] **Step 4: 更新响应构建逻辑**

```python
    # Build response
    last_item_id = items[-1].item_id if items else None
    last_fetched_at = items[-1].fetched_at if items else None

    return ItemListResponse(
        data=data,
        last_item_id=last_item_id,
        last_fetched_at=last_fetched_at,
        has_more=has_more,
        count=len(data),
        server_timestamp=datetime.now(UTC),
    )
```

- [ ] **Step 5: 移除未使用的导入**

```python
# Remove: since we no longer use since/until as datetime parameters from FastAPI
# Keep: from datetime import UTC, datetime (still needed)
```

- [ ] **Step 6: 运行测试**

Run: `uv run pytest tests/test_api/test_items.py -v`
Expected: 部分测试可能失败，需要更新测试

- [ ] **Step 7: 提交 API 重构**

```bash
git add src/cyberpulse/api/routers/items.py
git commit -m "refactor(api): implement incremental sync with since parameter"
```

---

### Task 3: 更新现有测试

**Files:**
- Modify: `tests/test_api/test_items.py`

- [ ] **Step 1: 更新 test_list_items_with_time_filter**

测试使用新的 `since` 参数格式：

```python
    @patch("cyberpulse.api.auth.get_current_client")
    def test_list_items_with_time_filter(self, mock_auth, client, mock_read_client):
        """Test listing items with since parameter."""
        mock_auth.return_value = mock_read_client

        # Test with ISO 8601 datetime
        response = client.get("/api/v1/items?since=2026-01-01T00:00:00Z")
        assert response.status_code in [200, 401]

        # Test with 'beginning'
        response = client.get("/api/v1/items?since=beginning")
        assert response.status_code in [200, 401]
```

- [ ] **Step 2: 添加 cursor 验证测试**

```python
    @patch("cyberpulse.api.auth.get_current_client")
    def test_cursor_without_since_returns_400(self, mock_auth, client, mock_read_client):
        """Test that cursor without since returns 400."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items?cursor=item_abc12345")
        assert response.status_code == 400
        assert "cursor must be used with since" in response.json()["detail"]
```

- [ ] **Step 3: 添加 since 格式验证测试**

```python
    @patch("cyberpulse.api.auth.get_current_client")
    def test_invalid_since_format_returns_400(self, mock_auth, client, mock_read_client):
        """Test that invalid since format returns 400."""
        mock_auth.return_value = mock_read_client

        response = client.get("/api/v1/items?since=invalid-format")
        assert response.status_code == 400
        assert "Invalid since format" in response.json()["detail"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_api/test_items.py -v`
Expected: 所有测试通过

- [ ] **Step 5: 提交测试更新**

```bash
git add tests/test_api/test_items.py
git commit -m "test(api): update tests for incremental sync parameters"
```

---

### Task 4: 添加增量同步场景测试

**Files:**
- Modify: `tests/test_api/test_items.py`

- [ ] **Step 1: 添加全量同步测试**

```python
def test_full_sync_with_since_beginning(client, db_session):
    """Test full sync starting from beginning."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different fetched_at times
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # Request with since=beginning
    response = client.get("/api/v1/items?since=beginning&limit=3")
    assert response.status_code == 200

    data = response.json()
    # Should return oldest items first (ascending order)
    assert len(data["data"]) == 3
    assert data["data"][0]["id"] == "item_00000000"  # Oldest first
    assert data["has_more"] is True
    assert data["last_item_id"] == "item_00000002"

    app.dependency_overrides.clear()
```

- [ ] **Step 2: 添加增量同步测试**

```python
def test_incremental_sync_with_since_datetime(client, db_session):
    """Test incremental sync with since=datetime."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items with different fetched_at times
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # Request items after the second item's time
    cutoff_time = base_time + timedelta(hours=2)
    response = client.get(f"/api/v1/items?since={cutoff_time.isoformat()}")
    assert response.status_code == 200

    data = response.json()
    # Should return items with fetched_at >= cutoff_time
    assert len(data["data"]) == 3  # items 2, 3, 4
    assert data["data"][0]["id"] == "item_00000002"

    app.dependency_overrides.clear()
```

- [ ] **Step 3: 添加分页继续测试**

```python
def test_pagination_with_cursor(client, db_session):
    """Test pagination using cursor with since."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    # Create items
    base_time = datetime(2026, 4, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        item = Item(
            item_id=f"item_{i:08d}",
            source_id="src_test",
            external_id=f"ext_{i}",
            url=f"https://example.com/{i}",
            title=f"Test Item {i}",
            published_at=base_time,
            fetched_at=base_time + timedelta(hours=i),
            status=ItemStatus.MAPPED,
        )
        db_session.add(item)
    db_session.commit()

    # First page
    response = client.get("/api/v1/items?since=beginning&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["has_more"] is True
    cursor = data["last_item_id"]

    # Second page using cursor
    response = client.get(f"/api/v1/items?since=beginning&cursor={cursor}&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["data"][0]["id"] == "item_00000002"  # Continues after cursor

    app.dependency_overrides.clear()
```

- [ ] **Step 4: 添加响应字段测试**

```python
def test_response_includes_last_fetched_at(client, db_session):
    """Test that response includes last_fetched_at field."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from cyberpulse.api.auth import get_current_client
    from cyberpulse.api.dependencies import get_db
    from cyberpulse.models import ApiClient, ApiClientStatus, Item, ItemStatus, Source

    # Create mock client
    mock_client = MagicMock(spec=ApiClient)
    mock_client.permissions = ["read"]
    mock_client.status = ApiClientStatus.ACTIVE

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_client] = lambda: mock_client

    # Create source and item
    source = Source(
        source_id="src_test",
        name="Test Source",
        connector_type="rss",
        config={"feed_url": "https://example.com/feed"},
    )
    db_session.add(source)

    fetched_at = datetime(2026, 4, 1, 10, 30, 45, tzinfo=UTC)
    item = Item(
        item_id="item_00000001",
        source_id="src_test",
        external_id="ext_1",
        url="https://example.com/1",
        title="Test Item",
        published_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC),
        fetched_at=fetched_at,
        status=ItemStatus.MAPPED,
    )
    db_session.add(item)
    db_session.commit()

    response = client.get("/api/v1/items?since=beginning")
    assert response.status_code == 200

    data = response.json()
    assert "last_fetched_at" in data
    assert data["last_fetched_at"] is not None
    assert "last_item_id" in data
    assert data["last_item_id"] == "item_00000001"

    app.dependency_overrides.clear()
```

- [ ] **Step 5: 运行所有测试确认通过**

Run: `uv run pytest tests/test_api/test_items.py -v`
Expected: 所有测试通过

- [ ] **Step 6: 提交新测试**

```bash
git add tests/test_api/test_items.py
git commit -m "test(api): add tests for incremental sync scenarios"
```

---

### Task 5: 更新 API 文档

**Files:**
- Modify: `docs/business-api-reference.md`

- [ ] **Step 1: 更新分页参数章节**

将现有的 Pagination & Filtering 章节替换为：

```markdown
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
```

- [ ] **Step 2: 更新获取方式示例章节**

替换现有的示例为：

```markdown
### 获取方式示例

#### 方式一：全量同步

适用场景：首次使用、数据迁移

**TypeScript:**
```typescript
// 首次请求
const response = await fetch(
  "http://localhost:8000/api/v1/items?since=beginning&limit=50",
  { headers: { Authorization: "Bearer cp_live_xxx" } }
);
const data = await response.json();

// 保存 last_fetched_at 和 last_item_id 用于后续增量同步
const { last_fetched_at, last_item_id } = data;

// 分页继续
if (data.has_more) {
  const nextResponse = await fetch(
    `http://localhost:8000/api/v1/items?since=beginning&cursor=${last_item_id}&limit=50`,
    { headers: { Authorization: "Bearer cp_live_xxx" } }
  );
}
```

#### 方式二：增量同步

适用场景：日常同步、获取新数据

**TypeScript:**
```typescript
// 使用上次保存的 last_fetched_at
const response = await fetch(
  `http://localhost:8000/api/v1/items?since=${last_fetched_at}&limit=50`,
  { headers: { Authorization: "Bearer cp_live_xxx" } }
);
const data = await response.json();

// 更新 last_fetched_at 和 last_item_id
last_fetched_at = data.last_fetched_at;
last_item_id = data.last_item_id;
```

#### 方式三：检查最新数据

适用场景：查看最新情报

**TypeScript:**
```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/items?limit=50",
  { headers: { Authorization: "Bearer cp_live_xxx" } }
);
const data = await response.json();
// data.data 按倒序排列，最新的在前
```

### 注意事项

- `cursor` 必须与 `since` 配合使用，不支持单独使用
- `cursor` 格式必须为 `item_{8位hex}`
- 时间过滤基于 `fetched_at` 字段（入库时间）
```

- [ ] **Step 3: 更新 Endpoints 章节的参数表**

```markdown
### Items

#### GET /api/v1/items

获取情报列表。

**参数：**

| 参数 | 类型 | 位置 | 必填 | 说明 |
|------|------|------|------|------|
| since | string | query | 否 | `beginning` 或 ISO 8601 时间戳 |
| cursor | string | query | 否 | 分页游标 |
| limit | int | query | 否 | 每页数量（1-100，默认 50） |
```

- [ ] **Step 4: 更新响应示例**

更新响应示例，添加 `last_item_id` 和 `last_fetched_at`：

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
  "count": 50,
  "server_timestamp": "2026-03-30T10:00:00Z"
}
```

- [ ] **Step 5: 更新响应字段说明表**

添加 `last_item_id` 和 `last_fetched_at` 的说明：

```markdown
| 字段 | 类型 | 说明 |
|------|------|------|
| data | array | 情报列表 |
| last_item_id | string | 本页最后一条的 ID，用于 cursor 分页 |
| last_fetched_at | string | 本页最后一条的 fetched_at，用于增量同步 |
| has_more | boolean | 是否有更多数据 |
| count | int | 当前页数据数量 |
| server_timestamp | datetime | 服务器时间戳 |
```

- [ ] **Step 6: 更新错误响应表**

```markdown
**错误：**

| 状态码 | 说明 |
|--------|------|
| 400 | cursor 未配合 since 使用，或 cursor/since 格式无效 |
| 401 | API Key 无效或权限不足 |
| 404 | cursor 指定的 item 不存在 |
```

- [ ] **Step 7: 移除废弃参数的文档**

删除 `since` 和 `until` 作为时间范围过滤的说明，删除 `from` 参数说明。

- [ ] **Step 8: 提交文档更新**

```bash
git add docs/business-api-reference.md
git commit -m "docs: update business API reference for incremental sync"
```

---

### Task 6: 运行完整测试套件

- [ ] **Step 1: 运行所有 API 测试**

Run: `uv run pytest tests/test_api/ -v`
Expected: 所有测试通过

- [ ] **Step 2: 运行完整测试套件**

Run: `uv run pytest tests/ -v --tb=short`
Expected: 所有测试通过

- [ ] **Step 3: 运行代码检查**

Run: `uv run ruff check src/ tests/`
Expected: 无错误

---

### Task 7: 创建 PR

- [ ] **Step 1: 推送所有提交**

```bash
git push origin feat/incremental-sync
```

- [ ] **Step 2: 更新 PR 描述**

更新 PR #99 的描述，标记设计文档已审核通过。

---

## Self-Review

**1. Spec Coverage:**
- ✅ API 参数设计：Task 2
- ✅ 响应字段：Task 1, Task 4
- ✅ 参数验证：Task 2, Task 3
- ✅ 用户工作流：Task 4 测试覆盖
- ✅ 文档更新：Task 5

**2. Placeholder Scan:**
- ✅ 无 TBD、TODO
- ✅ 所有代码步骤有完整代码块
- ✅ 所有命令有预期输出

**3. Type Consistency:**
- ✅ `last_item_id` 类型一致（str | None）
- ✅ `last_fetched_at` 类型一致（datetime | None）
- ✅ `since` 参数类型一致（str | None）