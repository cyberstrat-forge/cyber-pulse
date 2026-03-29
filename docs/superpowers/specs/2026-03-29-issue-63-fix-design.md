# Issue #63 修复设计方案

## 概述

**目标**: 修复 #63 中识别的多个问题，清理无效代码，提升采集兼容性

**相关 Issue**: #63, #80

**变更范围**: 模型字段删除、代码清理、请求头统一

---

## 问题分析

| 问题 | 当前状态 | 决策 |
|------|----------|------|
| a) 源状态更新 | 部分实现（5次失败才FROZEN） | 保持现状 |
| b) noise_ratio = 0 | 设计缺陷（基于已清理文本计算） | 删除字段 |
| c) User-Agent 403 | 部分网站仍有问题 | 统一请求头 |
| d) 全文拉取触发 | 已正确实现 | 关闭问题 |
| language 字段 | 模型缺失但代码赋值 | 清除代码 |

---

## 详细设计

### 1. 删除 noise_ratio 字段

**原因**: `_calculate_noise_ratio()` 基于 `raw_content` 计算，但 `raw_content` 是 trafilatura 提取后的纯文本，HTML 标签已被移除，导致结果始终接近 0。

**变更内容**:

| 文件 | 变更 |
|------|------|
| `models/item.py` | 删除 `noise_ratio` 字段 |
| `services/quality_gate_service.py` | 删除 `_calculate_noise_ratio()` 方法，删除 `AD_MARKERS` 常量 |
| `services/quality_gate_service.py` | `_calculate_metrics()` 中移除 noise_ratio 计算 |
| `tasks/quality_tasks.py` | 删除 `noise_ratio` 赋值 |
| `api/schemas/item.py` | 删除 `noise_ratio` 字段（如存在） |

**数据库迁移**: 需要 Alembic 迁移删除列

---

### 2. 清除 language 相关代码

**原因**: `Item` 模型没有 `language` 字段，但代码中多处尝试设置，导致运行时无效操作和 mypy 错误。

**变更内容**:

| 文件 | 变更 |
|------|------|
| `services/normalization_service.py` | 删除 `_detect_language()` 方法，删除 `NormalizationResult.language` 字段 |
| `services/normalization_service.py` | `normalize()` 方法中移除语言检测调用 |
| `tasks/normalization_tasks.py` | 删除 `item.language` 赋值（2处），删除日志中的 language 输出 |
| `tasks/quality_tasks.py` | 删除 `language` 参数，删除 `item.language` 赋值，删除 `NormalizationResult` 中的 language 传递 |

**影响**: 修复 #80 中的 2 个 mypy 错误

---

### 3. 统一请求头

**原因**: 各 connector 使用不同的 User-Agent，部分网站返回 403 Forbidden。

**实现**: 创建共享的请求头构建模块

```python
# src/cyberpulse/services/http_headers.py
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

**更新文件**:

| 文件 | 变更 |
|------|------|
| `services/rss_connector.py` | 导入 `get_browser_headers`，替换硬编码的 `DEFAULT_USER_AGENT` 和 headers |
| `services/web_connector.py` | 导入 `get_browser_headers`，更新 `_build_headers()` 方法 |
| `services/full_content_fetch_service.py` | 导入 `get_browser_headers`，替换硬编码的 `DEFAULT_USER_AGENT` |

---

### 4. 保持不变

**源状态更新机制**:
- 当前行为：5 次连续失败后 FROZEN
- diagnose API 提供 `unhealthy_sources`（`consecutive_failures >= 3`）
- 无需变更

**全文拉取触发机制**:
- 已正确实现于 `ContentQualityService` 和 `quality_tasks.py`
- 触发条件：正文 < 500 字符、词数 < 50、标题-正文相似度 > 80%
- 无需变更

---

## 文件变更清单

### 必须修改

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `models/item.py` | 删除字段 | 删除 `noise_ratio` |
| `services/quality_gate_service.py` | 删除方法 | 删除 `_calculate_noise_ratio()`、`AD_MARKERS` |
| `services/normalization_service.py` | 删除方法 | 删除 `_detect_language()`、`language` 字段 |
| `tasks/normalization_tasks.py` | 删除代码 | 删除 language 相关赋值 |
| `tasks/quality_tasks.py` | 删除代码 | 删除 language 参数和赋值、noise_ratio 赋值 |
| `services/http_headers.py` | 新建 | 共享请求头模块 |
| `services/rss_connector.py` | 修改 | 使用共享请求头 |
| `services/web_connector.py` | 修改 | 使用共享请求头 |
| `services/full_content_fetch_service.py` | 修改 | 使用共享请求头 |

### 数据库迁移

需要创建 Alembic 迁移：
```bash
uv run alembic revision --autogenerate -m "remove noise_ratio from items"
```

---

## 测试验证

### 单元测试

- 更新 `test_quality_gate_service.py`：移除 noise_ratio 相关测试
- 更新 `test_normalization_service.py`：移除 language 相关测试

### 集成测试

1. 部署本地测试环境
2. 创建测试源，验证采集成功
3. 检查 API 响应不再包含 `noise_ratio` 字段
4. 检查日志无 language 相关错误

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 数据库迁移失败 | 服务不可用 | 先备份数据库，使用 `alembic check` 验证 |
| API 响应格式变更 | 下游消费者受影响 | `noise_ratio` 为可选字段，删除不影响现有解析 |
| 请求头变更被检测 | 采集失败 | 统一使用 Chrome UA，与主流浏览器一致 |

---

## 预期结果

### mypy 错误变化

| 文件 | 修复前 | 修复后 |
|------|--------|--------|
| `normalization_tasks.py` | 2 errors (language) | 0 errors |
| `quality_tasks.py` | 相关警告 | 无警告 |

### 功能影响

- ✅ 代码简化，移除无效字段和逻辑
- ✅ 采集兼容性提升
- ✅ 修复 #80 中的 2 个 mypy 错误
- ✅ 数据模型与代码一致