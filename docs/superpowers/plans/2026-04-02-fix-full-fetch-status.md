# 全文采集成功后状态更新修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 修复全文采集成功后 Item 状态未从 PENDING_FULL_FETCH 更新为 MAPPED 的问题

**Issue:** #107

**Architecture:** 在 `quality_check_item` 中检查 `full_fetch_succeeded` 状态，避免死循环

**Tech Stack:** Python, FastAPI, SQLAlchemy, Dramatiq

---

## Root Cause Analysis

### 问题流程

```
初始采集 → normalize_item → quality_check_item
                                    │
                                    ▼ needs_full_fetch=True
                          status = PENDING_FULL_FETCH
                          fetch_full_content.send()
                                    │
                                    ▼
                          fetch_full_content (成功)
                                    │
                                    ├─ full_fetch_attempted = True
                                    ├─ full_fetch_succeeded = True
                                    ├─ raw_content = 新内容
                                    ├─ status = NORMALIZED
                                    └─ normalize_item.send() (重新触发)
                                            │
                                            ▼
                                    normalize_item (重跑)
                                            │
                                            ├─ 使用新的 raw_content 重新标准化
                                            └─ 标准化结果可能仍不达标
                                            │
                                            ▼
                                    quality_check_item (重跑)
                                            │
                                            ├─ ContentQualityService 检查内容质量
                                            ├─ 内容可能仍 < 500 字符 或 < 50 词
                                            ├─ 标题-正文相似度可能仍 > 0.8
                                            │
                                            ▼ needs_full_fetch=True (可能)
                                    ❌ 死循环起点！
                                    │
                                    ├─ 不检查 full_fetch_succeeded
                                    ├─ status = PENDING_FULL_FETCH (再次设置!)
                                    └─ fetch_full_content.send()
                                            │
                                            ▼
                                    fetch_full_content
                                            │
                                            └─ 跳过！full_fetch_attempted=True
                                               return {"skipped": True}
                                    
                                    ❌ 死循环！永远无法到达 MAPPED
```

### 根因

1. `quality_check_item` 不检查 `full_fetch_succeeded` 状态
2. 全文获取成功后，新内容可能仍不达标（< 500 字符、< 50 词、标题-正文相似度高）
3. `fetch_full_content` 跳过已尝试的 items

### 触发条件

- 全文获取成功 (`full_fetch_succeeded = True`)
- 重新质量检查时，内容仍被判定为 `needs_full_fetch = True`
- 可能原因：
  - Rule 1: 内容长度 < 500 字符（全文获取结果仍然太短）
  - Rule 2: 词数 < 50（全文获取结果仍然太少）
  - Rule 3: 标题-正文相似度 > 0.8（全文获取可能失败或格式错误）
  - Rule 4: 无效内容模式（全文获取可能得到错误页面）

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/cyberpulse/tasks/quality_tasks.py` | 检查 `full_fetch_succeeded`，避免死循环 |
| `src/cyberpulse/api/routers/admin/items.py` | 添加数据修复端点（可选） |
| `tests/test_tasks/test_quality_tasks.py` | 测试修复逻辑 |

---

## Task 1: 修复 quality_check_item 死循环问题

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`

**修改点:** 在 `quality_check_item` 函数中，当 `needs_full_fetch=True` 时，检查 `full_fetch_succeeded` 状态

**修复策略: REJECT 方案**

当 `full_fetch_succeeded=True` 且 `needs_full_fetch=True` 时：
- **含义**：全文获取已成功完成，但获取的内容仍不符合质量标准
- **正确行为**：REJECT（无法再尝试获取，不应接受不合格内容）
- **理由**：打破死循环，同时确保只有合格内容进入 MAPPED 状态

**实现逻辑:**

```python
# 在 quality_check_item 函数中，约第 79 行
if content_result.needs_full_fetch:
    # 新增：检查是否全文采集已成功
    if item.full_fetch_succeeded:
        # 全文采集已成功，但内容质量仍不合格
        # 无法再尝试获取 → REJECT
        item.status = ItemStatus.REJECTED  # type: ignore[assignment]
        if item.raw_metadata is None:
            item.raw_metadata = {}
        item.raw_metadata["rejection_reason"] = (
            f"Content quality still insufficient after full fetch: "
            f"{content_result.reason}"
        )
        db.commit()
        logger.warning(
            f"Item {item_id} rejected: content quality failed "
            f"after successful full fetch ({content_result.reason})"
        )
        return
    
    # 原有逻辑：未尝试过全文采集
    _handle_needs_full_fetch(db, item, content_result.reason)
    db.commit()

    # Trigger full content fetch
    if item.url:
        from .full_content_tasks import fetch_full_content
        fetch_full_content.send(item_id)
        logger.info(
            f"Queued full fetch for {item_id}: {content_result.reason}"
        )
    else:
        item.status = ItemStatus.REJECTED
        db.commit()
        logger.warning(
            f"Item {item_id} needs full fetch but has no URL, "
            "marking REJECTED"
        )

    logger.info(
        f"Quality check complete for item {item_id}: "
        f"PENDING_FULL_FETCH"
    )
    return
```

**为什么选择 REJECT 方案而非跳过检查方案：**

| 方案 | 行为 | 问题 |
|------|------|------|
| 跳过检查方案 | 忽略内容质量问题，直接进入元数据检查 | 可能接受不合格内容（< 500 字符等） |
| **REJECT 方案** | 拒绝不合格内容，打破死循环 | 确保数据质量，正确行为 |

元数据质量检查 (`QualityGateService`) 只验证结构完整性（published_at、title ≥5字符、body 非空、url），不验证内容质量。如果跳过内容检查，可能导致内容 < 50 词或标题-正文相似度高的 items 进入 MAPPED 状态，违背系统设计目标。

---

## Task 2: 添加单元测试

**Files:**
- Modify: `tests/test_tasks/test_quality_tasks.py`

**测试用例:**

1. `test_quality_check_full_fetch_succeeded_content_still_insufficient`
   - 创建 `full_fetch_succeeded=True` 的 item
   - 内容质量检查返回 `needs_full_fetch=True`（如内容仍 < 500 字符）
   - 验证 item 状态为 `REJECTED`
   - 验证 `rejection_reason` 包含 "after full fetch"

2. `test_quality_check_full_fetch_succeeded_content_quality_passes`
   - 创建 `full_fetch_succeeded=True` 的 item
   - 内容质量检查返回 `needs_full_fetch=False`（内容 >= 500 字符，>= 50 词）
   - 元数据质量检查通过
   - 验证 item 状态为 `MAPPED`（正常流程）

3. `test_quality_check_full_fetch_succeeded_but_meta_fails`
   - 创建 `full_fetch_succeeded=True` 的 item
   - 内容质量检查返回 `needs_full_fetch=False`
   - 元数据质量检查失败（如缺少 published_at）
   - 验证 item 状态为 `REJECTED`（元数据失败）

4. `test_quality_check_full_fetch_not_attempted_triggers_fetch`
   - 创建 `full_fetch_succeeded=None` 或 `False` 的 item
   - 内容质量检查返回 `needs_full_fetch=True`
   - 验证触发 `fetch_full_content.send()`
   - 验证 item 状态为 `PENDING_FULL_FETCH`（原有逻辑）

5. `test_quality_check_rejection_reason_recorded`
   - 验证 REJECT 时 `rejection_reason` 正确记录在 `raw_metadata`

---

## Task 3: 添加数据修复 API（可选）

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/items.py`

**端点:** `POST /api/v1/admin/items/fix-stuck-pending`

**功能:** 修复卡在 `PENDING_FULL_FETCH` 状态但 `full_fetch_succeeded=True` 的 items

**修复策略:** 采用 REJECT 方案处理卡住的数据

**实现:**

```python
@router.post("/items/fix-stuck-pending")
async def fix_stuck_pending_items(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> dict:
    """Fix items stuck in PENDING_FULL_FETCH with successful full fetch.
    
    These items have full_fetch_succeeded=True but are stuck in PENDING_FULL_FETCH
    status because quality_check_item doesn't check this flag.
    
    Fix strategy: Set status to REJECTED with appropriate reason.
    """
    from ...models import Item, ItemStatus
    
    # 查找卡住的 items
    stuck_items = db.query(Item).filter(
        Item.status == ItemStatus.PENDING_FULL_FETCH,
        Item.full_fetch_succeeded == True,
        Item.normalized_body.isnot(None),
    ).all()
    
    fixed_count = 0
    rejected_count = 0
    
    for item in stuck_items:
        # 检查内容质量是否合格
        from ...services.content_quality_service import ContentQualityService
        content_service = ContentQualityService()
        content_result = content_service.check_quality(
            title=item.normalized_title,
            body=item.normalized_body,
        )
        
        if content_result.needs_full_fetch:
            # 内容仍不合格 → REJECT
            item.status = ItemStatus.REJECTED
            if item.raw_metadata is None:
                item.raw_metadata = {}
            item.raw_metadata["rejection_reason"] = (
                f"Content quality still insufficient after full fetch (data fix): "
                f"{content_result.reason}"
            )
            rejected_count += 1
        else:
            # 内容合格 → 重新触发质量检查（进入正常流程）
            from ...tasks.quality_tasks import quality_check_item
            quality_check_item.send(
                item_id=item.item_id,
                normalized_title=item.normalized_title or "",
                normalized_body=item.normalized_body or "",
                canonical_hash=item.canonical_hash or "",
                word_count=item.word_count or 0,
            )
            fixed_count += 1
    
    db.commit()
    
    return {
        "status": "success",
        "processed_count": len(stuck_items),
        "rejected_count": rejected_count,
        "queued_for_recheck": fixed_count,
        "message": f"Processed {len(stuck_items)} stuck items: "
                   f"{rejected_count} rejected, {fixed_count} queued for recheck",
    }
```

**修复逻辑说明:**

对于卡住的 items，分两种情况处理：
1. **内容仍不合格** → 直接 REJECT（这是正确的状态）
2. **内容合格** → 重新触发质量检查（进入正常流程到 MAPPED）

这确保了历史数据被正确处理，不会因为新代码引入而被错误拒绝。

---

## Task 4: 运行测试验证

**验证步骤:**

1. 运行单元测试：`uv run pytest tests/test_tasks/test_quality_tasks.py -v`
2. 运行全部测试：`uv run pytest tests/ -v`
3. 验证修复后的 API 端点

---

## Task 5: 创建 PR

**PR 内容:**
- 关联 Issue #107
- 描述根因和修复方案
- 包含测试用例

---

## Self-Review Checklist

**完整性:**
- [ ] 问题根因分析完整
- [ ] 修复方案覆盖所有场景
- [ ] 测试用例覆盖边界条件
- [ ] 数据修复方案可选

**正确性:**
- [ ] 修复逻辑不会引入新问题
- [ ] 不会影响正常流程
- [ ] 向后兼容

**边界条件:**
- [ ] `full_fetch_succeeded=True` + `needs_full_fetch=True` → REJECT（内容不合格，无法再获取）
- [ ] `full_fetch_succeeded=True` + `needs_full_fetch=False` + meta PASS → MAPPED（正常流程）
- [ ] `full_fetch_succeeded=True` + `needs_full_fetch=False` + meta REJECT → REJECTED（元数据失败）
- [ ] `full_fetch_succeeded=False` + `needs_full_fetch=True` → PENDING_FULL_FETCH + 触发 fetch（原有逻辑）
- [ ] `full_fetch_succeeded=None` + `needs_full_fetch=True` → PENDING_FULL_FETCH + 触发 fetch（原有逻辑）
- [ ] `rejection_reason` 正确记录失败原因

---

## Risk Assessment

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 修复逻辑影响正常流程 | 低 | 中 | 完整的测试覆盖，边界条件测试 |
| 合格内容被误判为不合格 | 低 | 中 | REJECT 方案确保只有真正不合格内容被拒绝 |
| 全文成功后内容仍不合格的情况增多 | 中 | 低 | 这是正确行为，系统设计目标 |
| 现有卡住的数据无法自动修复 | 无 | 低 | 提供手动修复 API（Task 3） |

**关键决策说明：**

REJECT 方案是正确的设计选择：
- 如果全文获取成功但内容仍不合格，说明该 source 无法提供合格内容
- 继续尝试获取无意义（已成功一次，结果仍不达标）
- 接受不合格内容违背系统设计目标（为下游提供清洗后数据）
- 下游系统依赖 MAPPED 状态的数据质量保证

---

## Post-Fix Verification

修复后验证步骤：

1. 部署修复版本
2. 对现有卡住的数据调用数据修复 API
3. 验证：
   - 内容仍不合格的 items → 状态为 REJECTED
   - 内容合格的 items → 状态为 MAPPED
4. 验证新采集的 items 不再进入死循环：
   - 全文获取成功后，内容合格的 → MAPPED
   - 全文获取成功后，内容仍不合格的 → REJECTED
5. 验证业务 API 只返回 MAPPED 状态的 items