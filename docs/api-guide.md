# API 使用指南

本指南面向下游系统开发者，介绍如何通过 Cyber Pulse API 获取情报数据。

## 目录

- [概述](#概述)
- [认证](#认证)
- [API 端点](#api-端点)
- [数据拉取模式](#数据拉取模式)
- [分页与游标](#分页与游标)
- [错误处理](#错误处理)
- [最佳实践](#最佳实践)
- [代码示例](#代码示例)

---

## 概述

Cyber Pulse 提供 RESTful API，采用**拉取式增量同步**模式：

- 下游系统主动拉取数据
- 使用游标（Cursor）实现增量同步
- 保证 at-least-once 语义

### Base URL

```
https://your-domain.com/api/v1
```

### 响应格式

所有响应均为 JSON 格式：

```json
{
  "data": [...],
  "meta": {
    "next_cursor": "cnt_20260322120000_abc12345",
    "has_more": true
  }
}
```

---

## 认证

### API Key 格式

API Key 格式为 `cp_live_{32位十六进制字符}`：

```
cp_live_1234567890abcdef1234567890abcdef
```

### 认证方式

使用 `Authorization` 请求头：

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     https://api.example.com/api/v1/contents
```

### 获取 API Key

联系系统管理员创建客户端获取 API Key。

---

## API 端点

### 内容 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/contents` | GET | 获取内容列表（增量） |
| `/api/v1/contents/{id}` | GET | 获取单个内容详情 |

### 情报源 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/sources` | GET | 获取情报源列表 |
| `/api/v1/sources/{id}` | GET | 获取情报源详情 |

### 客户端 API（需 admin 权限）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/clients` | POST | 创建客户端 |
| `/api/v1/clients` | GET | 获取客户端列表 |
| `/api/v1/clients/{id}` | DELETE | 删除客户端 |

### 健康检查

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 服务健康状态 |

---

## 数据拉取模式

### 增量同步流程

```
下游系统                        Cyber Pulse
   │                               │
   │ GET /contents?cursor=xxx      │
   │──────────────────────────────>│
   │                               │
   │ 返回 cursor 之后的数据         │
   │<──────────────────────────────│
   │                               │
   │ 保存新的 next_cursor           │
   │                               │
   │ 下一轮请求使用新 cursor        │
   │──────────────────────────────>│
```

### 首次同步

首次同步不传递 `cursor` 参数：

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents?limit=100"
```

响应：

```json
{
  "data": [
    {
      "id": "cnt_20260322120000_abc12345",
      "title": "安全漏洞通告",
      "url": "https://example.com/advisory/123",
      "content": "Markdown 格式内容...",
      "author": "Security Team",
      "tags": ["vulnerability", "critical"],
      "published_at": "2026-03-22T12:00:00Z",
      "fetched_at": "2026-03-22T12:05:00Z",
      "source": {
        "id": "src_a1b2c3d4",
        "name": "安全客",
        "tier": "T1"
      },
      "quality_score": 85
    }
  ],
  "meta": {
    "next_cursor": "cnt_20260322120000_abc12345",
    "has_more": true
  }
}
```

### 后续同步

使用上一次返回的 `next_cursor`：

```bash
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents?cursor=cnt_20260322120000_abc12345&limit=100"
```

---

## 分页与游标

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cursor` | string | - | 起始游标（Content ID） |
| `limit` | int | 50 | 每页数量（最大 100） |
| `source_id` | string | - | 按情报源筛选 |

### 游标规则

1. **游标格式**：Content ID（如 `cnt_20260322120000_abc12345`）
2. **排序顺序**：按 `fetched_at` 升序
3. **has_more**：`true` 表示还有更多数据

### 完整同步示例

```python
import requests

API_URL = "https://api.example.com/api/v1"
API_KEY = "cp_live_xxx"

def sync_all_contents():
    cursor = None

    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            f"{API_URL}/contents",
            headers={"Authorization": f"Bearer {API_KEY}"},
            params=params
        )
        response.raise_for_status()

        data = response.json()

        for content in data["data"]:
            process_content(content)

        if not data["meta"]["has_more"]:
            break

        cursor = data["meta"]["next_cursor"]
```

---

## 错误处理

### 错误响应格式

```json
{
  "detail": "错误描述",
  "code": "ERROR_CODE"
}
```

### 错误码

| 状态码 | 错误码 | 说明 |
|--------|--------|------|
| 401 | `UNAUTHORIZED` | 无效或缺失 API Key |
| 403 | `FORBIDDEN` | 权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 429 | `RATE_LIMITED` | 请求过于频繁 |
| 500 | `INTERNAL_ERROR` | 服务器内部错误 |

### 重试策略

```python
import time
from requests.exceptions import RequestException

def fetch_with_retry(url, max_retries=3, backoff=1):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response
        except RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
```

---

## 最佳实践

### 1. 合理设置轮询间隔

```python
import schedule
import time

def sync_job():
    # 同步数据
    sync_all_contents()

# 每 5 分钟同步一次
schedule.every(5).minutes.do(sync_job)

while True:
    schedule.run_pending()
    time.sleep(1)
```

### 2. 去重处理

由于 at-least-once 语义，需要处理重复数据：

```python
def process_content(content):
    content_id = content["id"]

    # 检查是否已处理
    if is_already_processed(content_id):
        return

    # 处理内容
    save_to_database(content)

    # 标记为已处理
    mark_as_processed(content_id)
```

### 3. 错误日志

```python
import logging

logger = logging.getLogger(__name__)

def sync_with_logging():
    try:
        sync_all_contents()
    except Exception as e:
        logger.error(f"同步失败: {e}", exc_info=True)
        # 发送告警
        send_alert(f"同步失败: {e}")
```

### 4. 性能优化

```python
# 使用批量处理
def process_batch(contents):
    # 批量插入数据库
    batch_insert(contents)

# 控制并发
import concurrent.futures

def sync_with_concurrency():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # 并发处理多个源
        pass
```

---

## 代码示例

### Python 完整示例

```python
import os
import requests
import logging
from datetime import datetime

# 配置
API_URL = os.environ.get("CYBERPULSE_API_URL", "https://api.example.com/api/v1")
API_KEY = os.environ.get("CYBERPULSE_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CyberPulseClient:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def get_contents(self, cursor: str = None, limit: int = 100) -> dict:
        """获取内容列表"""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            f"{self.api_url}/contents",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_content(self, content_id: str) -> dict:
        """获取单个内容"""
        response = requests.get(
            f"{self.api_url}/contents/{content_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_sources(self) -> list:
        """获取情报源列表"""
        response = requests.get(
            f"{self.api_url}/sources",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def sync_all(self, callback):
        """增量同步所有内容"""
        cursor = None

        while True:
            data = self.get_contents(cursor=cursor)

            for content in data["data"]:
                callback(content)

            if not data["meta"]["has_more"]:
                break

            cursor = data["meta"]["next_cursor"]

        logger.info("同步完成")


# 使用示例
def main():
    client = CyberPulseClient(API_URL, API_KEY)

    def process_content(content):
        print(f"处理: {content['title']} - {content['id']}")

    client.sync_all(process_content)


if __name__ == "__main__":
    main()
```

### cURL 示例

```bash
# 获取内容列表
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents?limit=10"

# 获取单个内容
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents/cnt_20260322120000_abc12345"

# 按源筛选
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/contents?source_id=src_a1b2c3d4"

# 获取情报源列表
curl -H "Authorization: Bearer cp_live_xxx" \
     "https://api.example.com/api/v1/sources"
```

---

## 下一步

- [API 参考](./api-reference.md) - 完整 API 端点说明
- [情报源配置示例](./source-config-examples.md) - 配置各类情报源
- [故障排查手册](./troubleshooting.md) - 问题诊断与解决