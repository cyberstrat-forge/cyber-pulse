# 设计文档：RSS 内容质量问题全面修复

**版本**: 1.1
**日期**: 2026-03-25
**状态**: 已批准（经过 Spec Review）
**Issue**: #41, #46

---

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.1 | 2026-03-25 | 根据 Spec Review 更新：TitleParserService 实现、源治理逻辑、准入标准调整、任务集成修正 |
| 1.0 | 2026-03-25 | 初始版本 |

---

## 1. 概述

### 1.1 问题背景

cyber-pulse 是战略情报采集系统，通过 RSS 源采集高价值内容，提供给下游分析系统。当前存在以下内容质量问题：

| 问题类型 | 影响范围 | 严重程度 |
|---------|---------|---------|
| 标题 = 正文 | Anthropic Research (18条，100%) | P1 |
| 内容极短 | ~57 个源，RSS 只提供摘要 | P2 |
| RSS 无正文 | paulgraham.com 等约 57 个源 | P2 |

### 1.2 根因分析

1. **RSS Feed 结构问题** - 部分 RSS 的 `<title>` 和 `<description>` 完全相同
2. **缺少全文获取机制** - RSS 只提供摘要时无法获取全文
3. **质量门禁不完善** - 未检测标题=正文、正文过短等问题
4. **源准入无质量检测** - 添加源时不验证内容质量

### 1.3 设计目标

1. 增强质量门禁，检测并标记内容质量问题
2. 实现全文获取能力，从原文链接提取完整内容
3. 建立源准入验证机制，拒绝低质量源
4. 使用已知问题源作为测试用例，确保修复有效

---

## 2. 架构设计

### 2.1 采集流程改进

```
┌─────────────────────────────────────────────────────────────────┐
│                        采集流程 (改进后)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ingest_source ──→ normalize_item ──→ quality_check_item       │
│        │                                    │                  │
│        ▼                                    ▼                  │
│  ┌─────────────┐                   ┌─────────────────┐         │
│  │ Source 标记  │                   │ 质量检测增强     │         │
│  │ needs_full_ │                   │ • 标题=正文检测  │         │
│  │ fetch       │                   │ • 正文过短警告   │         │
│  │ full_fetch_ │                   │ • 标题格式异常   │         │
│  │ threshold   │                   └────────┬────────┘         │
│  └─────────────┘                            │                  │
│                                              ▼                  │
│                                    ┌─────────────────┐         │
│                                    │ content_complete│         │
│                                    │ ness < threshold?│         │
│                                    └────────┬────────┘         │
│                                             │                  │
│                              ┌──────────────┴──────────────┐   │
│                              ▼                             ▼   │
│                           [是]                           [否]  │
│                              │                             │   │
│                              ▼                             │   │
│                    fetch_full_content ──┐                  │   │
│                              │          │                  │   │
│                              ▼          │                  │   │
│                    re-normalize_item ◄──┘                  │   │
│                              │                             │   │
│                              ▼                             │   │
│                    quality_check_item                      │   │
│                              │                             │   │
│                              ▼                             ▼   │
│                         [完成] ────────────────────────→ [完成]│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 源准入验证流程

```
用户请求添加源 → SourceQualityValidator.validate_source()
                    ↓
            [符合质量标准?]
              ↓           ↓
             是          否
              ↓           ↓
          保存源      拒绝添加，返回原因
              ↓
         开始采集
```

**质量标准：**
- 样本数 ≥ 3 条（最多采集 10 条）
- 平均 content_completeness ≥ 0.4
- 平均内容长度 ≥ 50 字符

**force 选项：**
支持 `force=True` 强制添加不符合标准的源

---

## 3. 数据模型

### 3.1 Source 模型扩展

```python
# src/cyberpulse/models/source.py

class Source(Base, TimestampMixin):
    # 现有字段...

    # 新增：全文获取配置
    needs_full_fetch = Column(Boolean, nullable=False, default=False)
    full_fetch_threshold = Column(Float, nullable=True, default=0.7)

    # 新增：源质量标记
    content_type = Column(String(20), nullable=True)  # 'full' | 'summary' | 'mixed'
    avg_content_length = Column(Integer, nullable=True)
    quality_score = Column(Float, nullable=True, default=50.0)

    # 新增：统计信息
    full_fetch_success_count = Column(Integer, nullable=False, default=0)
    full_fetch_failure_count = Column(Integer, nullable=False, default=0)
```

### 3.2 Item 模型扩展

```python
# src/cyberpulse/models/item.py

class Item(Base, TimestampMixin):
    # 现有字段...

    # 新增：全文获取状态
    full_fetch_attempted = Column(Boolean, nullable=False, default=False)
    full_fetch_succeeded = Column(Boolean, nullable=True)
```

### 3.3 数据库迁移

```python
# alembic/versions/xxx_add_full_fetch_fields.py

def upgrade():
    # Source 表新增字段
    op.add_column('sources', sa.Column('needs_full_fetch', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('sources', sa.Column('full_fetch_threshold', sa.Float(), nullable=True))
    op.add_column('sources', sa.Column('content_type', sa.String(20), nullable=True))
    op.add_column('sources', sa.Column('avg_content_length', sa.Integer(), nullable=True))
    op.add_column('sources', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column('sources', sa.Column('full_fetch_success_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('sources', sa.Column('full_fetch_failure_count', sa.Integer(), nullable=False, server_default='0'))

    # Item 表新增字段
    op.add_column('items', sa.Column('full_fetch_attempted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('items', sa.Column('full_fetch_succeeded', sa.Boolean(), nullable=True))
```

---

## 4. 服务层设计

### 4.1 FullContentFetchService

```python
# src/cyberpulse/services/full_content_fetch_service.py

@dataclass
class FullContentResult:
    """全文获取结果"""
    content: str
    success: bool
    error: Optional[str] = None


class FullContentFetchService:
    """服务：从原文 URL 获取全文内容"""

    async def fetch_full_content(self, url: str) -> FullContentResult:
        """
        从 URL 获取全文内容

        流程：
        1. 使用 httpx 获取页面内容
        2. 使用 trafilatura 提取正文
        3. 返回提取结果
        """
        pass

    async def fetch_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> FullContentResult:
        """带重试的全文获取"""
        pass
```

### 4.2 SourceQualityValidator

```python
# src/cyberpulse/services/source_quality_validator.py

@dataclass
class SourceValidationResult:
    """源验证结果"""
    is_valid: bool
    content_type: str  # 'article' | 'summary_only' | 'empty'
    sample_completeness: float
    avg_content_length: int
    rejection_reason: Optional[str] = None
    samples_analyzed: int = 0


class SourceQualityValidator:
    """源质量验证器"""

    # 质量标准
    MIN_SAMPLE_ITEMS = 3  # 放宽对低频源的支持
    MIN_AVG_COMPLETENESS = 0.4
    MIN_AVG_CONTENT_LENGTH = 50

    async def validate_source(self, source_config: dict) -> SourceValidationResult:
        """
        验证源是否符合质量标准

        流程：
        1. 采集样本条目（最多 10 条）
        2. 分析样本内容质量
        3. 判断是否符合标准
        """
        pass

    async def validate_source_with_force(
        self,
        source_config: dict,
        force: bool = False
    ) -> SourceValidationResult:
        """
        验证源，支持强制添加

        Args:
            source_config: 源配置
            force: 强制添加，跳过质量验证
        """
        if force:
            return SourceValidationResult(
                is_valid=True,
                content_type='unknown',
                sample_completeness=0.0,
                avg_content_length=0,
            )
        return await self.validate_source(source_config)
```

### 4.3 TitleParserService

```python
# src/cyberpulse/services/title_parser_service.py

@dataclass
class ParsedTitle:
    """解析后的标题"""
    category: Optional[str]
    date: Optional[str]
    title: str
    summary: Optional[str]


class TitleParserService:
    """服务：解析复合标题"""

    # 已知源的标题格式规则
    SOURCE_PATTERNS = {
        "anthropic_research": re.compile(
            r'^(?P<category>[A-Z][a-z]+)'  # 分类（如 Alignment）
            r'(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})?'  # 可选日期
            r'(?P<title>.+?)'  # 标题
            r'(?P<summary>This paper provides.*)?$',  # 可选摘要开头
            re.DOTALL
        ),
    }

    def parse_compound_title(
        self,
        title: str,
        source_name: Optional[str] = None
    ) -> ParsedTitle:
        """
        解析复合标题

        输入: "AlignmentDec 18, 2024Alignment faking in large language models..."
        输出: ParsedTitle(
            category="Alignment",
            date="Dec 18, 2024",
            title="Alignment faking in large language models",
            ...
        )

        流程：
        1. 检查是否有源特定模式
        2. 尝试匹配模式
        3. 回退到默认处理（检测标题中的日期）
        """
        # 尝试源特定模式
        if source_name and source_name.lower().replace(' ', '_') in self.SOURCE_PATTERNS:
            pattern = self.SOURCE_PATTERNS[source_name.lower().replace(' ', '_')]
            if match := pattern.match(title):
                return ParsedTitle(
                    category=match.group('category'),
                    date=match.group('date'),
                    title=match.group('title').strip(),
                    summary=match.group('summary'),
                )

        # 回退：检测标题中的日期模式
        date_pattern = re.compile(
            r'(?P<date>[A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})'
        )
        if match := date_pattern.search(title):
            clean_title = date_pattern.sub('', title).strip()
            return ParsedTitle(
                category=None,
                date=match.group('date'),
                title=clean_title,
                summary=None,
            )

        # 无法解析，返回原始标题
        return ParsedTitle(
            category=None,
            date=None,
            title=title,
            summary=None,
        )
```

### 4.4 QualityGateService 增强

```python
# src/cyberpulse/services/quality_gate_service.py

class QualityGateService:
    # 新增检测规则

    # 标题与正文相同检测
    TITLE_BODY_SIMILARITY_THRESHOLD = 0.95

    # 正文最小长度
    MIN_BODY_LENGTH = 50

    # 标题异常模式（包含日期）
    TITLE_DATE_PATTERN = r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b'

    def _validate_content_quality(self, norm: NormalizationResult) -> List[str]:
        """
        内容质量检测（新增）

        检测项：
        1. 标题与正文相似度 > 95%
        2. 正文长度 < 50 字符
        3. 标题包含日期模式
        """
        warnings = []

        # 检测标题=正文
        if self._is_title_body_same(norm.normalized_title, norm.normalized_body):
            warnings.append("标题与正文相同，可能需要全文获取")

        # 检测正文过短
        if len(norm.normalized_body) < self.MIN_BODY_LENGTH:
            warnings.append(f"正文过短（{len(norm.normalized_body)} 字符），建议获取全文")

        # 检测标题格式异常
        if re.search(self.TITLE_DATE_PATTERN, norm.normalized_title):
            warnings.append("标题包含日期，可能存在解析问题")

        return warnings
```

---

## 5. Dramatiq 任务设计

### 5.1 fetch_full_content 任务

```python
# src/cyberpulse/tasks/full_content_tasks.py

@dramatiq.actor(max_retries=3)
def fetch_full_content(item_id: str) -> None:
    """
    获取全文内容

    触发条件：quality_check_item 发现 content_completeness < threshold

    流程：
    1. 获取 Item 和 Source 信息
    2. 检查是否已尝试过全文获取
    3. 调用 FullContentFetchService 获取全文
    4. 如果成功，触发重新标准化
    5. 如果失败，标记 full_fetch_attempted=True, full_fetch_succeeded=False
    6. 更新源治理统计，失败率过高时标记源需要审查
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        source = item.source

        # 检查是否已尝试过
        if item.full_fetch_attempted:
            logger.info(f"Full fetch already attempted for item: {item_id}")
            return

        # 获取全文
        fetch_service = FullContentFetchService()
        result = await fetch_service.fetch_full_content(item.url)

        item.full_fetch_attempted = True

        # 更新源治理统计
        if source:
            if result.success:
                source.full_fetch_success_count += 1
            else:
                source.full_fetch_failure_count += 1

            # 计算失败率，过高时标记需要审查
            total = source.full_fetch_success_count + source.full_fetch_failure_count
            if total >= 10 and source.full_fetch_failure_count / total > 0.5:
                source.pending_review = True
                source.review_reason = "全文获取失败率过高"

        if result.success:
            item.raw_content = result.content
            item.full_fetch_succeeded = True
            db.commit()

            # 触发重新标准化
            normalize_actor = broker.get_actor("normalize_item")
            normalize_actor.send(item_id)
        else:
            item.full_fetch_succeeded = False
            db.commit()
            # 失败后保持原始内容，由原质量规则处理
            logger.warning(f"Full fetch failed for item {item_id}: {result.error}")

    except Exception as e:
        logger.error(f"Full fetch failed for item {item_id}: {e}")
        db.rollback()
        raise
    finally:
        db.close()
```

### 5.2 quality_check_item 任务修改

```python
# src/cyberpulse/tasks/quality_tasks.py

@dramatiq.actor(max_retries=3)
def quality_check_item(
    item_id: str,
    normalized_title: str,
    normalized_body: str,
    canonical_hash: str,
    language: Optional[str] = None,
    word_count: int = 0,
    extraction_method: str = "trafilatura",
) -> None:
    """质量检查任务（修改）

    关键变更：从数据库查询 Source 获取全文获取配置，而非通过参数传递
    """
    db = SessionLocal()
    try:
        item = db.query(Item).filter(Item.item_id == item_id).first()
        if not item:
            logger.error(f"Item not found: {item_id}")
            return

        # 从数据库查询 Source 获取配置
        source = item.source  # 通过关系获取

        # 获取全文获取配置
        needs_full_fetch = source.needs_full_fetch if source else False
        threshold = source.full_fetch_threshold if source else 0.7

        # ... 现有质量检查逻辑 ...

        # 新增：检测内容质量问题
        quality_warnings = quality_service._validate_content_quality(normalization_result)

        # 新增：如果源需要全文获取且内容不完整，触发全文获取
        if (needs_full_fetch and
            quality_result.metrics.get("content_completeness", 1.0) < threshold and
            not item.full_fetch_attempted):

            logger.info(f"Triggering full content fetch for item: {item_id}")
            fetch_actor = broker.get_actor("fetch_full_content")
            fetch_actor.send(item_id)
            return  # 等待全文获取完成
```

---

## 6. 测试策略

### 6.1 已知问题源测试用例

| 测试场景 | 测试源 | 测试目的 |
|---------|-------|---------|
| 标题=正文 | Anthropic Research | 验证 `_is_title_body_same()` 检测 |
| 内容极短 | danielwirtz.com | 验证全文获取触发 |
| RSS 无正文 | paulgraham.com | 验证源准入拒绝 |
| 高质量源 | krebsonsecurity.com | 验证正常通过 |
| 复合标题 | Anthropic Research | 验证标题解析服务 |
| 中文内容 | 字节跳动安全中心 | 验证中文处理 |

### 6.2 测试用例实现

```python
# tests/fixtures/rss_samples.py

RSS_SAMPLES = {
    "anthropic_research": {
        "url": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
        "expected_issues": ["title_eq_body", "compound_title"],
        "expected_action": "fetch_full_content",
    },
    "danielwirtz": {
        "url": "https://danielwirtz.com/rss.xml",
        "expected_issues": ["body_too_short"],
        "expected_action": "fetch_full_content",
    },
    "paulgraham": {
        "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss",
        "expected_issues": ["empty_content"],
        "expected_action": "reject_source",
    },
    "krebsonsecurity": {
        "url": "https://krebsonsecurity.com/feed/",
        "expected_issues": [],
        "expected_action": "pass",
    },
}

# tests/test_services/test_source_quality_validator.py

class TestSourceQualityValidatorWithRealSources:
    """使用真实问题源测试"""

    @pytest.mark.parametrize("source_name,expected", RSS_SAMPLES.items())
    async def test_source_validation(self, source_name, expected):
        """验证各类源的质量检测结果"""
        validator = SourceQualityValidator()
        result = await validator.validate_source({"feed_url": expected["url"]})

        if expected["expected_action"] == "pass":
            assert result.is_valid == True
        elif expected["expected_action"] == "reject_source":
            assert result.is_valid == False
```

### 6.3 测试类型

| 测试类型 | 覆盖范围 |
|---------|---------|
| 单元测试 | FullContentFetchService, SourceQualityValidator, QualityGateService, TitleParserService |
| 集成测试 | 全文获取流程、源验证流程 |
| 端到端测试 | 完整采集流程 |

---

## 7. 实施计划

### 7.1 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/cyberpulse/models/source.py` | 修改 | 新增全文获取相关字段 |
| `src/cyberpulse/models/item.py` | 修改 | 新增全文获取状态字段 |
| `src/cyberpulse/services/full_content_fetch_service.py` | 新增 | 全文获取服务 |
| `src/cyberpulse/services/source_quality_validator.py` | 新增 | 源质量验证器 |
| `src/cyberpulse/services/title_parser_service.py` | 新增 | 复合标题解析服务 |
| `src/cyberpulse/services/quality_gate_service.py` | 修改 | 增强内容质量检测 |
| `src/cyberpulse/services/rss_connector.py` | 修改 | 优化内容提取逻辑 |
| `src/cyberpulse/tasks/full_content_tasks.py` | 新增 | 全文获取 Dramatiq 任务 |
| `src/cyberpulse/tasks/quality_tasks.py` | 修改 | 集成全文获取触发 |
| `alembic/versions/xxx_add_full_fetch_fields.py` | 新增 | 数据库迁移 |
| `tests/test_services/test_full_content_fetch.py` | 新增 | 单元测试 |
| `tests/test_services/test_source_quality_validator.py` | 新增 | 单元测试 |
| `tests/test_integration/test_full_content_flow.py` | 新增 | 集成测试 |
| `tests/fixtures/rss_samples.py` | 新增 | 测试样本数据 |

### 7.2 实施顺序

```
Phase 1: 数据模型 (Day 1)
├── Source 模型扩展
├── Item 模型扩展
└── 数据库迁移

Phase 2: 服务层 (Day 2-3)
├── FullContentFetchService
├── SourceQualityValidator
├── TitleParserService
└── QualityGateService 增强

Phase 3: 任务层 (Day 4)
├── fetch_full_content 任务
├── quality_check_item 修改
└── 任务流程集成

Phase 4: 测试 (Day 5)
├── 单元测试
├── 集成测试
└── 端到端验证
```

---

## 8. 相关文档

- Issue #41: RSS 采集内容不完整且标题正文混淆
- Issue #46: 部分 RSS 源只提供标题链接，无正文内容
- `issues/2026-03-24-rss-no-content.md`
- `issues/2026-03-24-content-incomplete.md`
- `issues/2026-03-24-content-quality-report.md`
- `issues/2026-03-24-rss-content-fetch-architecture.md`