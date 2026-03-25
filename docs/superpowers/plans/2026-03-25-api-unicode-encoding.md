# API Unicode Encoding Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix FastAPI JSON responses to properly encode Unicode characters instead of escaping them as `\uXXXX` sequences.

**Architecture:** Add a custom `UnicodeJSONResponse` class that uses `json.dumps(ensure_ascii=False)` and configure it as the default response class for the FastAPI application.

**Tech Stack:** Python 3.11+, FastAPI, pytest

---

## Files Overview

| File | Action | Purpose |
|------|--------|---------|
| `src/cyberpulse/api/main.py` | Modify | Add `UnicodeJSONResponse` class |
| `tests/test_api/test_unicode_encoding.py` | Create | Test Unicode encoding in responses |

---

### Task 1: Create Branch and Write Failing Tests

**Files:**
- Create: `tests/test_api/test_unicode_encoding.py`

- [ ] **Step 1: Create feature branch**

```bash
git checkout -b fix/api-unicode-encoding
```

- [ ] **Step 2: Create test file with failing tests**

```python
"""Test that API responses preserve Unicode characters."""
import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestUnicodeEncoding:
    """Verify Unicode characters are not escaped in JSON responses."""

    def test_health_endpoint_unicode(self, client):
        """Health endpoint should not escape Unicode in response."""
        response = client.get("/health")
        assert response.status_code == 200
        # Response should contain actual characters, not escape sequences
        raw_text = response.text
        assert "\\u" not in raw_text, "Unicode characters should not be escaped"

    def test_error_response_encoding(self, client):
        """Error responses should preserve Unicode in error messages."""
        response = client.get("/api/v1/items/item_notfound")
        assert response.status_code == 404
        raw_text = response.text
        assert "\\u" not in raw_text, "Error messages should not escape Unicode"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_api/test_unicode_encoding.py -v`

Expected: FAIL - tests detect `\u` escape sequences in responses

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/test_api/test_unicode_encoding.py
git commit -m "test: add Unicode encoding tests (currently failing)"
```

---

### Task 2: Implement UnicodeJSONResponse Class

**Files:**
- Modify: `src/cyberpulse/api/main.py`

- [ ] **Step 1: Add import statements**

Modify `src/cyberpulse/api/main.py`:

**After line 6** (after `from pathlib import Path`), add:
```python
import json
```

**After line 8** (after `from fastapi import FastAPI`), add:
```python
from fastapi.responses import JSONResponse
```

- [ ] **Step 2: Add UnicodeJSONResponse class**

Insert the following class **after line 12** (after `from .routers import content, sources, clients, health`) and **before line 15** (before `def setup_logging()`):

```python


class UnicodeJSONResponse(JSONResponse):
    """JSON response that preserves Unicode characters.

    By default, FastAPI uses json.dumps with ensure_ascii=True, which converts
    non-ASCII characters (like Chinese) to Unicode escape sequences (\\uXXXX).
    This class ensures proper UTF-8 encoding for international text.
    """

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")
```

- [ ] **Step 3: Add default_response_class to FastAPI app**

Find the `app = FastAPI(...)` block (around line 62-69). Add `default_response_class=UnicodeJSONResponse,` as a new parameter:

**Add this line** after `version=__version__,`:
```python
    default_response_class=UnicodeJSONResponse,
```

The complete block should look like:
```python
app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version=__version__,
    default_response_class=UnicodeJSONResponse,
    docs_url="/docs" if should_enable_docs() else None,
    redoc_url="/redoc" if should_enable_docs() else None,
    openapi_url="/openapi.json" if should_enable_docs() else None,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api/test_unicode_encoding.py -v`

Expected: PASS - both tests pass

- [ ] **Step 5: Run all API tests to ensure no regression**

Run: `uv run pytest tests/test_api/ -v`

Expected: PASS - all existing tests still pass

- [ ] **Step 6: Commit implementation**

```bash
git add src/cyberpulse/api/main.py
git commit -m "fix(api): use UnicodeJSONResponse for proper Chinese encoding

- Add UnicodeJSONResponse class with ensure_ascii=False
- Configure as default_response_class for FastAPI app
- Fixes #39"
```

---

### Task 3: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `uv run pytest`

Expected: PASS - all tests pass

- [ ] **Step 2: Run linting**

Run: `uv run ruff check src/ tests/`

Expected: PASS - no linting errors

- [ ] **Step 3: Run type checking**

Run: `uv run mypy src/ --ignore-missing-imports`

Expected: PASS - no type errors

---

### Task 4: Create Pull Request

- [ ] **Step 1: Push branch to remote**

```bash
git push -u origin fix/api-unicode-encoding
```

- [ ] **Step 2: Create Pull Request**

Create PR with title: `fix(api): ensure proper Chinese encoding in JSON output`

PR body:
```
## Summary

- Add `UnicodeJSONResponse` class with `ensure_ascii=False`
- Configure as `default_response_class` for FastAPI app
- Fixes Chinese characters displaying as Unicode escape sequences (`\uXXXX`)

## Affected components

- REST API JSON responses
- OpenAPI documentation (`/docs`, `/redoc`, `/openapi.json`)
- Error responses (401, 403, 404, 422)

## Test plan

- [x] Unit tests for Unicode encoding added
- [x] All existing tests pass
- [ ] Manual test: `curl localhost:8000/health` shows proper Unicode

Fixes #39
```

- [ ] **Step 3: Merge PR after review**

After PR approval, merge to main.

---

## Verification Checklist

- [ ] Unicode tests pass
- [ ] All existing tests pass
- [ ] No linting errors
- [ ] No type errors
- [ ] Manual test: `curl localhost:8000/health` shows proper Unicode
- [ ] PR merged to main
- [ ] Issue #39 closed