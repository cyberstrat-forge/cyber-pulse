# SQLAlchemy 2.0 Mapped 类型迁移设计

## 概述

**目标**: 将项目模型层从 SQLAlchemy 1.x `Column` 风格迁移到 2.0 `Mapped[T]` 风格，获得完整的类型安全。

**相关 Issue**: #55, #58

**影响范围**: 7 个模型文件 + 1 个 Mixin

**预期结果**: mypy 错误从 124 降至 ~10（剩余为非 SQLAlchemy 问题）

---

## 背景与动机

### 当前问题

```python
# 当前代码 (SQLAlchemy 1.x 风格)
class Source(Base, TimestampMixin):
    tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
    status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)
    score = Column(Float, nullable=False, default=50.0)
```

**问题**: `Column[T]` 是描述符，静态分析器看到的是 `Column[T]`，而运行时返回 `T`。导致：

```python
source.status = SourceStatus.ACTIVE  # mypy 报错: Column[SourceStatus] vs SourceStatus
source.score = 0.5                    # mypy 报错: Column[float] vs float
```

### 解决方案

```python
# 目标代码 (SQLAlchemy 2.0 风格)
class Source(Base, TimestampMixin):
    tier: Mapped[SourceTier] = mapped_column(default=SourceTier.T2)
    status: Mapped[SourceStatus] = mapped_column(default=SourceStatus.ACTIVE)
    score: Mapped[float] = mapped_column(default=50.0)
```

`Mapped[T]` 让 mypy 正确推断属性类型为 `T`，实现类型安全。

---

## 迁移模式

### 1. 基本字段

```python
# Before
source_id = Column(String(64), primary_key=True, index=True)
name = Column(String(255), nullable=False, unique=True)
score = Column(Float, nullable=False, default=50.0)
total_items = Column(Integer, nullable=False, default=0)

# After
source_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
score: Mapped[float] = mapped_column(default=50.0)
total_items: Mapped[int] = mapped_column(default=0)
```

**规则**:
- 主键、有长度限制的字符串：保留 `String(N)` 参数
- `nullable=False` + `default` → 可省略 `nullable=False`（默认值隐含非空）
- 数值类型：省略类型参数，由 `Mapped[T]` 推断

### 2. 可空字段

```python
# Before
observation_until = Column(DateTime, nullable=True)
review_reason = Column(Text, nullable=True)
fetch_interval = Column(Integer, nullable=True)

# After
observation_until: Mapped[datetime | None] = mapped_column()
review_reason: Mapped[str | None] = mapped_column(Text)
fetch_interval: Mapped[int | None] = mapped_column()
```

**规则**:
- `Mapped[T | None]` 表示可空，无需 `nullable=True`
- 大文本字段保留 `Text` 参数

### 3. Boolean 字段

```python
# Before - 非空 Boolean
is_in_observation = Column(Boolean, nullable=False, default=False)
pending_review = Column(Boolean, nullable=False, default=False)

# After - 非空 Boolean
is_in_observation: Mapped[bool] = mapped_column(default=False)
pending_review: Mapped[bool] = mapped_column(default=False)

# Before - 可空 Boolean
full_fetch_succeeded = Column(Boolean, nullable=True)

# After - 可空 Boolean
full_fetch_succeeded: Mapped[bool | None] = mapped_column()
```

**规则**:
- 非空 Boolean 有默认值：`Mapped[bool]` + `default=...`
- 可空 Boolean：`Mapped[bool | None]`

**受影响字段**: `Source.is_in_observation`, `Source.pending_review`, `Source.needs_full_fetch`, `Item.full_fetch_attempted`, `Item.full_fetch_succeeded`

### 4. Float 字段

```python
# Before - 非空 Float
score = Column(Float, nullable=False, default=50.0)

# After - 非空 Float
score: Mapped[float] = mapped_column(default=50.0)

# Before - 可空 Float 有默认值
full_fetch_threshold = Column(Float, nullable=True, default=0.7)
quality_score = Column(Float, nullable=True, default=50.0)

# After - 可空 Float 有默认值
full_fetch_threshold: Mapped[float | None] = mapped_column(default=0.7)
quality_score: Mapped[float | None] = mapped_column(default=50.0)

# Before - 可空 Float 无默认值
meta_completeness = Column(Float, nullable=True)
content_completeness = Column(Float, nullable=True)
noise_ratio = Column(Float, nullable=True)

# After - 可空 Float 无默认值
meta_completeness: Mapped[float | None] = mapped_column()
content_completeness: Mapped[float | None] = mapped_column()
noise_ratio: Mapped[float | None] = mapped_column()
```

**规则**:
- 非空：`Mapped[float]` + `default=...`
- 可空有默认值：`Mapped[float | None]` + `default=...`
- 可空无默认值：`Mapped[float | None]`

**受影响字段**: `Source.score`, `Source.full_fetch_threshold`, `Source.quality_score`, `Item.meta_completeness`, `Item.content_completeness`, `Item.noise_ratio`

### 5. 枚举字段

```python
# Before
tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.T2)
status = Column(Enum(SourceStatus), nullable=False, default=SourceStatus.ACTIVE)

# After
tier: Mapped[SourceTier] = mapped_column(default=SourceTier.T2)
status: Mapped[SourceStatus] = mapped_column(default=SourceStatus.ACTIVE)
```

**规则**:
- 无需 `Enum()` 包装，由 `Mapped[EnumType]` 自动推断
- 无需 `nullable=False`，有默认值即非空

### 6. 外键字段

```python
# Before
source_id = Column(String(64), ForeignKey("sources.source_id"), nullable=True)
content_id = Column(String(64), ForeignKey("contents.content_id"), nullable=True, index=True)

# After
source_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sources.source_id"))
content_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("contents.content_id"), index=True)
```

**规则**:
- 可空外键：`Mapped[str | None]`
- 保留 `ForeignKey()` 和索引参数

**注意**: Item.source_id 是非空外键，Item.content_id 是可空外键。

### 7. JSONB 字段

```python
# Before
config = Column(JSONB, nullable=False, default=dict)
permissions = Column(JSONB, nullable=False, default=list)

# After
config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
```

**规则**:
- 使用精确的类型注解：`dict[str, Any]` 或 `list[str]`
- 保留 `JSONB` 参数和默认值

### 8. Relationship 字段

```python
# Before
jobs = relationship("Job", back_populates="source")
source = relationship("Source", back_populates="jobs")

# After
jobs: Mapped[list["Job"]] = relationship(back_populates="source")
source: Mapped["Source | None"] = relationship(back_populates="jobs")
```

**规则**:
- 一对多：`Mapped[list["Model"]]`
- 多对一：`Mapped["Model | None"]`（可空外键）
- 字符串引用避免循环导入

### 9. 复合索引 (`__table_args__`)

```python
# Before (无变化)
__table_args__ = (
    Index("ix_items_source_published", "source_id", "published_at"),
    Index("ix_items_source_url", "source_id", "url", unique=True),
)

# After (保持不变)
__table_args__ = (
    Index("ix_items_source_published", "source_id", "published_at"),
    Index("ix_items_source_url", "source_id", "url", unique=True),
)
```

**规则**: `__table_args__` 与 `Column` 定义无关，迁移时保持不变。

**受影响模型**:
- `Item`: 2 个复合索引
- `Content`: 1 个复合索引

### 10. TimestampMixin

```python
# Before
class TimestampMixin:
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

# After
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

**规则**:
- 无需 `nullable=False`，有默认值即非空
- 保留 `func.now()` 和 `onupdate`

### 11. 枚举类升级

```python
# Before
from enum import Enum

class ItemStatus(str, Enum):
    NEW = "NEW"
    NORMALIZED = "NORMALIZED"

# After
from enum import StrEnum

class ItemStatus(StrEnum):
    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
```

**规则**:
- Python 3.11+ 支持 `StrEnum`，语义更清晰
- 无需 `(str, Enum)` 多重继承
- 统一导入风格：所有枚举使用 `from enum import StrEnum`

**当前不一致情况**:
- `source.py`, `job.py`: `from enum import Enum as PyEnum`
- `item.py`, `content.py`, `api_client.py`: `from enum import Enum`
- 迁移后统一为 `StrEnum`

### 12. 可空 JSONB 字段

```python
# Before (无默认值)
result = Column(JSONB, nullable=True)

# After
result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
```

**规则**: 可空 JSONB 无默认值时，类型为 `Mapped[dict[str, Any] | None]`。

**受影响字段**: `Job.result`

### 13. Settings 模型

```python
# Before
class Settings(Base, TimestampMixin):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)

# After
class Settings(Base, TimestampMixin):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
```

---

## 迁移计划

### 执行顺序

按复杂度递增，每个步骤后验证：

| Step | 组件 | 字段数 | 特殊处理 | 难度 |
|------|------|--------|---------|------|
| 1 | `TimestampMixin` | 2 | func.now() | 低 |
| 2 | `Settings` | 2 | 主键 + 可空 | 低 |
| 3 | `ApiClient` | 8 | 枚举 + JSONB(list) | 低 |
| 4 | `Content` | 8 + 1复合索引 | 枚举 | 低 |
| 5 | `Item` | 17 + 2复合索引 | 枚举 + 外键(2) + JSONB + Boolean(2) + Float可空(3) | 中 |
| 6 | `Job` | 11 | 枚举(2) + 外键 + JSONB + relationship | 中 |
| 7 | `Source` | 26 + 1 relationship | 枚举(2) + JSONB + Boolean(3) + Float可空(2) | 高 |
| 8 | 枚举类升级 (6个) | - | StrEnum | 低 |

### 验证检查点

每个 Step 后执行：

```bash
# 1. 模型层类型检查
uv run mypy src/cyberpulse/models/ --ignore-missing-imports

# 2. 模型测试
uv run pytest tests/test_models/ tests/test_models.py -v

# 3. 数据库兼容性
uv run alembic check
```

完成后执行完整验证：

```bash
# 全量类型检查
uv run mypy src/ --ignore-missing-imports

# 全量测试
uv run pytest

# Lint 检查
uv run ruff check src/ tests/
```

---

## 文件变更清单

### 必须修改

| 文件 | 变更内容 |
|------|---------|
| `src/cyberpulse/models/base.py` | TimestampMixin 迁移 |
| `src/cyberpulse/models/settings.py` | Settings 模型迁移 |
| `src/cyberpulse/models/api_client.py` | ApiClient 模型 + 枚举迁移 |
| `src/cyberpulse/models/content.py` | Content 模型 + 枚举迁移 |
| `src/cyberpulse/models/item.py` | Item 模型 + 枚举迁移 |
| `src/cyberpulse/models/job.py` | Job 模型 + 枚举 + relationship 迁移 |
| `src/cyberpulse/models/source.py` | Source 模型 + 枚举 + relationship 迁移 |

### 无需修改

| 文件/目录 | 原因 |
|-----------|------|
| `alembic/versions/` | 数据库结构不变 |
| `src/cyberpulse/services/` | 类型推断自动修复 |
| `src/cyberpulse/tasks/` | 类型推断自动修复 |
| `src/cyberpulse/api/` | 类型推断自动修复 |
| `src/cyberpulse/api/schemas/` | Pydantic 已用 `from_attributes` |

---

## 预期结果

### mypy 错误变化

| 类别 | 迁移前 | 迁移后 |
|------|--------|--------|
| SQLAlchemy Column 类型问题 | ~110 | 0 |
| 枚举字段缺类型注解 | 7 | 0 |
| 其他问题（非本次范围） | 7 | ~7 |
| **总计** | **124** | **~7** |

### 剩余问题（后续 Issue 处理）

| 问题 | 文件位置 | 说明 |
|------|---------|------|
| `item.normalized_title` 属性不存在 | `api/routers/items.py:124` | Item 模型无此字段，Content 模型有。需确认是引用错误还是需添加字段 |
| `item.normalized_body` 属性不存在 | `api/routers/items.py:127` | 同上 |
| `rss_connector.fetch` 返回类型不兼容 | `services/rss_connector.py:66` | 方法签名与基类不匹配 |
| `datetime` 重复 `tzinfo` 参数 | `services/rss_connector.py:233` | 参数传递错误 |
| `avg_content_length` float vs int | `services/source_quality_validator.py:99` | 类型不匹配 |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 迁移引入语法错误 | 测试失败 | 每个 Step 后运行模型测试 |
| 类型注解错误 | mypy 新错误 | 每个 Step 后运行类型检查 |
| 运行时行为变化 | 功能异常 | 全量测试验证 |
| Alembic 检测到差异 | 产生意外迁移 | `alembic check` 验证无差异 |

---

## 参考资料

- [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [SQLAlchemy ORM Declarative Mapping](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
- [Python 3.11 StrEnum](https://docs.python.org/3/library/enum.html#enum.StrEnum)