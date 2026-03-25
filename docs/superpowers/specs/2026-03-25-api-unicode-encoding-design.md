# Design: API Unicode Encoding Fix

**Issue**: #39
**Date**: 2026-03-25
**Status**: Revised

## Problem

FastAPI uses `json.dumps()` with `ensure_ascii=True` by default, causing all non-ASCII characters (like Chinese) to be escaped as Unicode escape sequences (`\uXXXX`).

### Example

**Current Response**:
```json
{
  "normalized_title": "\u6df1\u5ea6\u63ed\u79d8\uff1aOpenClaw Skill\u5e02\u573a\u7684\u706b\u7206"
}
```

**Expected Response**:
```json
{
  "normalized_title": "深度揭秘：OpenClaw Skill市场的火爆"
}
```

## Solution

Configure a custom `UnicodeJSONResponse` class as the default response class for the FastAPI application.

### Implementation

**File**: `src/cyberpulse/api/main.py`

```python
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..config import settings
from .. import __version__


class UnicodeJSONResponse(JSONResponse):
    """JSON response that preserves Unicode characters.

    By default, FastAPI uses json.dumps with ensure_ascii=True, which converts
    non-ASCII characters (like Chinese) to Unicode escape sequences (\uXXXX).
    This class ensures proper UTF-8 encoding for international text.
    """

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


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

### Design Notes

1. **Removed `allow_nan=False`**: Standard `json.dumps()` handles `NaN`/`Infinity` by default. Removing this parameter maintains backward compatibility and avoids potential errors.

2. **Null handling**: The implementation handles `None` (JSON `null`) correctly - `json.dumps(None)` returns `"null"`, which is valid JSON.

## Scope

This fix covers:

1. **REST API JSON responses** - All endpoints return properly encoded Chinese
2. **OpenAPI documentation** - `/docs`, `/redoc`, `/openapi.json`
3. **Error responses** - 401, 403, 404, 422 and other auto-generated errors

## Testing

### Manual Verification

```bash
# Create API client
docker compose -f deploy/docker-compose.yml exec api cyber-pulse client create "test"

# Test API response
curl -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/contents?limit=1" | jq '.data[0].normalized_title'

# Expected: Chinese characters displayed, not \uXXXX
```

### Automated Tests

Add a test to verify Unicode encoding in API responses. This prevents future regression.

**File**: `tests/test_api/test_unicode_encoding.py`

```python
"""Test that API responses preserve Unicode characters."""
import pytest
from fastapi.testclient import TestClient
from cyberpulse.api.main import app


client = TestClient(app)


class TestUnicodeEncoding:
    """Verify Unicode characters are not escaped in JSON responses."""

    def test_health_endpoint_unicode(self):
        """Health endpoint should not escape Unicode in description."""
        response = client.get("/health")
        assert response.status_code == 200
        # Response should contain actual characters, not escape sequences
        raw_text = response.text
        assert "\\u" not in raw_text, "Unicode characters should not be escaped"

    def test_error_response_encoding(self):
        """Error responses should preserve Unicode in error messages."""
        response = client.get("/api/v1/contents/cnt_notfound")
        assert response.status_code == 404
        raw_text = response.text
        assert "\\u" not in raw_text, "Error messages should not escape Unicode"
```

### Integration Verification

The existing API tests in `tests/` will continue to verify response structure. The encoding change is transparent to the test layer at the assertion level.

## Impact

- **Backward compatible**: JSON structure unchanged
- **No performance impact**: Same serialization path, just without ASCII escaping
- **No breaking changes**: Clients already handling UTF-8 will work correctly

## References

- PR #38: CLI Unicode encoding fix (same approach, used `ensure_ascii=False`)
- Python `json.dumps()` documentation: `ensure_ascii=False` parameter

## Completion Status

This fix **completes** the Unicode encoding work for the system:

| Component | Status | Reference |
|-----------|--------|-----------|
| CLI JSON output | ✅ Fixed | PR #38 |
| REST API responses | 🔲 This issue | Issue #39 |
| OpenAPI docs | 🔲 This issue | Issue #39 |
| Error responses | 🔲 This issue | Issue #39 |

After this fix is implemented, all JSON output from the system will properly display Chinese and other non-ASCII characters.