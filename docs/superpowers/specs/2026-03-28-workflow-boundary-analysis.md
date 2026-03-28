# 工作流边界条件推演

## 当前代码流程分析

### 状态定义（ItemStatus）

```python
NEW = "NEW"           # 刚采集
NORMALIZED = "NORMALIZED"  # 归一化完成
MAPPED = "MAPPED"     # 质量检测通过
REJECTED = "REJECTED" # 质量检测不通过
```

### API 暴露条件

```python
# items.py:71
query = db.query(Item).filter(Item.status != ItemStatus.REJECTED)
```

**问题 1**：NEW、NORMALIZED、MAPPED 状态都会被暴露。

---

## 边界条件路径推演

### 路径 1：正常流程（内容完整）

```
ingest → status=NEW
    ↓
normalize_item → status=NORMALIZED
    ↓
quality_check_item
    ├─ 内容质量检测通过
    └─ status=MAPPED ✓

API 暴露：MAPPED 状态 ✓ 正确
```

### 路径 2：内容不足 + 全文获取成功

```
ingest → status=NEW
    ↓
normalize_item → status=NORMALIZED
    ↓
quality_check_item
    ├─ 内容质量检测失败
    ├─ source.needs_full_fetch=True
    ├─ 触发 fetch_full_content
    └─ status=MAPPED (问题！内容不完整却是 MAPPED)

fetch_full_content
    ├─ Level 1/2 成功
    └─ 触发 normalize_item

normalize_item (第二次) → status=NORMALIZED (问题！)
    ↓
quality_check_item (第二次)
    └─ status=MAPPED

问题：
- 在全文获取进行中，item 是 MAPPED 状态，会被 API 暴露（问题！）
- 重归一化后是 NORMALIZED 状态，会被 API 暴露（问题！）
```

### 路径 3：内容不足 + 全文获取失败

```
ingest → status=NEW
    ↓
normalize_item → status=NORMALIZED
    ↓
quality_check_item
    ├─ 内容质量检测失败
    ├─ source.needs_full_fetch=True
    ├─ 触发 fetch_full_content
    └─ status=MAPPED (问题！)

fetch_full_content
    ├─ Level 1/2 失败
    ├─ full_fetch_succeeded=False
    └─ status 不变，仍然是 MAPPED (问题！)

API 暴露：MAPPED 状态，但内容不完整 ✗ 错误
```

### 路径 4：内容不足 + source.needs_full_fetch=False

```
ingest → status=NEW
    ↓
normalize_item → status=NORMALIZED
    ↓
quality_check_item
    ├─ 内容质量检测失败
    ├─ source.needs_full_fetch=False (或未配置)
    ├─ 不触发全文获取
    └─ status=MAPPED (问题！内容不完整却是 MAPPED)

API 暴露：MAPPED 状态，但内容不完整 ✗ 错误
```

### 路径 5：内容不足 + 无 URL

```
quality_check_item
    ├─ 内容质量检测失败
    ├─ item.url 为空
    └─ 不触发全文获取，status=MAPPED

API 暴露：MAPPED 状态，但内容不完整 ✗ 错误
```

### 路径 6：全文获取任务超时/异常

```
fetch_full_content
    ├─ max_retries=2
    ├─ 任务执行中，数据库事务已提交
    └─ status=MAPPED (问题！)

如果任务队列阻塞：
- item 长期保持 MAPPED 状态
- API 暴露不完整内容 ✗ 错误
```

### 路径 7：SSRF 保护触发

```
fetch_full_content
    ├─ URL 被 SSRF 保护拦截
    └─ fetch_with_retry 返回失败

当前代码：
    ├─ full_fetch_succeeded=False
    └─ status 不变，仍然是 MAPPED ✗ 错误
```

---

## 问题汇总

| 问题 | 描述 | 影响 |
|------|------|------|
| **P1** | 全文获取失败后状态不变 | API 暴露不完整内容 |
| **P2** | 全文获取进行中状态是 MAPPED | API 暴露不完整内容 |
| **P3** | 重归一化后状态是 NORMALIZED | API 暴露中间状态 |
| **P4** | 触发条件依赖 source.needs_full_fetch | 未配置时不触发，遗漏 |
| **P5** | 内容不足但未触发全文获取 | API 暴露不完整内容 |
| **P6** | API 暴露 NEW/NORMALIZED 状态 | 暴露未完成的 item |

---

## 方案 A 设计要求 vs 现状

| 要求 | 方案 A 设计 | 现有代码 | 状态 |
|------|-------------|----------|------|
| 统一触发点 | ContentQualityService | source.needs_full_fetch | ❌ 不符合 |
| 全文获取失败 | REJECTED | 保持 MAPPED | ❌ 不符合 |
| 进行中状态 | 不暴露 | 暴露 MAPPED | ❌ 不符合 |
| API 暴露 | 只有 MAPPED（内容完整） | NEW/NORMALIZED/MAPPED | ❌ 不符合 |

---

## 修正方案

### 修正 1：新增状态 PENDING_FULL_FETCH

```python
class ItemStatus(StrEnum):
    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PENDING_FULL_FETCH = "PENDING_FULL_FETCH"  # 新增
    MAPPED = "MAPPED"
    REJECTED = "REJECTED"
```

### 修正 2：API 只暴露 MAPPED

```python
# items.py
query = db.query(Item).filter(Item.status == ItemStatus.MAPPED)
```

### 修正 3：状态流转修正

```
quality_check_item
    ├─ 内容质量检测通过 → MAPPED
    └─ 内容质量检测失败
        ├─ 有 URL → PENDING_FULL_FETCH → 触发全文获取
        └─ 无 URL → REJECTED

fetch_full_content
    ├─ 成功 → normalize_item → NORMALIZED → quality_check_item
    └─ 失败 → REJECTED
```

### 修正 4：完整流程

```
ingest → NEW
    ↓
normalize_item → NORMALIZED
    ↓
quality_check_item
    ├─ 内容完整 → MAPPED ✓ (API 可见)
    └─ 内容不足
        ├─ 有 URL → PENDING_FULL_FETCH (API 不可见)
        │       ↓
        │   fetch_full_content
        │       ├─ 成功 → NORMALIZED → quality_check_item
        │       └─ 失败 → REJECTED (API 不可见)
        └─ 无 URL → REJECTED (API 不可见)
```

---

## 验证矩阵

| 场景 | 修正后状态 | API 可见 | 正确性 |
|------|-----------|---------|--------|
| 内容完整 | MAPPED | ✓ | ✓ |
| 内容不足 + 全文成功 | MAPPED | ✓ | ✓ |
| 内容不足 + 全文失败 | REJECTED | ✗ | ✓ |
| 内容不足 + 无 URL | REJECTED | ✗ | ✓ |
| 全文获取进行中 | PENDING_FULL_FETCH | ✗ | ✓ |
| SSRF 保护触发 | REJECTED | ✗ | ✓ |

---

## 实现变更清单

1. **新增状态**：`PENDING_FULL_FETCH`
2. **数据库迁移**：添加新状态值
3. **API 过滤**：`status == MAPPED` 而非 `status != REJECTED`
4. **quality_tasks.py**：
   - 内容不足 → `PENDING_FULL_FETCH`
   - 无 URL → `REJECTED`
5. **full_content_tasks.py**：
   - 成功 → `NORMALIZED` + 触发归一化
   - 失败 → `REJECTED`
6. **移除 source.needs_full_fetch 依赖**