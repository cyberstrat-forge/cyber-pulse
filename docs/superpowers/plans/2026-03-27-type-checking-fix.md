# 类型检查问题修复计划

## 概述

解决 Issue #55 和 #58 中遗留的类型检查问题，提高代码类型安全性。

## 目标

- 消除 mypy 类型检查错误
- 统一 SQLAlchemy 模型类型注解
- 修复方法签名不匹配问题

## 任务列表

### Task 1: 修复 Enum 继承 (UP042)

**Files:**
- `src/cyberpulse/models/item.py`
- `src/cyberpulse/models/source.py`
- `src/cyberpulse/models/job.py`
- `src/cyberpulse/models/api_client.py`

**修改内容:**
将 `class Xxx(str, Enum):` 改为 `class Xxx(StrEnum):`

```python
# Before
from enum import Enum

class ItemStatus(str, Enum):
    NEW = "NEW"

# After
from enum import StrEnum

class ItemStatus(StrEnum):
    NEW = "NEW"
```

---

### Task 2: 为 Enum 字段添加类型注解

**Files:**
- `src/cyberpulse/models/source.py`
- `src/cyberpulse/models/job.py`
- `src/cyberpulse/models/item.py`
- `src/cyberpulse/models/api_client.py`

**修改内容:**
```python
# Before
status = Column(SAEnum(ItemStatus), ...)

# After
status: Mapped[ItemStatus] = Column(SAEnum(ItemStatus), ...)
```

---

### Task 3: 修复 avg_content_length 类型不匹配

**File:** `src/cyberpulse/services/source_quality_validator.py`

**修改内容:**
- Line 99: 将 float 转换为 int

```python
# Before
avg_content_length=statistics.mean(lengths)

# After
avg_content_length=int(statistics.mean(lengths))
```

---

### Task 4: 修复 RSS Connector 方法签名

**File:** `src/cyberpulse/services/rss_connector.py`

**问题:**
1. Line 66: fetch() 返回类型与父类不兼容
2. Line 229: datetime 重复 tzinfo 参数

**修改内容:**
- 统一 fetch() 返回类型
- 修复 datetime 构造

---

### Task 5: 修复 quality_gate_service.py 参数类型

**File:** `src/cyberpulse/services/quality_gate_service.py`

**问题:**
- Line 155: `_is_valid_url` 参数类型
- Line 172: `raw_metadata` 缺少类型注解
- Line 217: `_calculate_noise_ratio` 参数类型

**修改内容:**
添加必要的类型转换或类型注解

---

### Task 6: 运行测试验证

**验证命令:**
```bash
uv run pytest tests/ -v
uv run mypy src/ --ignore-missing-imports
uv run ruff check src/ tests/
```

---

## 预期结果

- mypy 错误从 134 减少到 < 50
- ruff UP042 警告清零
- 所有测试通过

## 风险

- Enum 继承变更可能影响序列化行为
- 类型注解变更需要测试覆盖