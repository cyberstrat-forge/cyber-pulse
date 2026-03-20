# Cyber-Pulse CLI 使用手册

## 概述

Cyber-Pulse CLI 是管理员命令行工具，用于管理情报源、任务调度、内容查询、客户端 API Key 和系统诊断。

### 安装与配置

```bash
# 安装（开发模式）
pip install -e ".[dev]"

# 验证安装
cyberpulse --version

# 环境变量配置
export DATABASE_URL="postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse"
export REDIS_URL="redis://localhost:6379/0"
```

### 全局命令

```bash
# 查看版本
cyberpulse version

# 启动交互式 Shell（自动补全）
cyberpulse shell

# 启动 API 服务器
cyberpulse server [--host 0.0.0.0] [--port 8000]
```

---

## 1. 情报源管理（Source）

### 1.1 列出情报源

```bash
cyberpulse source list [OPTIONS]

Options:
  --status [active|frozen|inactive]  按状态筛选
  --tier [T0|T1|T2|T3]               按分级筛选
  --type [rss|api|web|media]         按类型筛选
  --limit INT                        返回数量限制（默认 50）
```

**示例：**

```bash
# 列出所有活跃源
cyberpulse source list --status active

# 列出 T0 级别源
cyberpulse source list --tier T0

# 列出 RSS 类型源
cyberpulse source list --type rss
```

### 1.2 添加情报源

```bash
cyberpulse source add [OPTIONS] NAME TYPE

Arguments:
  NAME                      情报源名称
  TYPE                      情报源类型（rss, api, web, media）

Options:
  --tier [T0|T1|T2|T3]     情报源分级（默认 T2）
  --url TEXT               情报源 URL
  --config JSON            采集配置（JSON 格式）
  --schedule TEXT          调度间隔（cron 表达式）
```

**示例：**

```bash
# 添加 RSS 源
cyberpulse source add "安全客" rss \
  --tier T1 \
  --url "https://www.anquanke.com/rss.xml" \
  --schedule "0 */6 * * *"

# 添加 API 源（带配置）
cyberpulse source add "VirusTotal" api \
  --tier T0 \
  --url "https://www.virustotal.com/api/v3" \
  --config '{"api_key": "xxx", "rate_limit": 100}'
```

### 1.3 更新情报源

```bash
cyberpulse source update [OPTIONS] SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID（格式：src_xxxxxxxx）

Options:
  --name TEXT              新名称
  --tier [T0|T1|T2|T3]     新分级
  --status [active|frozen|inactive]  新状态
  --config JSON            新配置
```

**示例：**

```bash
# 更新分级
cyberpulse source update src_a1b2c3d4 --tier T0

# 冻结源
cyberpulse source update src_a1b2c3d4 --status frozen

# 更新配置
cyberpulse source update src_a1b2c3d4 --config '{"timeout": 30}'
```

### 1.4 删除情报源

```bash
cyberpulse source remove SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID
```

**示例：**

```bash
cyberpulse source remove src_a1b2c3d4
```

### 1.5 测试情报源

```bash
cyberpulse source test SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --timeout INT            超时时间（秒，默认 30）
```

**示例：**

```bash
# 测试源连接性
cyberpulse source test src_a1b2c3d4
```

### 1.6 查看源统计

```bash
cyberpulse source stats [OPTIONS]

Options:
  --source-id TEXT         指定源 ID
  --days INT               统计天数（默认 7）
```

**示例：**

```bash
# 查看所有源统计
cyberpulse source stats

# 查看指定源近 30 天统计
cyberpulse source stats --source-id src_a1b2c3d4 --days 30
```

---

## 2. 任务管理（Job）

### 2.1 列出任务

```bash
cyberpulse job list [OPTIONS]

Options:
  --status [pending|running|completed|failed]  按状态筛选
  --source-id TEXT                              按源筛选
  --limit INT                                   返回数量限制
```

**示例：**

```bash
# 列出失败任务
cyberpulse job list --status failed

# 列出指定源的任务
cyberpulse job list --source-id src_a1b2c3d4
```

### 2.2 运行任务

```bash
cyberpulse job run [OPTIONS] SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --force                  强制运行（忽略并发限制）
```

**示例：**

```bash
# 立即运行采集任务
cyberpulse job run src_a1b2c3d4

# 强制运行
cyberpulse job run src_a1b2c3d4 --force
```

### 2.3 取消任务

```bash
cyberpulse job cancel JOB_ID

Arguments:
  JOB_ID                    任务 ID
```

**示例：**

```bash
cyberpulse job cancel job_12345678
```

### 2.4 查看任务状态

```bash
cyberpulse job status JOB_ID

Arguments:
  JOB_ID                    任务 ID
```

**示例：**

```bash
cyberpulse job status job_12345678
```

### 2.5 调度定时任务

```bash
cyberpulse job schedule [OPTIONS] SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --interval INT           间隔秒数（最小 60）
  --cron TEXT              Cron 表达式
```

**示例：**

```bash
# 每小时调度
cyberpulse job schedule src_a1b2c3d4 --interval 3600

# 使用 cron 表达式（每天 6:00）
cyberpulse job schedule src_a1b2c3d4 --cron "0 6 * * *"
```

### 2.6 取消定时任务

```bash
cyberpulse job unschedule SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID
```

**示例：**

```bash
cyberpulse job unschedule src_a1b2c3d4
```

---

## 3. 内容管理（Content）

### 3.1 列出内容

```bash
cyberpulse content list [OPTIONS]

Options:
  --source-id TEXT         按源筛选
  --after DATETIME         时间范围起始
  --before DATETIME        时间范围结束
  --quality [high|medium|low]  按质量筛选
  --limit INT              返回数量限制
```

**示例：**

```bash
# 列出近 24 小时内容
cyberpulse content list --after "2026-03-19T00:00:00"

# 列出高质量内容
cyberpulse content list --quality high

# 列出指定源内容
cyberpulse content list --source-id src_a1b2c3d4
```

### 3.2 获取内容详情

```bash
cyberpulse content get CONTENT_ID

Arguments:
  CONTENT_ID                内容 ID（格式：cnt_YYYYMMDDHHMMSS_xxxxxxxx）
```

**示例：**

```bash
cyberpulse content get cnt_20260319120000_a1b2c3d4
```

### 3.3 查看内容统计

```bash
cyberpulse content stats [OPTIONS]

Options:
  --days INT               统计天数（默认 7）
  --by-source              按源分组统计
```

**示例：**

```bash
# 查看近 7 天统计
cyberpulse content stats

# 按源分组统计
cyberpulse content stats --by-source

# 近 30 天统计
cyberpulse content stats --days 30
```

---

## 4. 客户端管理（Client）

### 4.1 创建客户端

```bash
cyberpulse client create [OPTIONS] NAME

Arguments:
  NAME                      客户端名称

Options:
  --description TEXT       描述
  --expires DATETIME       过期时间
```

**示例：**

```bash
# 创建客户端
cyberpulse client create "分析系统" --description "下游分析系统"

# 创建带过期时间的客户端
cyberpulse client create "临时系统" --expires "2026-12-31T23:59:59"
```

**输出包含 API Key（仅显示一次，请妥善保存）：**
```
Client ID: cli_a1b2c3d4e5f6g7h8
API Key: cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4.2 列出客户端

```bash
cyberpulse client list [OPTIONS]

Options:
  --status [active|disabled]  按状态筛选
```

**示例：**

```bash
# 列出所有客户端
cyberpulse client list

# 列出活跃客户端
cyberpulse client list --status active
```

### 4.3 禁用客户端

```bash
cyberpulse client disable CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID（格式：cli_xxxxxxxxxxxxxxxx）
```

**示例：**

```bash
cyberpulse client disable cli_a1b2c3d4e5f6g7h8
```

### 4.4 启用客户端

```bash
cyberpulse client enable CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID
```

**示例：**

```bash
cyberpulse client enable cli_a1b2c3d4e5f6g7h8
```

### 4.5 删除客户端

```bash
cyberpulse client delete CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID
```

**示例：**

```bash
cyberpulse client delete cli_a1b2c3d4e5f6g7h8
```

---

## 5. 配置管理（Config）

### 5.1 获取配置

```bash
cyberpulse config get KEY

Arguments:
  KEY                       配置键名
```

**示例：**

```bash
cyberpulse config get database_url
```

### 5.2 设置配置

```bash
cyberpulse config set KEY VALUE

Arguments:
  KEY                       配置键名
  VALUE                     配置值
```

**示例：**

```bash
cyberpulse config set log_level DEBUG
```

### 5.3 列出所有配置

```bash
cyberpulse config list
```

**示例：**

```bash
cyberpulse config list
```

### 5.4 重置配置

```bash
cyberpulse config reset [KEY]

Arguments:
  KEY                       配置键名（可选，不指定则重置全部）
```

**示例：**

```bash
# 重置单个配置
cyberpulse config reset log_level

# 重置所有配置
cyberpulse config reset
```

---

## 6. 日志管理（Log）

### 6.1 实时日志

```bash
cyberpulse log tail [OPTIONS]

Options:
  --follow, -f             持续跟踪
  --lines INT              显示行数（默认 100）
  --level [DEBUG|INFO|WARNING|ERROR]  日志级别过滤
```

**示例：**

```bash
# 查看最近日志
cyberpulse log tail

# 持续跟踪错误日志
cyberpulse log tail -f --level ERROR

# 显示最近 500 行
cyberpulse log tail --lines 500
```

### 6.2 错误日志

```bash
cyberpulse log errors [OPTIONS]

Options:
  --since DATETIME         起始时间
  --limit INT              返回数量限制
```

**示例：**

```bash
# 查看最近错误
cyberpulse log errors

# 查看指定时间后的错误
cyberpulse log errors --since "2026-03-19T00:00:00"
```

### 6.3 搜索日志

```bash
cyberpulse log search PATTERN

Arguments:
  PATTERN                   搜索模式（正则表达式）

Options:
  --level [DEBUG|INFO|WARNING|ERROR]  日志级别过滤
  --limit INT                          返回数量限制
```

**示例：**

```bash
# 搜索包含 "timeout" 的日志
cyberpulse log search "timeout"

# 搜索指定源相关日志
cyberpulse log search "src_a1b2c3d4"

# 使用正则表达式
cyberpulse log search "error.*source"
```

### 6.4 日志统计

```bash
cyberpulse log stats [OPTIONS]

Options:
  --days INT               统计天数（默认 7）
```

**示例：**

```bash
# 查看近 7 天日志统计
cyberpulse log stats

# 查看近 30 天统计
cyberpulse log stats --days 30
```

---

## 7. 诊断工具（Diagnose）

### 7.1 系统诊断

```bash
cyberpulse diagnose system
```

**输出示例：**
```
System Health Check
===================
Database: ✓ Connected (PostgreSQL 15.2)
Redis: ✓ Connected (Redis 7.0)
Scheduler: ✓ Running (3 jobs scheduled)
Worker: ✓ Running (2 workers active)

Storage:
  Database size: 1.2 GB
  Redis memory: 256 MB

Recent Errors: 12 (last 24h)
```

### 7.2 源诊断

```bash
cyberpulse diagnose sources [OPTIONS]

Options:
  --source-id TEXT         指定源 ID
```

**示例：**

```bash
# 诊断所有源
cyberpulse diagnose sources

# 诊断指定源
cyberpulse diagnose sources --source-id src_a1b2c3d4
```

**输出示例：**
```
Source Diagnostics
==================
src_a1b2c3d4 (安全客)
  Status: Active
  Tier: T1
  Last Collection: 2026-03-19 14:30:00 (2 hours ago)
  Success Rate: 98.5% (last 100 jobs)
  Average Items: 45/collection
  Warnings: None

src_e5f6g7h8 (Example Feed)
  Status: Frozen
  Last Collection: Never
  Warnings:
    - Source is frozen
    - No successful collections
```

### 7.3 错误诊断

```bash
cyberpulse diagnose errors [OPTIONS]

Options:
  --hours INT              时间范围（默认 24）
  --limit INT              返回数量限制
```

**示例：**

```bash
# 诊断近 24 小时错误
cyberpulse diagnose errors

# 诊断近 72 小时错误
cyberpulse diagnose errors --hours 72
```

**输出示例：**
```
Error Analysis (Last 24h)
=========================
Total Errors: 12

By Type:
  ConnectionError: 5
  TimeoutError: 4
  ValueError: 3

By Source:
  src_a1b2c3d4: 8 errors
  src_e5f6g7h8: 4 errors

Top Errors:
  1. ConnectionError: Redis connection refused (5 occurrences)
     Source: src_a1b2c3d4
     Last seen: 2026-03-19 15:45:00

  2. TimeoutError: Request timed out after 30s (4 occurrences)
     Source: src_e5f6g7h8
     Last seen: 2026-03-19 14:20:00
```

---

## 最佳实践

### 日常运维

```bash
# 1. 检查系统健康状态
cyberpulse diagnose system

# 2. 查看错误日志
cyberpulse log errors --limit 20

# 3. 检查失败任务
cyberpulse job list --status failed

# 4. 查看内容统计
cyberpulse content stats --days 1
```

### 新源接入流程

```bash
# 1. 添加源
cyberpulse source add "新源名称" rss --url "https://example.com/feed.xml" --tier T2

# 2. 测试连接
cyberpulse source test src_xxxxxxxx

# 3. 手动运行一次采集
cyberpulse job run src_xxxxxxxx

# 4. 确认采集成功后设置调度
cyberpulse job schedule src_xxxxxxxx --interval 3600

# 5. 观察一段时间后调整分级
cyberpulse source update src_xxxxxxxx --tier T1
```

### 问题排查流程

```bash
# 1. 系统诊断
cyberpulse diagnose system

# 2. 查看错误分析
cyberpulse diagnose errors --hours 72

# 3. 检查特定源状态
cyberpulse diagnose sources --source-id src_xxxxxxxx

# 4. 搜索相关日志
cyberpulse log search "src_xxxxxxxx" --level ERROR

# 5. 查看任务状态
cyberpulse job list --source-id src_xxxxxxxx --status failed
```

### 客户端管理流程

```bash
# 1. 创建客户端
cyberpulse client create "分析系统" --description "下游分析系统"
# 保存输出的 API Key

# 2. 验证客户端
curl -H "Authorization: Bearer cp_live_xxx" http://localhost:8000/api/v1/contents

# 3. 定期审计客户端
cyberpulse client list

# 4. 禁用不再使用的客户端
cyberpulse client disable cli_xxxxxxxxxxxxxxxx
```

---

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接串 | 必需 |
| `REDIS_URL` | Redis 连接串 | 必需 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `API_HOST` | API 监听地址 | 0.0.0.0 |
| `API_PORT` | API 监听端口 | 8000 |

---

## 错误码参考

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| `SOURCE_NOT_FOUND` | 情报源不存在 | 检查源 ID 是否正确 |
| `SOURCE_FROZEN` | 情报源已冻结 | 解冻或使用其他源 |
| `JOB_RUNNING` | 任务正在运行 | 等待完成或取消后重试 |
| `CLIENT_DISABLED` | 客户端已禁用 | 启用客户端或创建新的 |
| `RATE_LIMITED` | 请求过于频繁 | 降低请求频率 |
| `CONNECTION_ERROR` | 数据库/Redis 连接失败 | 检查服务状态 |

---

## 附录

### ID 格式规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 情报源 | `src_{uuid8}` | src_a1b2c3d4 |
| 内容 | `cnt_{YYYYMMDDHHMMSS}_{uuid8}` | cnt_20260319120000_a1b2c3d4 |
| 任务 | `job_{uuid8}` | job_a1b2c3d4 |
| 客户端 | `cli_{uuid16}` | cli_a1b2c3d4e5f6g7h8 |
| API Key | `cp_live_{hex32}` | cp_live_xxx... |

### Source 分级说明

| 分级 | 含义 | 评分范围 | 采集频率 |
|------|------|----------|----------|
| T0 | 核心战略源 | ≥80 | 每小时 |
| T1 | 重要参考源 | 60-80 | 每 2-4 小时 |
| T2 | 普通观察源 | 40-60 | 每 6-12 小时 |
| T3 | 观察/降频源 | <40 | 每 24 小时 |

### Source 状态说明

| 状态 | 说明 |
|------|------|
| active | 活跃，正常采集 |
| frozen | 冻结，暂停采集 |
| inactive | 失效，不再使用 |