# Issue #63 修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 #63 中的设计缺陷，删除无效的 noise_ratio 字段和 language 相关代码，统一 HTTP 请求头

**Architecture:** 分三个独立模块处理：1) noise_ratio 删除（模型、服务、任务层）；2) language 清理（规范化服务、任务层）；3) HTTP 请求头统一（新建共享模块，更新各 connector）

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, Alembic, FastAPI, pytest

---

## 文件结构

### 新建文件
- `src/cyberpulse/services/http_headers.py` - 共享 HTTP 请求头模块

### 修改文件
- `src/cyberpulse/models/item.py` - 删除 noise_ratio 字段
- `src/cyberpulse/services/quality_gate_service.py` - 删除 noise_ratio 相关代码
- `src/cyberpulse/services/item_service.py` - 删除 noise_ratio 赋值
- `src/cyberpulse/services/source_score_service.py` - 更新质量计算公式
- `src/cyberpulse/api/routers/items.py` - 更新 completeness_score 计算
- `src/cyberpulse/services/normalization_service.py` - 删除 language 相关代码
- `src/cyberpulse/tasks/normalization_tasks.py` - 删除 language 相关代码
- `src/cyberpulse/tasks/quality_tasks.py` - 删除 language 和 noise_ratio 相关代码
- `src/cyberpulse/services/rss_connector.py` - 使用共享请求头
- `src/cyberpulse/services/web_connector.py` - 使用共享请求头
- `src/cyberpulse/services/full_content_fetch_service.py` - 使用共享请求头

### 测试文件
- `tests/test_services/test_quality_gate_service.py` - 移除 noise_ratio 测试
- `tests/test_services/test_item_service.py` - 移除 noise_ratio 断言
- `tests/test_services/test_source_score_service.py` - 更新质量计算测试
- `tests/test_integration/test_e2e.py` - 移除 language 断言

---

## Task 1: 创建共享 HTTP 请求头模块

**Files:**
- Create: `src/cyberpulse/services/http_headers.py`

- [ ] **Step 1: 创建 http_headers.py 模块**

```python
"""Shared HTTP headers for browser-like requests."""

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def get_browser_headers(custom: dict | None = None) -> dict[str, str]:
    """Get browser-like headers for HTTP requests.

    Args:
        custom: Optional custom headers to merge.

    Returns:
        Dictionary of HTTP headers.
    """
    headers = DEFAULT_HEADERS.copy()
    if custom:
        headers.update(custom)
    return headers
```

- [ ] **Step 2: 验证模块可导入**

Run: `uv run python -c "from cyberpulse.services.http_headers import get_browser_headers, DEFAULT_USER_AGENT; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/services/http_headers.py
git commit -m "feat(services): add shared HTTP headers module for browser-like requests"
```

---

## Task 2: 更新 RSS Connector 使用共享请求头

**Files:**
- Modify: `src/cyberpulse/services/rss_connector.py`

- [ ] **Step 1: 更新 imports 和移除本地 DEFAULT_USER_AGENT**

将第 36-40 行的本地 `DEFAULT_USER_AGENT` 替换为导入共享模块：

```python
# 在文件顶部 imports 区域添加
from .http_headers import get_browser_headers

# 删除第 36-40 行的本地 DEFAULT_USER_AGENT 定义
```

- [ ] **Step 2: 更新 fetch 方法中的 headers 使用**

将第 85-88 行：

```python
response = await client.get(
    feed_url,
    headers={"User-Agent": self.DEFAULT_USER_AGENT},
)
```

替换为：

```python
response = await client.get(
    feed_url,
    headers=get_browser_headers(),
)
```

- [ ] **Step 3: 运行测试验证**

Run: `uv run pytest tests/test_services/test_rss_connector.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/services/rss_connector.py
git commit -m "refactor(rss): use shared browser headers module"
```

---

## Task 3: 更新 Web Scraper Connector 使用共享请求头

**Files:**
- Modify: `src/cyberpulse/services/web_connector.py`

- [ ] **Step 1: 添加导入**

在文件顶部 imports 区域添加：

```python
from .http_headers import get_browser_headers
```

- [ ] **Step 2: 更新 _build_headers 方法**

将第 254-273 行的 `_build_headers` 方法替换为：

```python
def _build_headers(self) -> dict[str, str]:
    """Build HTTP headers for requests.

    Returns:
        Dictionary of headers
    """
    # Use shared browser headers as base
    headers = get_browser_headers()

    # Allow config override for user_agent
    if user_agent := self.config.get("user_agent"):
        headers["User-Agent"] = user_agent

    # Add custom headers from config
    custom_headers = self.config.get("headers", {})
    headers.update(custom_headers)

    return headers
```

- [ ] **Step 3: 运行测试验证**

Run: `uv run pytest tests/test_services/test_web_connector.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/services/web_connector.py
git commit -m "refactor(web): use shared browser headers module"
```

---

## Task 4: 更新 Full Content Fetch Service 使用共享请求头

**Files:**
- Modify: `src/cyberpulse/services/full_content_fetch_service.py`

- [ ] **Step 1: 添加导入并移除本地 DEFAULT_USER_AGENT**

在 imports 区域添加：

```python
from .http_headers import get_browser_headers
```

删除第 36-40 行的本地 `DEFAULT_USER_AGENT` 定义。

- [ ] **Step 2: 更新 _fetch_level1 方法中的 headers**

将第 83-87 行：

```python
response = await client.get(
    url,
    follow_redirects=True,
    headers={"User-Agent": self.DEFAULT_USER_AGENT},
)
```

替换为：

```python
response = await client.get(
    url,
    follow_redirects=True,
    headers=get_browser_headers(),
)
```

- [ ] **Step 3: 运行测试验证**

Run: `uv run pytest tests/test_services/test_full_content_fetch_service.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/cyberpulse/services/full_content_fetch_service.py
git commit -m "refactor(full-content): use shared browser headers module"
```

---

## Task 5: 删除 NormalizationResult.language 字段和 _detect_language 方法

**Files:**
- Modify: `src/cyberpulse/services/normalization_service.py`

- [ ] **Step 1: 删除 NormalizationResult.language 字段**

将第 13-22 行：

```python
@dataclass(frozen=True)
class NormalizationResult:
    """Result of content normalization."""

    normalized_title: str
    normalized_body: str  # Markdown format
    canonical_hash: str  # For deduplication
    language: str | None
    word_count: int
    extraction_method: str  # "trafilatura" | "raw"
```

替换为：

```python
@dataclass(frozen=True)
class NormalizationResult:
    """Result of content normalization."""

    normalized_title: str
    normalized_body: str  # Markdown format
    canonical_hash: str  # For deduplication
    word_count: int
    extraction_method: str  # "trafilatura" | "raw"
```

- [ ] **Step 2: 删除 normalize 方法中的 language 检测调用**

删除第 67-68 行：

```python
        # Detect language
        language = self._detect_language(markdown_body)
```

- [ ] **Step 3: 更新 NormalizationResult 构造，移除 language 参数**

将第 73-80 行：

```python
        return NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=markdown_body,
            canonical_hash=canonical_hash,
            language=language,
            word_count=word_count,
            extraction_method=extraction_method,
        )
```

替换为：

```python
        return NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=markdown_body,
            canonical_hash=canonical_hash,
            word_count=word_count,
            extraction_method=extraction_method,
        )
```

- [ ] **Step 4: 删除 _detect_language 方法**

删除第 191-259 行的整个 `_detect_language` 方法。

- [ ] **Step 5: 运行测试验证**

Run: `uv run pytest tests/test_services/test_normalization_service.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/cyberpulse/services/normalization_service.py
git commit -m "refactor(normalization): remove unused language detection"
```

---

## Task 6: 清理 normalization_tasks.py 中的 language 相关代码

**Files:**
- Modify: `src/cyberpulse/tasks/normalization_tasks.py`

- [ ] **Step 1: 删除日志中的 language 输出**

将第 59-63 行：

```python
        logger.debug(
            f"Normalization complete for {item_id}: "
            f"word_count={result.word_count}, "
            f"language={result.language}"
        )
```

替换为：

```python
        logger.debug(
            f"Normalization complete for {item_id}: "
            f"word_count={result.word_count}"
        )
```

- [ ] **Step 2: 删除 item.language 赋值（normalize_item 函数）**

删除第 93 行：

```python
        item.language = result.language  # type: ignore[assignment]
```

- [ ] **Step 3: 删除 quality_check_item.send 中的 language 参数**

将第 105-114 行：

```python
        quality_actor.send(
            item_id=item_id,
            normalized_title=normalized_title,
            normalized_body=result.normalized_body,
            canonical_hash=result.canonical_hash,
            language=result.language,
            word_count=result.word_count,
            extraction_method=result.extraction_method,
        )
```

替换为：

```python
        quality_actor.send(
            item_id=item_id,
            normalized_title=normalized_title,
            normalized_body=result.normalized_body,
            canonical_hash=result.canonical_hash,
            word_count=result.word_count,
            extraction_method=result.extraction_method,
        )
```

- [ ] **Step 4: 删除 normalize_item_with_result 中的 item.language 赋值**

删除第 182 行：

```python
        item.language = result.language  # type: ignore[assignment]
```

- [ ] **Step 5: 删除返回值中的 language**

将第 187-195 行：

```python
        return {
            "item_id": item_id,
            "normalized_title": normalized_title,
            "normalized_body": result.normalized_body,
            "canonical_hash": result.canonical_hash,
            "language": result.language,
            "word_count": result.word_count,
            "extraction_method": result.extraction_method,
        }
```

替换为：

```python
        return {
            "item_id": item_id,
            "normalized_title": normalized_title,
            "normalized_body": result.normalized_body,
            "canonical_hash": result.canonical_hash,
            "word_count": result.word_count,
            "extraction_method": result.extraction_method,
        }
```

- [ ] **Step 6: 运行 mypy 验证**

Run: `uv run mypy src/cyberpulse/tasks/normalization_tasks.py --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add src/cyberpulse/tasks/normalization_tasks.py
git commit -m "fix(tasks): remove invalid language assignments from normalization tasks"
```

---

## Task 7: 清理 quality_tasks.py 中的 language 和 noise_ratio 相关代码

**Files:**
- Modify: `src/cyberpulse/tasks/quality_tasks.py`

- [ ] **Step 1: 删除 quality_check_item 函数的 language 参数**

将第 18-26 行：

```python
def quality_check_item(
    item_id: str,
    normalized_title: str,
    normalized_body: str,
    canonical_hash: str,
    language: str | None = None,
    word_count: int = 0,
    extraction_method: str = "trafilatura",
) -> None:
```

替换为：

```python
def quality_check_item(
    item_id: str,
    normalized_title: str,
    normalized_body: str,
    canonical_hash: str,
    word_count: int = 0,
    extraction_method: str = "trafilatura",
) -> None:
```

- [ ] **Step 2: 删除 NormalizationResult 构造中的 language**

将第 59-66 行：

```python
        normalization_result = NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            canonical_hash=canonical_hash,
            language=language,
            word_count=word_count,
            extraction_method=extraction_method,
        )
```

替换为：

```python
        normalization_result = NormalizationResult(
            normalized_title=normalized_title,
            normalized_body=normalized_body,
            canonical_hash=canonical_hash,
            word_count=word_count,
            extraction_method=extraction_method,
        )
```

- [ ] **Step 3: 删除 _handle_pass 中的 item.language 和 noise_ratio 赋值**

将第 161-171 行：

```python
    # Update item with normalized content and quality metrics
    source = getattr(item, "source", None)
    item.status = ItemStatus.MAPPED  # type: ignore[assignment]
    item.normalized_title = normalization_result.normalized_title
    item.normalized_body = normalization_result.normalized_body
    item.canonical_hash = normalization_result.canonical_hash
    item.language = normalization_result.language
    item.word_count = normalization_result.word_count
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")
```

替换为：

```python
    # Update item with normalized content and quality metrics
    source = getattr(item, "source", None)
    item.status = ItemStatus.MAPPED  # type: ignore[assignment]
    item.normalized_title = normalization_result.normalized_title
    item.normalized_body = normalization_result.normalized_body
    item.canonical_hash = normalization_result.canonical_hash
    item.word_count = normalization_result.word_count
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
```

- [ ] **Step 4: 删除 _handle_reject 中的 noise_ratio 赋值**

将第 209-222 行：

```python
    item.status = ItemStatus.REJECTED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")
    item.noise_ratio = quality_result.metrics.get("noise_ratio")

    # Store rejection reason in raw_metadata
```

替换为：

```python
    item.status = ItemStatus.REJECTED  # type: ignore[assignment]
    item.meta_completeness = quality_result.metrics.get("meta_completeness")
    item.content_completeness = quality_result.metrics.get("content_completeness")

    # Store rejection reason in raw_metadata
```

- [ ] **Step 5: 运行 mypy 验证**

Run: `uv run mypy src/cyberpulse/tasks/quality_tasks.py --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add src/cyberpulse/tasks/quality_tasks.py
git commit -m "fix(tasks): remove invalid language and noise_ratio assignments from quality tasks"
```

---

## Task 8: 删除 quality_gate_service.py 中的 noise_ratio 相关代码

**Files:**
- Modify: `src/cyberpulse/services/quality_gate_service.py`

- [ ] **Step 1: 删除 AD_MARKERS 常量**

删除第 64-74 行：

```python
    # Noise ratio ad markers (Chinese and English)
    AD_MARKERS = [
        "广告",
        "推广",
        "推荐阅读",
        "AD",
        "advertisement",
        "sponsored",
        "赞助",
        "合作",
    ]
```

- [ ] **Step 2: 更新 _calculate_metrics 方法，移除 noise_ratio 计算**

将第 178-219 行的 `_calculate_metrics` 方法替换为：

```python
    def _calculate_metrics(
        self, item: "Item", norm: "NormalizationResult"
    ) -> dict[str, float]:
        """Calculate quality metrics.

        Metrics calculated:
        - title_length: Title character count
        - body_length: Body character count
        - word_count: Word count (from NormalizationResult)
        - meta_completeness: Metadata completeness score (0-1)
        - content_completeness: Content quality score (0-1)

        Args:
            item: Item model instance
            norm: NormalizationResult instance

        Returns:
            Dictionary of metric name to value
        """
        metrics = {}

        # Title length
        metrics["title_length"] = float(len(norm.normalized_title or ""))

        # Body length
        body = norm.normalized_body or ""
        metrics["body_length"] = float(len(body))

        # Word count (from normalization result)
        metrics["word_count"] = float(norm.word_count or 0)

        # Meta completeness (author, tags, published_at)
        metrics["meta_completeness"] = self._calculate_meta_completeness(item)

        # Content completeness (based on body length)
        metrics["content_completeness"] = self._calculate_content_completeness(body)

        return metrics
```

- [ ] **Step 3: 删除 _calculate_noise_ratio 方法**

删除第 330-365 行的整个 `_calculate_noise_ratio` 方法。

- [ ] **Step 4: 运行测试验证**

Run: `uv run pytest tests/test_services/test_quality_gate_service.py -v`
Expected: Some tests may fail due to noise_ratio assertions (will fix in Task 12)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/quality_gate_service.py
git commit -m "refactor(quality): remove flawed noise_ratio calculation"
```

---

## Task 9: 删除 item_service.py 中的 noise_ratio 赋值

**Files:**
- Modify: `src/cyberpulse/services/item_service.py`

- [ ] **Step 1: 删除 update_item_status 中的 noise_ratio 赋值**

将第 176-182 行：

```python
        if quality_metrics:
            if "meta_completeness" in quality_metrics:
                item.meta_completeness = quality_metrics["meta_completeness"]
            if "content_completeness" in quality_metrics:
                item.content_completeness = quality_metrics["content_completeness"]
            if "noise_ratio" in quality_metrics:
                item.noise_ratio = quality_metrics["noise_ratio"]
```

替换为：

```python
        if quality_metrics:
            if "meta_completeness" in quality_metrics:
                item.meta_completeness = quality_metrics["meta_completeness"]
            if "content_completeness" in quality_metrics:
                item.content_completeness = quality_metrics["content_completeness"]
```

- [ ] **Step 2: 运行测试验证**

Run: `uv run pytest tests/test_services/test_item_service.py -v`
Expected: Some tests may fail due to noise_ratio assertions (will fix in Task 13)

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/services/item_service.py
git commit -m "refactor(item): remove noise_ratio assignment from update_item_status"
```

---

## Task 10: 更新 source_score_service.py 质量计算公式

**Files:**
- Modify: `src/cyberpulse/services/source_score_service.py`

- [ ] **Step 1: 更新 QUALITY_WEIGHTS 常量**

将第 58-61 行：

```python
    QUALITY_WEIGHTS = {
        "meta_completeness": 0.4,
        "content_completeness": 0.4,
        "noise_ratio": 0.2,  # Applied as (1 - noise_ratio)
    }
```

替换为：

```python
    QUALITY_WEIGHTS = {
        "meta_completeness": 0.5,
        "content_completeness": 0.5,
    }
```

- [ ] **Step 2: 更新 calculate_quality 方法的文档字符串**

将第 176-181 行的文档字符串：

```python
        """Calculate content quality (Cq).

        Quality is based on item quality metrics from normalized items.
        Cq = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
```

替换为：

```python
        """Calculate content quality (Cq).

        Quality is based on item quality metrics from normalized items.
        Cq = meta_completeness * 0.5 + content_completeness * 0.5
```

- [ ] **Step 3: 更新 calculate_quality 方法的查询和计算**

将第 189-221 行：

```python
        items = (
            self.db.query(
                func.avg(Item.meta_completeness).label("avg_meta"),
                func.avg(Item.content_completeness).label("avg_content"),
                func.avg(Item.noise_ratio).label("avg_noise"),
                func.count(Item.item_id).label("count"),
            )
            .filter(
                Item.source_id == source_id,
                Item.meta_completeness.isnot(None),
                Item.content_completeness.isnot(None),
                Item.noise_ratio.isnot(None),
            )
            .first()
        )

        if items is None or items.count == 0:
            return self.DEFAULT_QUALITY

        # Calculate quality components
        avg_meta = items.avg_meta or 0.0
        avg_content = items.avg_content or 0.0
        avg_noise = items.avg_noise or 0.0

        # Cq = meta_completeness * 0.4 + content_completeness * 0.4 + (1 - noise_ratio) * 0.2
        quality = (
            avg_meta * self.QUALITY_WEIGHTS["meta_completeness"]
            + avg_content * self.QUALITY_WEIGHTS["content_completeness"]
            + (1 - avg_noise) * self.QUALITY_WEIGHTS["noise_ratio"]
        )

        # Clamp to valid range
        return max(0.0, min(1.0, quality))
```

替换为：

```python
        items = (
            self.db.query(
                func.avg(Item.meta_completeness).label("avg_meta"),
                func.avg(Item.content_completeness).label("avg_content"),
                func.count(Item.item_id).label("count"),
            )
            .filter(
                Item.source_id == source_id,
                Item.meta_completeness.isnot(None),
                Item.content_completeness.isnot(None),
            )
            .first()
        )

        if items is None or items.count == 0:
            return self.DEFAULT_QUALITY

        # Calculate quality components
        avg_meta = items.avg_meta or 0.0
        avg_content = items.avg_content or 0.0

        # Cq = meta_completeness * 0.5 + content_completeness * 0.5
        quality = (
            avg_meta * self.QUALITY_WEIGHTS["meta_completeness"]
            + avg_content * self.QUALITY_WEIGHTS["content_completeness"]
        )

        # Clamp to valid range
        return max(0.0, min(1.0, quality))
```

- [ ] **Step 4: 运行测试验证**

Run: `uv run pytest tests/test_services/test_source_score_service.py -v`
Expected: Some tests may fail due to noise_ratio test data (will fix in Task 14)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/source_score_service.py
git commit -m "refactor(score): update quality formula to 50/50 meta/content"
```

---

## Task 11: 更新 items.py router 中的 completeness_score 计算

**Files:**
- Modify: `src/cyberpulse/api/routers/items.py`

- [ ] **Step 1: 更新 calculate_completeness_score 函数**

将第 33-40 行：

```python
def calculate_completeness_score(item: Item) -> float:
    """Calculate completeness score for an item."""
    meta = item.meta_completeness or 0.0
    content = item.content_completeness or 0.0
    noise = item.noise_ratio or 0.0

    score = meta * 0.4 + content * 0.4 + (1 - noise) * 0.2
    return round(score, 3)
```

替换为：

```python
def calculate_completeness_score(item: Item) -> float:
    """Calculate completeness score for an item."""
    meta = item.meta_completeness or 0.0
    content = item.content_completeness or 0.0

    score = meta * 0.5 + content * 0.5
    return round(score, 3)
```

- [ ] **Step 2: 运行 API 测试验证**

Run: `uv run pytest tests/test_api/test_items.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/api/routers/items.py
git commit -m "refactor(api): update completeness_score formula to 50/50"
```

---

## Task 12: 删除 Item 模型的 noise_ratio 字段

**Files:**
- Modify: `src/cyberpulse/models/item.py`

- [ ] **Step 1: 删除 noise_ratio 字段**

删除第 56 行：

```python
    noise_ratio: Mapped[float | None] = mapped_column()
```

- [ ] **Step 2: 运行 mypy 验证**

Run: `uv run mypy src/cyberpulse/models/item.py --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/models/item.py
git commit -m "refactor(models): remove noise_ratio field from Item model"
```

---

## Task 13: 更新测试文件 - test_quality_gate_service.py

**Files:**
- Modify: `tests/test_services/test_quality_gate_service.py`

- [ ] **Step 1: 删除 test_calculate_metrics 中的 noise_ratio 断言**

找到 `test_calculate_metrics` 相关测试，删除所有 `noise_ratio` 相关断言：

删除第 299 行：
```python
        assert "noise_ratio" in metrics
```

删除第 306 行：
```python
        assert 0.0 <= metrics["noise_ratio"] <= 1.0
```

- [ ] **Step 2: 删除 test_calculate_metrics_noise_ratio_clean 测试方法**

删除整个测试方法（约第 372-381 行）：

```python
    def test_calculate_metrics_noise_ratio_clean(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio low for clean content."""
        valid_item.raw_content = "This is clean text content without HTML or ads."

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # Clean text should have low noise ratio
        assert metrics["noise_ratio"] < 0.1
```

- [ ] **Step 3: 删除 test_calculate_metrics_noise_ratio_html 测试方法**

删除整个测试方法（约第 383-401 行）：

```python
    def test_calculate_metrics_noise_ratio_html(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio higher for HTML with ad markers."""
        valid_item.raw_content = """
        <html><body>
        <div class="ad">广告</div>
        ...
        assert metrics["noise_ratio"] > 0
```

- [ ] **Step 4: 删除 test_calculate_metrics_empty_raw_content 测试方法**

该测试专门测试 `noise_ratio` 行为，删除 `noise_ratio` 后整个测试失去意义。

删除整个测试方法（约第 402-411 行）：

```python
    def test_calculate_metrics_empty_raw_content(
        self, quality_gate_service, valid_item, valid_normalization_result
    ):
        """Test noise_ratio handles empty raw_content."""
        valid_item.raw_content = None

        metrics = quality_gate_service._calculate_metrics(valid_item, valid_normalization_result)

        # Should handle None gracefully
        assert metrics["noise_ratio"] == 0.0
```

- [ ] **Step 5: 运行测试验证**

Run: `uv run pytest tests/test_services/test_quality_gate_service.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_services/test_quality_gate_service.py
git commit -m "test(quality): remove noise_ratio test cases"
```

---

## Task 14: 更新测试文件 - test_item_service.py

**Files:**
- Modify: `tests/test_services/test_item_service.py`

- [ ] **Step 1: 更新 test_update_item_status_with_quality_metrics 测试**

删除第 273 行和第 284 行的 `noise_ratio` 相关代码：

```python
# 删除
            "noise_ratio": 0.05,
# 和
        assert updated.noise_ratio == 0.05
```

- [ ] **Step 2: 更新 test_update_item_status_partial_metrics 测试**

删除第 310 行：

```python
        assert updated.noise_ratio is None
```

- [ ] **Step 3: 运行测试验证**

Run: `uv run pytest tests/test_services/test_item_service.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_services/test_item_service.py
git commit -m "test(item): remove noise_ratio assertions"
```

---

## Task 15: 更新测试文件 - test_source_score_service.py

**Files:**
- Modify: `tests/test_services/test_source_score_service.py`

- [ ] **Step 1: 更新所有测试中的 Item 创建，移除 noise_ratio 参数**

在每个测试中找到包含 `noise_ratio` 的 Item 创建，移除该字段。例如：

第 59 行：
```python
            noise_ratio=0.1,
```

第 226 行：
```python
            noise_ratio=0.0,
```

第 240 行：
```python
            noise_ratio=0.5,
```

等等，移除所有 `noise_ratio=...` 行。

- [ ] **Step 2: 运行测试验证**

Run: `uv run pytest tests/test_services/test_source_score_service.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_services/test_source_score_service.py
git commit -m "test(score): update tests for 50/50 quality formula"
```

---

## Task 16: 更新测试文件 - test_e2e.py

**Files:**
- Modify: `tests/test_integration/test_e2e.py`

- [ ] **Step 1: 删除 test_rss_source_to_item_flow 中的 noise_ratio 断言**

删除第 173 行：
```python
        assert "noise_ratio" in quality_result.metrics
```

- [ ] **Step 2: 删除 test_rss_source_to_item_flow 中的 language 相关代码**

删除第 180 行：
```python
        item.language = normalization_result.language
```

删除第 187 行：
```python
                "noise_ratio": quality_result.metrics["noise_ratio"],
```

删除第 197 行：
```python
        assert item.language == normalization_result.language
```

- [ ] **Step 3: 删除 test_duplicate_item_deduplication 中的 language 相关代码**

删除第 255 行和第 287 行：
```python
        item1.language = normalization_result.language
        item2.language = normalization_result.language
```

- [ ] **Step 4: 删除 test_full_flow_to_item_normalization 中的 language 相关代码**

删除第 439 行和第 448 行：
```python
        item.language = normalization_result.language
        assert item.language == normalization_result.language
```

- [ ] **Step 5: 运行测试验证**

Run: `uv run pytest tests/test_integration/test_e2e.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_integration/test_e2e.py
git commit -m "test(e2e): remove language and noise_ratio assertions"
```

---

## Task 17: 创建数据库迁移

**Files:**
- Create: Alembic migration file

- [ ] **Step 1: 生成迁移文件**

Run: `uv run alembic revision --autogenerate -m "remove noise_ratio from items"`
Expected: 新迁移文件生成于 `alembic/versions/` 目录

- [ ] **Step 2: 检查迁移文件内容**

Run: `cat alembic/versions/*remove_noise_ratio*.py`
Expected: 包含 `op.drop_column('items', 'noise_ratio')`

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "db: add migration to remove noise_ratio from items table"
```

---

## Task 18: 运行完整测试套件

**Files:**
- None (verification only)

- [ ] **Step 1: 运行全部测试**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: 运行 mypy 类型检查**

Run: `uv run mypy src/ --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 3: 运行 ruff lint 检查**

Run: `uv run ruff check src/ tests/`
Expected: No errors

---

## Task 19: 创建 Pull Request

**Files:**
- None

- [ ] **Step 1: 推送分支**

```bash
git push -u origin feature/issue-63-fix
```

- [ ] **Step 2: 创建 PR**

```bash
gh pr create --title "fix: remove noise_ratio field and language code, unify HTTP headers" --body "$(cat <<'EOF'
## Summary

- Remove flawed `noise_ratio` field from Item model and all related code
- Remove orphaned `language` detection code (field never existed in model)
- Create shared `http_headers` module for unified browser-like request headers
- Update quality score formula from 40/40/20 to 50/50 (meta/content)

## Test Plan

- [ ] All unit tests pass
- [ ] mypy type check passes (fixes #80)
- [ ] Database migration tested locally
- [ ] API responses no longer contain noise_ratio

Fixes #63, #80
EOF
)"
```

---

## Self-Review Checklist

**1. Spec Coverage:**
- [x] noise_ratio 字段删除 - Task 8, 9, 10, 11, 12
- [x] noise_ratio 测试更新 - Task 13, 14, 15, 16
- [x] language 代码清理 - Task 5, 6, 7
- [x] HTTP headers 统一 - Task 1, 2, 3, 4
- [x] 数据库迁移 - Task 17
- [x] 完整测试验证 - Task 18

**2. Placeholder Scan:**
- 无 TBD、TODO 或占位符

**3. Type Consistency:**
- NormalizationResult 在 Task 5 更新后，Task 6、7 引用一致
- QUALITY_WEIGHTS 在 Task 10 更新后，引用一致