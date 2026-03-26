# Issue: Worker 大量 RSS 采集错误

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P1（影响采集成功率）
**影响范围**: RSS 源采集任务

## 错误统计

### 按错误类型分类

| 错误类型 | 次数 | 说明 |
|----------|------|------|
| HTTP 301 | 1077 | 永久重定向，URL 已迁移 |
| HTTP 403 | 225 | 禁止访问，反爬限制 |
| HTTP 302 | 165 | 临时重定向 |
| HTTP 308 | 111 | 永久重定向 |
| ConnectError | 84 | 连接失败 |
| **总计** | **1662** | - |

### 重试统计

- 重试任务数: 489 次
- 当前队列待处理: 12 个

## 错误详情

### 问题 1: HTTP 重定向错误 (301/302/308)

**典型错误**:
```
ConnectorError: Failed to fetch RSS feed 'https://blog.langchain.dev/rss/': HTTP 308
ConnectorError: Failed to fetch RSS feed 'https://blog.google/products/gemini/rss/': HTTP 301
ConnectorError: Failed to fetch RSS feed 'http://venturebeat.com/feed/': HTTP 308
ConnectorError: Failed to fetch RSS feed 'http://googleresearch.blogspot.com/atom.xml': HTTP 301
```

**原因分析**:
1. RSS 源 URL 已迁移到新地址
2. httpx 默认不跟随跨域重定向（或配置问题）
3. 未配置 `follow_redirects=True`

**涉及文件**: `src/cyberpulse/services/rss_connector.py`

**当前代码检查**:
```python
# 检查是否有 follow_redirects 配置
response = await client.get(feed_url, timeout=30.0, follow_redirects=True)
```

**建议修复**:
```python
# 确保配置了 follow_redirects
async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
    response = await client.get(feed_url)
```

### 问题 2: HTTP 403 禁止访问

**典型错误**:
```
ConnectorError: Failed to fetch RSS feed 'https://rsshub.app/deeplearning/thebatch': HTTP 403
ConnectorError: Failed to fetch RSS feed 'https://www.coalitionforsecureai.org/feed/': HTTP 403
ConnectorError: Failed to fetch RSS feed 'https://momentumcyber.com/feed/': HTTP 403
ConnectorError: Failed to fetch RSS feed 'https://menlovc.com/feed/': HTTP 403
```

**原因分析**:
1. RSSHub 公共实例有反爬限制
2. 部分网站有 Cloudflare 或其他反爬保护
3. 缺少 User-Agent 或其他必要请求头

**建议修复**:
```python
# 添加常见浏览器 User-Agent
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
response = await client.get(feed_url, headers=headers)
```

### 问题 3: 连接错误 (ConnectError)

**典型错误**:
```
ConnectorError: Failed to fetch RSS feed 'https://www.tedunangst.com/flak/rss': ConnectError:
ConnectorError: Failed to fetch RSS feed 'https://rachelbythebay.com/w/atom.xml': ConnectError:
```

**原因分析**:
1. 服务器不可达
2. DNS 解析失败
3. 网络超时

**建议修复**:
- 增加超时时间
- 添加重试机制（已有，但可优化退避策略）
- 标记长期失败的源

## Scheduler 日志分析

### 正常运行

```
2026-03-24 15:23:26 - Running job "Scheduled Collection"
2026-03-24 15:23:26 - Running scheduled collection for all active sources
2026-03-24 15:23:26 - Queued 146 sources for collection (0 failed)
2026-03-24 15:23:26 - Job scheduled_collection executed successfully
```

### 启动时的迁移错误（已恢复）

```
sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint "pg_type_typname_nsp_index"
DETAIL: Key (typname, typnamespace)=(alembic_version, 2200) already exists.
[entrypoint] Migration failed after 1 attempts
[entrypoint] Set ALLOW_MIGRATION_FAILURE=true to continue on failure
...
[entrypoint] Migration attempt 1/5
[entrypoint] Migrations completed successfully
```

**说明**: 迁移失败后重试成功，不影响功能。

## 影响分析

### 对系统的影响

1. **采集成功率下降**: 1662 次错误 vs 成功采集
2. **任务队列积压**: 重试任务占用队列
3. **日志膨胀**: 大量错误日志
4. **资源浪费**: 反复重试失败的源

### 数据质量影响

- 部分源无法采集新内容
- 情报完整性受影响

## 解决方案建议

### P0 - 紧急修复

#### 1. 启用 HTTP 重定向跟随

```python
# src/cyberpulse/services/rss_connector.py

class RSSConnector(BaseConnector):
    def __init__(self, config: dict):
        self.feed_url = config.get("feed_url")
        self._client = httpx.AsyncClient(
            follow_redirects=True,  # 跟随重定向
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)"
            }
        )
```

#### 2. 更新已知迁移的 RSS URL

```sql
-- 更新重定向的源 URL
UPDATE sources
SET config = jsonb_set(config, '{feed_url}', '"https://www.langchain.com/blog/rss.xml"')
WHERE config->>'feed_url' = 'https://blog.langchain.dev/rss/';

UPDATE sources
SET config = jsonb_set(config, '{feed_url}', '"https://venturebeat.com/feed/"')
WHERE config->>'feed_url' = 'http://venturebeat.com/feed/';
```

### P1 - 功能增强

#### 1. 自动更新重定向 URL

```python
async def fetch(self) -> List[Item]:
    response = await self._client.get(self.feed_url)

    # 检测永久重定向，自动更新 URL
    if response.history:
        final_url = str(response.url)
        if final_url != self.feed_url:
            logger.info(f"RSS feed redirected: {self.feed_url} -> {final_url}")
            # 可选：自动更新数据库中的 URL
```

#### 2. 失败源自动降级

```python
# 当连续失败超过阈值时，标记源为 FROZEN
MAX_CONSECUTIVE_FAILURES = 5

if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
    await self.source_service.update_status(source_id, "FROZEN")
    logger.warning(f"Source {source_id} frozen due to consecutive failures")
```

#### 3. 请求头配置

```yaml
# 源配置支持自定义请求头
- name: "RSSHub Source"
  config:
    feed_url: "https://rsshub.app/..."
    headers:
      User-Agent: "Mozilla/5.0..."
      Accept: "application/xml"
```

### P2 - 监控增强

#### 1. 采集成功率监控

```python
# 添加采集成功率指标
class IngestionMetrics:
    total_sources: int
    successful: int
    failed: int
    redirected: int

    @property
    def success_rate(self) -> float:
        return self.successful / self.total_sources if self.total_sources > 0 else 0
```

#### 2. 源健康告警

当采集成功率低于阈值时发出告警。

## 相关文件

- `src/cyberpulse/services/rss_connector.py` - RSS 连接器
- `src/cyberpulse/tasks/ingestion_tasks.py` - 采集任务
- `src/cyberpulse/scheduler/jobs.py` - 调度任务

## 相关 Issue

- `2026-03-24-rss-source-accessibility.md` - RSS 源可访问性问题
- `2026-03-24-source-health-api.md` - 源健康监控 API