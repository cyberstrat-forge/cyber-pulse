# 场景支持分析报告

## 三个场景概览

| 场景 | 入口 | 当前行为 | 全文获取支持 |
|------|------|---------|-------------|
| 添加单个源 | `POST /sources` | 创建源 + 触发采集 | ✅ 一致 |
| 批量导入 | `process_import_job` | 创建源 + 触发采集 | ✅ 一致 |
| 定时采集 | `schedule_source_collection` | 触发采集 | ✅ 一致 |

---

## 详细分析

### 场景 1: 添加单个源

**代码路径：**
```
POST /sources
    ↓
SourceService.add_source()
    ↓
ingest_source.send(source_id)  ← 立即触发采集
    ↓
ingest_source → normalize_item → quality_check_item
```

**特点：**
- 创建源后立即触发初始采集
- 完整的数据处理流程

**全文获取支持：** ✅ 正确。采集后自动进入质量检测和全文获取流程。

---

### 场景 2: 批量导入

**代码路径：**
```
process_import_job
    ↓
SourceService.add_source()
    ↓
ingest_source.send(source_id)  ← 立即触发采集
    ↓
ingest_source → normalize_item → quality_check_item
```

**特点：**
- 创建源后立即触发初始采集
- 完整的数据处理流程

**全文获取支持：** ✅ 正确。采集后自动进入质量检测和全文获取流程。

---

### 场景 3: 定时采集

**代码路径：**
```
APScheduler (定时触发)
    ↓
collect_source(source_id)
    ↓
ingest_source.send(source_id)
    ↓
ingest_source → normalize_item → quality_check_item
```

**特点：**
- 按配置的间隔定时触发
- 完整的数据处理流程

**全文获取支持：** ✅ 正确。每次采集后自动进入质量检测和全文获取流程。

---

## 全文获取流程（统一）

无论哪个场景，全文获取都在 `quality_check_item` 阶段触发：

```
ingest_source
    ↓ 创建 Item (status=NEW)
normalize_item
    ↓ (status=NORMALIZED)
quality_check_item
    ├─ 内容完整 → MAPPED ✓
    └─ 内容不足
        ├─ 有 URL → PENDING_FULL_FETCH
        │       ↓
        │   fetch_full_content
        │       ├─ 成功 → NORMALIZED → quality_check_item
        │       └─ 失败 → REJECTED
        │
        └─ 无 URL → REJECTED
```

---

## 发现的问题

### 问题：现有代码仍依赖 `source.needs_full_fetch`

**位置：** `quality_tasks.py:126`

```python
if not content_validity and item.url:
    if source and source.needs_full_fetch:  # ← 依赖源配置
        needs_full_fetch = True
```

**方案 A 要求：** 移除这个依赖，改用 `ContentQualityService` 统一判断

**修复：** 实现计划中已包含此修改（Task 7）

---

## 已解决的变更

### 变更：添加单个源立即触发采集

**原行为：** `POST /sources` 只创建源，不触发采集

**新行为：** 创建源后立即调用 `ingest_source.send(source_id)` 触发初始采集

**实现：** 实现计划 Task 7 已包含对 `sources.py` 的修改

---

## 结论

| 场景 | 数据流 | 全文获取 | 状态 |
|------|--------|---------|------|
| 添加单个源 | 完整 | ✅ 支持 | 设计一致 |
| 批量导入 | 完整 | ✅ 支持 | 设计一致 |
| 定时采集 | 完整 | ✅ 支持 | 设计一致 |

**当前设计方案完全支持三个场景。** 唯一需要修复的是移除 `source.needs_full_fetch` 依赖，这在实现计划中已包含。

---

## 实现计划验证

实现计划的 Task 7 会修改 `quality_tasks.py`，移除对 `source.needs_full_fetch` 的依赖：

```python
# 修改前 (quality_tasks.py)
if source and source.needs_full_fetch:
    needs_full_fetch = True

# 修改后
content_service = ContentQualityService()
content_result = content_service.check_quality(
    title=normalized_title,
    body=normalized_body,
)

if content_result.needs_full_fetch:
    item.status = ItemStatus.PENDING_FULL_FETCH
    # 触发全文获取
```

这确保了三个场景都使用统一的内容质量判断逻辑。