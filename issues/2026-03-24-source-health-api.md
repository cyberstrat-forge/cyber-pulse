# Issue: 缺少源健康状态监控 API

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: P1（影响运维监控能力）
**影响范围**: 源管理、运维监控

## 背景

当前系统有 146 个情报源，其中：
- 12 个源无法访问（HTTP 403/404/000）
- 57 个源只提供标题链接，无正文
- 缺乏有效的健康状态监控机制

## 当前状态

### 已有的健康检查

```bash
# 服务级别的健康检查
GET /health
→ {"status": "healthy", "version": "1.3.0", "components": {"database": "healthy", "api": "healthy"}}
```

### 缺失的功能

| 功能 | 状态 | 重要性 |
|------|------|--------|
| 源级别健康状态 | ❌ 缺失 | 高 |
| 采集成功率统计 | ❌ 缺失 | 高 |
| 内容质量趋势 | ❌ 缺失 | 中 |
| 告警机制 | ❌ 缺失 | 高 |
| 健康状态 API | ❌ 缺失 | 高 |

## 需求分析

### 1. 源健康状态定义

```python
class SourceHealthStatus(str, Enum):
    HEALTHY = "healthy"       # 正常采集，内容质量良好
    DEGRADED = "degraded"     # 可采集但有问题（内容短、部分失败）
    UNHEALTHY = "unhealthy"   # 无法采集或采集失败
    UNKNOWN = "unknown"       # 从未采集过
```

### 2. 健康指标

| 指标 | 计算方式 | 健康阈值 |
|------|----------|----------|
| HTTP 可达性 | 最近采集请求成功率 | ≥ 95% |
| 内容获取率 | 有内容的条目 / 总条目 | ≥ 80% |
| 内容质量率 | 完整度 ≥ 0.7 的内容占比 | ≥ 70% |
| 更新活跃度 | 最近 24h 有新内容 | - |

### 3. API 设计

#### 获取源健康状态

```
GET /api/v1/sources/health
```

**响应：**

```json
{
  "summary": {
    "total": 146,
    "healthy": 89,
    "degraded": 34,
    "unhealthy": 12,
    "unknown": 11
  },
  "sources": [
    {
      "source_id": "src_70d4d89c",
      "name": "VentureBeat",
      "status": "healthy",
      "health_score": 92,
      "last_fetch": "2026-03-24T14:00:00Z",
      "fetch_success_rate": 1.0,
      "content_rate": 0.95,
      "quality_rate": 0.88,
      "items_24h": 12
    },
    {
      "source_id": "src_f60158be",
      "name": "Anthropic Press Releases",
      "status": "unhealthy",
      "health_score": 0,
      "last_fetch": null,
      "fetch_success_rate": 0,
      "error": "HTTP 403: Forbidden",
      "suggestion": "更新 feed_url 或使用原始 RSS 地址"
    }
  ]
}
```

#### 获取单个源健康详情

```
GET /api/v1/sources/{source_id}/health
```

**响应：**

```json
{
  "source_id": "src_f60158be",
  "name": "Anthropic Press Releases",
  "status": "unhealthy",
  "health_score": 0,
  "checks": {
    "connectivity": {
      "status": "fail",
      "http_status": 403,
      "error": "Forbidden",
      "last_check": "2026-03-24T14:00:00Z"
    },
    "content": {
      "status": "unknown",
      "total_items": 0,
      "items_with_content": 0
    },
    "quality": {
      "status": "unknown",
      "avg_completeness": null
    }
  },
  "history": [
    {"date": "2026-03-24", "status": "unhealthy", "fetch_attempts": 3, "success": 0},
    {"date": "2026-03-23", "status": "unhealthy", "fetch_attempts": 3, "success": 0}
  ],
  "suggestions": [
    "Feed URL (feedproxy.feedly.com) 返回 403",
    "建议使用原始 RSS 地址: https://www.anthropic.com/news/rss"
  ]
}
```

#### 批量测试源健康

```
POST /api/v1/sources/health/check
```

**请求体：**

```json
{
  "source_ids": ["src_70d4d89c", "src_f60158be"],
  "force": true
}
```

**响应：**

```json
{
  "job_id": "job_abc123",
  "status": "running",
  "message": "Health check started for 2 sources"
}
```

### 4. CLI 命令

```bash
# 查看所有源健康状态
cyber-pulse source health

# 查看特定源健康详情
cyber-pulse source health src_f60158be

# 批量测试
cyber-pulse source test --all
cyber-pulse source test --unhealthy
```

### 5. 告警配置

```yaml
# config.yaml
alerts:
  sources:
    # 源连续失败告警
    consecutive_failures: 3

    # 健康分数下降告警
    health_score_threshold: 50

    # 通知渠道
    channels:
      - type: email
        recipients: ["ops@example.com"]
      - type: webhook
        url: "https://hooks.slack.com/..."
```

## 数据模型扩展

```python
# 新增表：source_health_logs
class SourceHealthLog(Base):
    __tablename__ = "source_health_logs"

    id = Column(Integer, primary_key=True)
    source_id = Column(String, ForeignKey("sources.source_id"))
    checked_at = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum("healthy", "degraded", "unhealthy", "unknown"))
    health_score = Column(Integer)
    fetch_success = Column(Boolean)
    http_status = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    items_fetched = Column(Integer, default=0)
    items_with_content = Column(Integer, default=0)
    avg_completeness = Column(Float, nullable=True)
```

## 实施计划

### Phase 1: 基础健康检查（1周）

- [ ] 定义健康状态枚举和计算逻辑
- [ ] 实现 `source test` CLI 命令
- [ ] 添加 `GET /api/v1/sources/health` API
- [ ] 数据库存储健康日志

### Phase 2: 详细监控（2周）

- [ ] 实现健康历史记录
- [ ] 添加 `GET /api/v1/sources/{id}/health` API
- [ ] CLI 健康趋势展示
- [ ] 源详情页面显示健康指标

### Phase 3: 告警机制（1周）

- [ ] 告警规则引擎
- [ ] 邮件/Webhook 通知
- [ ] 告警历史记录
- [ ] 告警静默配置

## 相关 Issue

- `2026-03-24-rss-source-accessibility.md` - 源可访问性问题
- `2026-03-24-rss-no-content.md` - 源无内容问题
- `2026-03-24-rss-content-fetch-architecture.md` - 架构改进讨论