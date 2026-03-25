# Design: API Unicode Encoding Fix

**Issue**: #39
**Date**: 2026-03-25
**Status**: Draft

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


class UnicodeJSONResponse(JSONResponse):
    """JSON response that preserves Unicode characters."""

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
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

No new tests required. The existing API tests will verify the response structure remains unchanged. The encoding change is transparent to the test layer.

## Impact

- **Backward compatible**: JSON structure unchanged
- **No performance impact**: Same serialization path, just without ASCII escaping
- **No breaking changes**: Clients already handling UTF-8 will work correctly

## References

- PR #38: CLI Unicode encoding fix (same approach)
- Python `json.dumps()` documentation: `ensure_ascii=False` parameter