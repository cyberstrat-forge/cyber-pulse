# 部署与运维

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 单机部署方案

**环境要求：**
- ✅ Python 3.11+
- ✅ PostgreSQL 15
- ✅ Redis 7
- ✅ 磁盘空间：至少 10GB（数据 + 日志）

---

### Docker Compose 部署

**docker-compose.yml：**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: cyber_pulse
      POSTGRES_USER: cyber
      POSTGRES_PASSWORD: cyber123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    mem_limit: 1g
    cpus: 1.0

  redis:
    image: redis:7
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    mem_limit: 512m
    cpus: 0.5

  app:
    build: .
    environment:
      DATABASE_URL: postgresql://cyber:cyber123@postgres:5432/cyber_pulse
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    mem_limit: 1g
    cpus: 2.0

volumes:
  postgres_data:
  redis_data:
```

**启动流程：**
```bash
# 🌅 早上上班
cd cyber-pulse
docker-compose up -d              # 启动所有服务
./cli server status               # 检查状态

# 🌙 下班关闭
docker-compose down               # 停止所有服务（数据保留）
```

**重启后：**
- ✅ 所有 Source 配置保留
- ✅ 所有采集历史保留
- ✅ 调度任务保留（APScheduler 从数据库恢复）
- ✅ 未完成任务可继续

---

## 配置管理

**环境变量：**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://...` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379` |
| `API_PORT` | API 服务端口 | `8000` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 备份与恢复

**数据备份：**

```bash
# 备份数据库
pg_dump -U cyber cyber_pulse > backup_$(date +%Y%m%d).sql

# 备份配置文件
cp ~/.cyber-pulse/config.yaml backup_config.yaml

# 备份原始数据（可选）
tar -czf data_backup.tar.gz ./data
```

**数据恢复：**

```bash
# 恢复数据库
psql -U cyber cyber_pulse < backup_20260318.sql

# 恢复配置文件
cp backup_config.yaml ~/.cyber-pulse/config.yaml
```

---

## 硬件要求

### 最低配置（开发/测试环境）

```
CPU: 2 核
内存: 4 GB
磁盘: 20 GB (SSD 推荐)
网络: 100 Mbps
操作系统: Linux / macOS / Windows (WSL2)
```

**适用场景：**
- 开发调试
- 小规模测试（< 50 个 Source）
- 日处理量 < 1,000 条

---

### 推荐配置（原型验证环境）

```
CPU: 4 核
内存: 8 GB
磁盘: 50 GB SSD
网络: 1 Gbps
操作系统: Linux (Ubuntu 20.04+)
```

**适用场景：**
- 单机原型运行
- 200-500 个 Source
- 日处理量 1,000-10,000 条

---

### 高性能配置（接近生产）

```
CPU: 8 核
内存: 16 GB
磁盘: 100 GB SSD + 500 GB HDD (数据存储)
网络: 1 Gbps
操作系统: Linux (CentOS 7+ / Ubuntu 20.04+)
```

**适用场景：**
- 500+ 个 Source
- 日处理量 10,000+ 条
- 需要长时间稳定运行

---

### 资源占用估算

| 组件 | 内存 | 磁盘 | 说明 |
|------|------|------|------|
| PostgreSQL | 512 MB | 10 GB | 根据数据量增长 |
| Redis | 256 MB | 1 GB | 缓存和队列 |
| App (Python) | 512 MB | 5 GB | 代码 + 运行时 |
| 原始数据存储 | - | 20 GB | 1 年数据估算 |
| 日志文件 | - | 5 GB | 结构化日志 |

**总计：**
- 内存：~1.5 GB (运行时)
- 磁盘：~40 GB (1 年数据 + 系统)

---

### 网络带宽估算

**日采集 10,000 条：**
- 平均每条 50 KB (HTML + 图片)
- 日流量：~500 MB
- 月流量：~15 GB

**建议：**
- 宽带：至少 100 Mbps
- 流量：月 50 GB 以上套餐

---

### 监控建议

```bash
# 系统资源监控
docker stats  # 实时查看容器资源

# 磁盘空间
df -h  # 查看磁盘使用

# 内存
free -h  # 查看内存使用
```

---

## 日志与监控

### 结构化日志

**日志级别：**

| 级别 | 说明 |
|------|------|
| DEBUG | 详细调试信息 |
| INFO | 常规操作（任务开始/结束） |
| WARNING | 警告（可选字段缺失） |
| ERROR | 错误（任务失败） |
| CRITICAL | 严重错误（系统级问题） |

**日志查看：**

```bash
# 查看最近 50 行日志
/log tail -n 50

# 实时跟踪日志
/log tail -f

# 查看错误日志（最近 1 小时）
/log errors --since "1h"

# 按 Source 过滤错误
/log errors --source "安全客"

# 搜索关键词
/log search "403 Forbidden"

# 查看日志统计
/log stats
```

---

### 核心指标

**通过 CLI 查看：**

```bash
/log stats
→ 今日日志：1,245 条
   错误日志：15 条
   警告日志：23 条
```

**核心指标：**

| 指标 | 说明 |
|------|------|
| 今日采集量 | 按 Source Tier 统计 |
| 任务成功率 | 最近 24 小时 |
| 平均延迟 | 采集 → 可用 |
| 队列积压情况 | 待处理任务数 |
| API 调用统计 | 按客户端统计 |

---

## 数据校验规则

### 入库校验

**Item 表：**
- ✅ `external_id` 或 `url` 唯一
- ✅ `source_id` 外键约束
- ✅ `fetched_at` 非空

**Content 表：**
- ✅ `canonical_hash` 唯一
- ✅ `first_seen_at` ≤ `last_seen_at`

---

### 业务校验

**重复采集检测：**
- 同一 Source 的重复采集不会生成重复 Item（通过 `external_id` 或 `url` 唯一约束）

**跨源去重：**
- 计算 `canonical_hash`（标准化后的标题 + 正文）
- 如果已存在相同 hash，复用已有 Content

---

## 未来扩展

### 生产版演进路径

| 组件 | 原型版 | 生产版 | 迁移成本 |
|------|--------|--------|---------|
| PostgreSQL | PostgreSQL 15 | CockroachDB | 低（SQL 兼容） |
| APScheduler | APScheduler | Airflow | 中（需重写 DAG） |
| Dramatiq | Dramatiq | Celery + Redis Cluster | 低（概念相同） |
| 本地文件系统 | 本地文件系统 | S3/MinIO | 低（抽象为 Storage Layer） |
| 单机部署 | `docker-compose up` | Kubernetes | 高（需容器化） |

**迁移策略：**
1. **数据库层**：CockroachDB 完全兼容 PostgreSQL 协议，只需修改连接字符串
2. **任务队列**：Celery 与 Dramatiq 概念相似（Producer/Worker），重写任务定义即可
3. **存储层**：实现统一的 Storage Interface，切换底层存储无需改业务逻辑
4. **调度器**：APScheduler 的作业定义可作为 Airflow DAG 的参考

---

### 待实现功能清单

**v2（增强版）：**
- [ ] 在线自学习（权重自动调整）
- [ ] 战略价值反馈接口（接收 cyber-nexus 数据）
- [ ] Web 界面（可选）
- [ ] 邮件通知（错误告警）

**v3（生产版）：**
- [ ] 分布式部署
- [ ] 消息队列（Kafka）
- [ ] 多租户模式
- [ ] 完整监控栈（Prometheus + Grafana）

---

### 与 cyber-nexus 的集成路径

**阶段 1：原型独立运行**
- cyber-pulse 独立运行，使用默认的维度 V 值
- 验证采集、标准化、治理流程

**阶段 2：API 对接**
- cyber-nexus 开发完成后，接入 Pull API
- cyber-nexus 开始消费增量数据

**阶段 3：反馈闭环**
- cyber-nexus 通过预留的 API 端点提供维度 V 评分
- Source Score 系统使用真实的维度 V 数据