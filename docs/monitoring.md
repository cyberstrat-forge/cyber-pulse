# 监控与告警指南

本指南涵盖 Cyber Pulse 的监控配置和告警设置。

## 目录

- [监控概述](#监控概述)
- [健康检查](#健康检查)
- [指标监控](#指标监控)
- [日志监控](#日志监控)
- [告警配置](#告警配置)
- [仪表盘](#仪表盘)

---

## 监控概述

### 监控目标

| 指标类型 | 监控项 | 重要性 |
|----------|--------|--------|
| 可用性 | 服务健康状态 | 高 |
| 性能 | API 响应时间 | 高 |
| 资源 | CPU、内存、磁盘 | 中 |
| 业务 | 采集任务状态、内容数量 | 中 |
| 安全 | 认证失败、异常访问 | 高 |

### 监控架构

```
┌─────────────────┐     ┌─────────────────┐
│   Prometheus    │────▶│   Grafana       │
│   (指标采集)     │     │   (可视化)       │
└─────────────────┘     └─────────────────┘
         ▲
         │
┌─────────────────┐     ┌─────────────────┐
│   Cyber Pulse   │────▶│   Alertmanager  │
│   (指标暴露)     │     │   (告警)         │
└─────────────────┘     └─────────────────┘
```

---

## 健康检查

### API 健康端点

```bash
# 基础健康检查
curl http://localhost:8000/health

# 响应示例
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "1.2.0"
}
```

### 健康检查脚本

```bash
#!/bin/bash
# healthcheck.sh

API_URL="http://localhost:8000"
TIMEOUT=5

response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT $API_URL/health)

if [ "$response" = "200" ]; then
    echo "OK: API is healthy"
    exit 0
else
    echo "CRITICAL: API returned $response"
    exit 2
fi
```

### Systemd 健康检查

```ini
# /etc/systemd/system/cyberpulse-api.service
[Service]
# 添加健康检查
ExecStartPost=/bin/sleep 5
Restart=on-failure
RestartSec=5

# 健康检查脚本
ExecStartPost=/usr/local/bin/healthcheck.sh
```

---

## 指标监控

### Prometheus 配置

**prometheus.yml**：

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'cyberpulse'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| `cyberpulse_api_requests_total` | API 请求总数 | - |
| `cyberpulse_api_request_duration_seconds` | 请求延迟 | > 1s |
| `cyberpulse_db_connections` | 数据库连接数 | > 80% |
| `cyberpulse_redis_connections` | Redis 连接数 | > 80% |
| `cyberpulse_jobs_total` | 任务总数 | - |
| `cyberpulse_jobs_failed_total` | 失败任务数 | > 10/hour |
| `cyberpulse_sources_active` | 活跃情报源数 | - |
| `cyberpulse_contents_total` | 内容总数 | - |

### 自定义指标暴露

如需暴露 Prometheus 指标，可添加 `/metrics` 端点：

```python
# src/cyberpulse/api/routers/metrics.py
from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Response

REQUEST_COUNT = Counter(
    'cyberpulse_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'cyberpulse_api_request_duration_seconds',
    'API request latency',
    ['method', 'endpoint']
)

async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

---

## 日志监控

### 日志级别统计

```bash
# 统计各级别日志数量
cyberpulse log stats --days 1

# 输出示例
# DEBUG: 0
# INFO: 1500
# WARNING: 25
# ERROR: 3
```

### 错误日志监控

```bash
# 查看最近错误
cyberpulse log errors --since 1h

# 导出错误日志
cyberpulse log export --output /tmp/errors.log --level ERROR --since 24h
```

### 日志告警规则

**日志告警检查脚本**：

```bash
#!/bin/bash
# log_alert.sh

ERROR_COUNT=$(cyberpulse log errors --since 1h --format json | jq 'length')

if [ "$ERROR_COUNT" -gt 10 ]; then
    echo "WARNING: $ERROR_COUNT errors in the last hour"
    # 发送告警
    # curl -X POST $WEBHOOK_URL -d "alert=errors&count=$ERROR_COUNT"
    exit 1
fi

echo "OK: $ERROR_COUNT errors in the last hour"
exit 0
```

### Logrotate 配置

```bash
# /etc/logrotate.d/cyberpulse
/var/log/cyberpulse/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 cyberpulse cyberpulse
    sharedscripts
    postrotate
        systemctl reload cyberpulse-api > /dev/null 2>&1 || true
    endscript
}
```

---

## 告警配置

### 告警规则（Prometheus）

**alerts.yml**：

```yaml
groups:
  - name: cyberpulse
    rules:
      # 服务可用性
      - alert: CyberPulseAPIDown
        expr: up{job="cyberpulse"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Cyber Pulse API is down"
          description: "API has been down for more than 1 minute"

      # 高错误率
      - alert: HighErrorRate
        expr: rate(cyberpulse_api_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} requests/sec"

      # 高延迟
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(cyberpulse_api_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency"
          description: "95th percentile latency is {{ $value }}s"

      # 任务失败
      - alert: JobFailures
        expr: rate(cyberpulse_jobs_failed_total[1h]) > 0.1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High job failure rate"
          description: "Job failure rate is {{ $value }}/sec"
```

### 告警通知配置

**Slack 通知**：

```yaml
# alertmanager.yml
global:
  slack_api_url: 'https://hooks.slack.com/services/xxx'

route:
  receiver: 'slack-notifications'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - channel: '#alerts'
        send_resolved: true
        title: '{{ .Status | toUpper }}: {{ .CommonAnnotations.summary }}'
        text: '{{ .CommonAnnotations.description }}'
```

**邮件通知**：

```yaml
global:
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alerts@cyberpulse.example.com'
  smtp_auth_username: 'alerts@cyberpulse.example.com'
  smtp_auth_password: 'password'

route:
  receiver: 'email-notifications'

receivers:
  - name: 'email-notifications'
    email_configs:
      - to: 'admin@example.com'
        send_resolved: true
```

### Webhook 通知

```bash
#!/bin/bash
# send_alert.sh

WEBHOOK_URL="https://your-webhook-url"
MESSAGE="$1"

curl -X POST $WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$MESSAGE\", \"severity\": \"warning\"}"
```

---

## 仪表盘

### Grafana 仪表盘

**导入仪表盘**：

1. 打开 Grafana → Dashboards → Import
2. 粘贴仪表盘 JSON 或输入 ID
3. 选择 Prometheus 数据源
4. 点击 Import

**推荐仪表盘面板**：

| 面板 | 类型 | 说明 |
|------|------|------|
| API 请求速率 | Graph | QPS 趋势 |
| 响应时间 | Graph | P50/P95/P99 延迟 |
| 错误率 | Graph | 4xx/5xx 错误比例 |
| 活跃情报源 | Stat | 当前活跃源数量 |
| 任务状态 | Pie Chart | 成功/失败/进行中 |
| 数据库连接 | Gauge | 连接池使用率 |
| 内存使用 | Graph | 内存趋势 |

### CLI 诊断仪表盘

```bash
# 一键诊断
cyberpulse diagnose system

# 输出示例
System Health Check
===================
Database: ✓ Connected (PostgreSQL 15.2)
Redis: ✓ Connected (Redis 7.0)

API Service:
  ✓ API service: healthy
  URL: http://127.0.0.1:8000/health

Task Queue:
  ✓ Dramatiq Redis: connected
  Pending tasks in default queue: 3

Configuration:
  Log level: INFO
  Log file: logs/cyberpulse.log
  Scheduler enabled: True

Recent Errors: 12 (last 24h)
```

---

## 监控检查清单

### 每日检查

- [ ] 健康检查端点响应正常
- [ ] 无严重错误日志
- [ ] 采集任务正常运行
- [ ] 磁盘空间充足

### 每周检查

- [ ] 检查告警历史
- [ ] 审查性能指标趋势
- [ ] 验证备份完整性
- [ ] 检查日志轮转正常

### 每月检查

- [ ] 审查监控规则有效性
- [ ] 调整告警阈值
- [ ] 验证告警通知正常
- [ ] 检查存储容量趋势

---

## 故障诊断

### 服务不可用

```bash
# 1. 检查服务状态
docker-compose ps
# 或
systemctl status cyberpulse-api

# 2. 检查日志
docker-compose logs --tail 100 api

# 3. 检查依赖服务
curl localhost:8000/health

# 4. 检查资源使用
docker stats
```

### 性能下降

```bash
# 1. 检查数据库连接
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"

# 2. 检查慢查询
psql $DATABASE_URL -c "SELECT query, duration FROM pg_stat_activity WHERE state = 'active' ORDER BY duration DESC LIMIT 10;"

# 3. 检查 Redis
redis-cli INFO memory

# 4. 检查系统资源
top -p $(pgrep -f uvicorn)
```

### 告警风暴

```bash
# 临时静默告警
curl -X POST http://alertmanager:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "HighErrorRate"}],
    "startsAt": "2026-03-22T00:00:00Z",
    "endsAt": "2026-03-22T01:00:00Z",
    "createdBy": "admin",
    "comment": "Planned maintenance"
  }'
```