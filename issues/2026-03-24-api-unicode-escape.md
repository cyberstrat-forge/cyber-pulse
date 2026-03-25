# Issue: API 返回中文 Unicode 转义问题

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P1（影响下游系统数据解析）
**影响范围**: 所有包含中文的 API 响应

## 问题复现

### 请求

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "http://localhost:8000/api/v1/contents/cnt_20260324121106_92464fa9"
```

### 响应

```json
{
  "normalized_title": "\u6df1\u5ea6\u63ed\u79d8\uff1aOpenClaw Skill\u5e02\u573a\u7684\u706b\u7206\u3001\u98ce\u9669\u4e0e\u9632\u5fa1",
  "normalized_body": "\u5b57\u8282\u8df3\u52a8\u5b89\u5168\u4e2d\u5fc3..."
}
```

### 期望响应

```json
{
  "normalized_title": "深度揭秘：OpenClaw Skill市场的火爆、风险与防御",
  "normalized_body": "字节跳动安全中心..."
}
```

## 根因分析

与 CLI 问题相同，FastAPI 默认使用 `json.dumps()` 的 `ensure_ascii=True` 模式。

### 涉及文件

- `src/cyberpulse/api/main.py` - FastAPI 应用配置
- `src/cyberpulse/api/routers/content.py` - 内容 API 路由
- `src/cyberpulse/api/routers/sources.py` - 源 API 路由

## 解决方案

### 方案 1：全局配置（推荐）

在 FastAPI 应用初始化时配置 JSON 响应：

```python
# src/cyberpulse/api/main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse

class UnicodeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

app = FastAPI(default_response_class=UnicodeJSONResponse)
```

### 方案 2：中间件处理

```python
from starlette.middleware.base import BaseHTTPMiddleware

class UnicodeResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # 处理响应...
        return response
```

## 验证方法

```bash
# 创建客户端
docker compose -f deploy/docker-compose.yml exec api cyber-pulse client create "测试"

# 测试 API
curl -H "Authorization: Bearer <api_key>" \
     "http://localhost:8000/api/v1/contents?limit=1" | jq '.data[0].normalized_title'

# 预期：显示正常中文，而非 \uXXXX
```

## 相关 Issue

- `2026-03-24-cli-json-unicode-escape.md` - CLI JSON 输出中文显示问题