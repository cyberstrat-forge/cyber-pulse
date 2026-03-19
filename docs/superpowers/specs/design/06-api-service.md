# API 服务

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 接口模型

**Pull + Cursor 增量模型**

数据流：
```
Source → cyber-pulse → Curated Storage → Pull API → cyber-nexus → iNBox → 情报卡片
```

**关键特性：**
- ✅ 不采用事件推送
- ✅ 不记录消费状态
- ✅ 不维护下游系统的处理记录
- ✅ 支持多消费者并行
- ✅ 支持增量与重算
- ✅ 语义为 at-least-once

**消费者职责（cyber-nexus）：**
- ✅ 维护自己的 cursor
- ✅ 基于 `content_id` 实现幂等
- ✅ 写入本地 iNBox 目录
- ✅ 生成情报卡片并长期保存

---

## API 端点设计

**获取内容：**

```http
GET /api/v1/content?cursor=12345&since=2026-03-18T10:00:00Z&limit=100
Authorization: Bearer cp_live_xxx
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `cursor` | int | 基于 ID 的游标（上次读取的最大 `content_id`） |
| `since` | timestamp | 基于时间的游标（某时间之后的数据） |
| `limit` | int | 每页数量（默认 100，最大 1000） |
| `source_tier` | enum | 可选：按等级过滤（T0/T1/T2） |

**响应格式：**

```json
{
  "data": [
    {
      "content_id": "cnt_123",
      "source_id": "src_456",
      "source_name": "安全客",
      "source_tier": "T1",
      "source_score": 75.5,
      "source_quality_metrics": {
        "content_completeness": 0.92,
        "noise_ratio": 0.08,
        "update_frequency": "daily",
        "stability": 0.95
      },
      "original_title": "XXX 漏洞分析",
      "publish_time": "2026-03-18T10:00:00Z",
      "processed_time": "2026-03-18T10:05:00Z",
      "normalized_markdown": "...",
      "content_hash": "abc123...",
      "language": "zh",
      "metadata": {
        "author": "张三",
        "word_count": 1500
      }
    }
  ],
  "next_cursor": 12445,
  "has_more": true,
  "count": 100,
  "server_timestamp": "2026-03-18T10:30:00Z"
}
```

**关键字段说明：**
- `source_score`：0-100 评分，为 cyber-nexus 提供情报可信度评估依据
- `source_quality_metrics`：可选详细质量指标，用于细粒度可信度计算

---

## 认证机制

**API Key 认证**

```http
Authorization: Bearer cp_live_xxx
```

**API 客户端管理：**

```bash
# 创建 API 客户端
./cli client create --name "cyber-nexus" --permissions read

# → 生成 API Key: cp_live_a1b2c3d4e5f6...

# 列出所有客户端
./cli client list

# 禁用客户端
./cli client disable <client-id>
```

**数据模型：**

```sql
CREATE TABLE api_clients (
    client_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    permissions JSONB,
    rate_limit INT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);
```

---

## 错误模型

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 认证失败 |
| 403 | 未授权（未来扩展） |
| 404 | 不适用资源 |
| 429 | 限流（达到 rate_limit） |
| 500 | 内部错误 |
| 503 | 服务不可用 |

---

## 消费者实现样例（cyber-nexus）

```python
# cyber-nexus 消费者实现
import requests
import json
import time

class CyberPulseConsumer:
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.cursor = self._load_cursor()  # 从本地文件加载

    def _load_cursor(self):
        """从本地文件加载 cursor"""
        try:
            with open("cursor.txt", "r") as f:
                return int(f.read().strip())
        except:
            return 0  # 首次运行

    def _save_cursor(self, cursor):
        """保存 cursor 到本地文件"""
        with open("cursor.txt", "w") as f:
            f.write(str(cursor))

    def fetch_incremental(self, limit=100):
        """拉取增量数据"""
        params = {
            "cursor": self.cursor,
            "limit": limit
        }

        response = requests.get(
            f"{self.api_url}/api/v1/content",
            headers=self.headers,
            params=params
        )

        if response.status_code == 200:
            data = response.json()
            contents = data["data"]

            if contents:
                # 处理数据（去重、写入 iNBox）
                self._process_contents(contents)

                # 更新 cursor
                self.cursor = data["next_cursor"]
                self._save_cursor(self.cursor)

                print(f"✓ Fetched {len(contents)} items, new cursor: {self.cursor}")

            return contents
        else:
            print(f"✗ Error: {response.status_code}")
            return []

    def _process_contents(self, contents):
        """处理内容（去重、写入 iNBox）"""
        for content in contents:
            content_id = content["content_id"]

            # 幂等性检查（基于 content_id）
            if not self._exists_in_inbox(content_id):
                # 写入 iNBox
                self._write_to_inbox(content)

    def _exists_in_inbox(self, content_id):
        """检查是否已存在（幂等性）"""
        # 实现：检查本地数据库或文件
        pass

    def _write_to_inbox(self, content):
        """写入 iNBox"""
        # 实现：保存为 Markdown 文件
        filename = f"inbox/{content['content_id']}.md"
        with open(filename, "w") as f:
            f.write(self._format_markdown(content))

    def _format_markdown(self, content):
        """格式化为 Markdown"""
        md = f"""# {content['original_title']}

来源: {content['source_name']} ({content['source_tier']})
Score: {content.get('source_score', 'N/A')}
发布时间: {content['publish_time']}

{content['normalized_markdown']}
"""
        return md

    def run_forever(self, interval=300):
        """持续运行，定期拉取"""
        while True:
            try:
                self.fetch_incremental()
                time.sleep(interval)  # 每 5 分钟拉取一次
            except KeyboardInterrupt:
                print("Stopped by user")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)  # 错误后等待 1 分钟

# 使用示例
if __name__ == "__main__":
    consumer = CyberPulseConsumer(
        api_url="http://localhost:8000",
        api_key="cp_live_xxx"
    )

    # 启动消费者
    consumer.run_forever(interval=300)
```

**关键要点：**
- Cursor 本地持久化（文件存储）
- 基于 `content_id` 幂等处理
- 定期轮询（建议 5-10 分钟）
- 错误重试机制