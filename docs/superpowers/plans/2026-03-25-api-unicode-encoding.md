# API Unicode Encoding Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix FastAPI JSON responses to properly encode Unicode characters instead of escaping them as `\uXXXX` sequences.

**Architecture:** Add a custom `UnicodeJSONResponse` class that uses `json.dumps(ensure_ascii=False)` and configure it as the default response class for the FastAPI application.

**Tech Stack:** Python 3.11+, FastAPI, pytest

---

## ⚠️ 重要发现

**在实施过程中发现：Starlette 的 `JSONResponse` 已经默认使用 `ensure_ascii=False`！**

```python
# starlette/responses.py
def render(self, content: Any) -> bytes:
    return json.dumps(
        content,
        ensure_ascii=False,  # 已经是 False！
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
    ).encode("utf-8")
```

这意味着 FastAPI 的默认响应已经正确处理 Unicode 编码，**不需要额外的 UnicodeJSONResponse 类**。

测试验证了这一点：
- Health 端点正确显示中文（如有）
- Content API 正确返回中文字符，无 `\uXXXX` 转义

---

## Files Overview

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_api/test_unicode_encoding.py` | Create | Test Unicode encoding in responses |

---

### Task 1: Create Branch and Write Tests

**Files:**
- Create: `tests/test_api/test_unicode_encoding.py`

- [x] **Step 1: Create feature branch**

```bash
git checkout -b fix/api-unicode-encoding
```

- [x] **Step 2: Create test file**

测试验证 Starlette 的 JSONResponse 已经正确处理 Unicode。

- [x] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_api/test_unicode_encoding.py -v`

Expected: PASS - all tests pass (Starlette already handles Unicode correctly)

- [x] **Step 4: Commit tests**

```bash
git add tests/test_api/test_unicode_encoding.py
git commit -m "test: add Unicode encoding tests

Verify that Starlette's JSONResponse correctly handles Unicode
without escaping Chinese characters to \\uXXXX sequences."
```

---

## Verification Checklist

- [x] Unicode tests pass
- [x] Chinese characters are preserved in responses
- [x] No `\uXXXX` escape sequences in API responses