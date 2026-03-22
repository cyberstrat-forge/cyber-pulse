# Cyber-Pulse CLI 使用手册

## 概述

Cyber-Pulse CLI 是管理员命令行工具，用于管理情报源、任务调度、内容查询、客户端 API Key 和系统诊断。

### 安装与配置

```bash
# 安装（开发模式）
pip install -e ".[dev]"

# 验证安装
cyber-pulse --version

# 环境变量配置
export DATABASE_URL="postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse"
export REDIS_URL="redis://localhost:6379/0"
```

### 全局命令

```bash
# 查看版本
cyber-pulse version

# 启动交互式 Shell（自动补全）
cyber-pulse shell

# 启动 API 服务器
cyber-pulse server start [--host 0.0.0.0] [--port 8000]

# 查看 API 服务器状态
cyber-pulse server status
```

---

## 1. 情报源管理（Source）

### 1.1 列出情报源

```bash
cyber-pulse source list [OPTIONS]

Options:
  --status [active|frozen|inactive]  按状态筛选
  --tier [T0|T1|T2|T3]               按分级筛选
  --type [rss|api|web|media]         按类型筛选
  --limit INT                        返回数量限制（默认 50）
```

**示例：**

```bash
# 列出所有活跃源
cyber-pulse source list --status active

# 列出 T0 级别源
cyber-pulse source list --tier T0

# 列出 RSS 类型源
cyber-pulse source list --type rss
```

### 1.2 添加情报源

```bash
cyber-pulse source add [OPTIONS] NAME CONNECTOR URL

Arguments:
  NAME                      情报源名称
  CONNECTOR                 情报源类型（rss, api, web, media）
  URL                       情报源 URL

Options:
  --tier [T0|T1|T2|T3]     情报源分级（默认 T2）
  --yes, -y                跳过确认提示
```

**示例：**

```bash
# 添加 RSS 源
cyber-pulse source add "安全客" rss "https://www.anquanke.com/rss.xml" \
  --tier T1 --yes

# 添加 API 源（自动执行准入流程）
cyber-pulse source add "VirusTotal" api "https://www.virustotal.com/api/v3" \
  --tier T0 --yes
```

### 1.3 更新情报源

```bash
cyber-pulse source update [OPTIONS] SOURCE_ID

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
cyber-pulse source update src_a1b2c3d4 --tier T0

# 冻结源
cyber-pulse source update src_a1b2c3d4 --status frozen

# 更新配置
cyber-pulse source update src_a1b2c3d4 --config '{"timeout": 30}'
```

### 1.4 删除情报源

```bash
cyber-pulse source remove SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID
```

**示例：**

```bash
cyber-pulse source remove src_a1b2c3d4
```

### 1.5 测试情报源

```bash
cyber-pulse source test SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --timeout INT            超时时间（秒，默认 30）
```

**示例：**

```bash
# 测试源连接性
cyber-pulse source test src_a1b2c3d4
```

### 1.6 查看源统计

```bash
cyber-pulse source stats [OPTIONS]

Options:
  --source-id TEXT         指定源 ID
  --days INT               统计天数（默认 7）
```

**示例：**

```bash
# 查看所有源统计
cyber-pulse source stats

# 查看指定源近 30 天统计
cyber-pulse source stats --source-id src_a1b2c3d4 --days 30
```

---

## 2. 任务管理（Job）

### 2.1 列出任务

```bash
cyber-pulse job list [OPTIONS]

Options:
  --status [pending|running|completed|failed]  按状态筛选
  --source-id TEXT                              按源筛选
  --limit INT                                   返回数量限制
```

**示例：**

```bash
# 列出失败任务
cyber-pulse job list --status failed

# 列出指定源的任务
cyber-pulse job list --source-id src_a1b2c3d4
```

### 2.2 运行任务

```bash
cyber-pulse job run [OPTIONS] SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --force                  强制运行（忽略并发限制）
```

**示例：**

```bash
# 立即运行采集任务
cyber-pulse job run src_a1b2c3d4

# 强制运行
cyber-pulse job run src_a1b2c3d4 --force
```

### 2.3 取消任务

```bash
cyber-pulse job cancel JOB_ID

Arguments:
  JOB_ID                    任务 ID
```

**示例：**

```bash
cyber-pulse job cancel job_12345678
```

### 2.4 查看任务状态

```bash
cyber-pulse job status JOB_ID

Arguments:
  JOB_ID                    任务 ID
```

**示例：**

```bash
cyber-pulse job status job_12345678
```

### 2.5 调度定时任务

```bash
cyber-pulse job schedule [OPTIONS] SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID

Options:
  --interval INT           间隔秒数（最小 60）
  --cron TEXT              Cron 表达式
```

**示例：**

```bash
# 每小时调度
cyber-pulse job schedule src_a1b2c3d4 --interval 3600

# 使用 cron 表达式（每天 6:00）
cyber-pulse job schedule src_a1b2c3d4 --cron "0 6 * * *"
```

### 2.6 取消定时任务

```bash
cyber-pulse job unschedule SOURCE_ID

Arguments:
  SOURCE_ID                 情报源 ID
```

**示例：**

```bash
cyber-pulse job unschedule src_a1b2c3d4
```

---

## 3. 内容管理（Content）

### 3.1 列出内容

```bash
cyber-pulse content list [OPTIONS]

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
cyber-pulse content list --after "2026-03-19T00:00:00"

# 列出高质量内容
cyber-pulse content list --quality high

# 列出指定源内容
cyber-pulse content list --source-id src_a1b2c3d4
```

### 3.2 获取内容详情

```bash
cyber-pulse content get CONTENT_ID

Arguments:
  CONTENT_ID                内容 ID（格式：cnt_YYYYMMDDHHMMSS_xxxxxxxx）
```

**示例：**

```bash
cyber-pulse content get cnt_20260319120000_a1b2c3d4
```

### 3.3 查看内容统计

```bash
cyber-pulse content stats [OPTIONS]

Options:
  --days INT               统计天数（默认 7）
  --by-source              按源分组统计
```

**示例：**

```bash
# 查看近 7 天统计
cyber-pulse content stats

# 按源分组统计
cyber-pulse content stats --by-source

# 近 30 天统计
cyber-pulse content stats --days 30
```

---

## 4. 客户端管理（Client）

### 4.1 创建客户端

```bash
cyber-pulse client create [OPTIONS] NAME

Arguments:
  NAME                      客户端名称

Options:
  --description TEXT       描述
  --expires DATETIME       过期时间
```

**示例：**

```bash
# 创建客户端
cyber-pulse client create "分析系统" --description "下游分析系统"

# 创建带过期时间的客户端
cyber-pulse client create "临时系统" --expires "2026-12-31T23:59:59"
```

**输出包含 API Key（仅显示一次，请妥善保存）：**
```
Client ID: cli_a1b2c3d4e5f6g7h8
API Key: cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4.2 列出客户端

```bash
cyber-pulse client list [OPTIONS]

Options:
  --status [active|disabled]  按状态筛选
```

**示例：**

```bash
# 列出所有客户端
cyber-pulse client list

# 列出活跃客户端
cyber-pulse client list --status active
```

### 4.3 禁用客户端

```bash
cyber-pulse client disable CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID（格式：cli_xxxxxxxxxxxxxxxx）
```

**示例：**

```bash
cyber-pulse client disable cli_a1b2c3d4e5f6g7h8
```

### 4.4 启用客户端

```bash
cyber-pulse client enable CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID
```

**示例：**

```bash
cyber-pulse client enable cli_a1b2c3d4e5f6g7h8
```

### 4.5 删除客户端

```bash
cyber-pulse client delete CLIENT_ID

Arguments:
  CLIENT_ID                 客户端 ID
```

**示例：**

```bash
cyber-pulse client delete cli_a1b2c3d4e5f6g7h8
```

---

## 5. 配置管理（Config）

### 5.1 获取配置

```bash
cyber-pulse config get KEY

Arguments:
  KEY                       配置键名
```

**示例：**

```bash
cyber-pulse config get database_url
```

### 5.2 设置配置

```bash
cyber-pulse config set KEY VALUE

Arguments:
  KEY                       配置键名
  VALUE                     配置值
```

**示例：**

```bash
cyber-pulse config set log_level DEBUG
```

### 5.3 列出所有配置

```bash
cyber-pulse config list
```

**示例：**

```bash
cyber-pulse config list
```

### 5.4 重置配置

```bash
cyber-pulse config reset [KEY]

Arguments:
  KEY                       配置键名（可选，不指定则重置全部）
```

**示例：**

```bash
# 重置单个配置
cyber-pulse config reset log_level

# 重置所有配置
cyber-pulse config reset
```

---

## 6. 日志管理（Log）

### 6.1 实时日志

```bash
cyber-pulse log tail [OPTIONS]

Options:
  --follow, -f             持续跟踪
  --lines INT              显示行数（默认 100）
  --level [DEBUG|INFO|WARNING|ERROR]  日志级别过滤
```

**示例：**

```bash
# 查看最近日志
cyber-pulse log tail

# 持续跟踪错误日志
cyber-pulse log tail -f --level ERROR

# 显示最近 500 行
cyber-pulse log tail --lines 500
```

### 6.2 错误日志

```bash
cyber-pulse log errors [OPTIONS]

Options:
  --since, -s TEXT         起始时间（如 '1h', '24h', '7d'）
  --source TEXT            按日志源过滤
  --lines, -n INT          返回数量限制（默认 50）
  --format, -f TEXT        输出格式：text 或 json
```

**示例：**

```bash
# 查看最近错误
cyber-pulse log errors

# 查看最近 24 小时错误
cyber-pulse log errors --since 24h

# JSON 格式输出（便于程序化处理）
cyber-pulse log errors --format json

# 按日志源过滤
cyber-pulse log errors --source cyberpulse.tasks
```

### 6.3 搜索日志

```bash
cyber-pulse log search PATTERN

Arguments:
  PATTERN                   搜索模式（支持关键词匹配）

Options:
  --lines, -n INT          返回数量限制（默认 50）
  --level, -l TEXT         日志级别过滤（DEBUG, INFO, WARNING, ERROR, CRITICAL）
  --format, -f TEXT        输出格式：text 或 json
```

**示例：**

```bash
# 搜索包含 "timeout" 的日志
cyber-pulse log search "timeout"

# 搜索指定源相关日志
cyber-pulse log search "src_a1b2c3d4"

# JSON 格式输出
cyber-pulse log search "error" --format json

# 按级别过滤
cyber-pulse log search "connection" --level ERROR
```

### 6.4 日志统计

```bash
cyber-pulse log stats [OPTIONS]

Options:
  --days INT               统计天数（默认 7）
```

**示例：**

```bash
# 查看近 7 天日志统计
cyber-pulse log stats

# 查看近 30 天统计
cyber-pulse log stats --days 30
```

### 6.5 日志导出

```bash
cyber-pulse log export [OPTIONS]

Options:
  --output, -o TEXT        输出文件路径（必需）
  --since, -s TEXT         导出起始时间（如 '1h', '24h', '7d'）
  --level, -l TEXT         按日志级别过滤
```

**示例：**

```bash
# 导出所有日志到文件
cyber-pulse log export --output /tmp/cyberpulse.log

# 导出最近 24 小时的日志
cyber-pulse log export --output /tmp/recent.log --since 24h

# 仅导出错误日志
cyber-pulse log export --output /tmp/errors.log --level ERROR
```

### 6.6 日志清理

```bash
cyber-pulse log clear [OPTIONS]

Options:
  --older-than, -o TEXT    清理指定时间前的日志（默认 7d）
  --yes, -y                跳过确认提示
```

**示例：**

```bash
# 清理 7 天前的日志（需要确认）
cyber-pulse log clear

# 清理 30 天前的日志（跳过确认）
cyber-pulse log clear --older-than 30d --yes
```

**注意：** 日志清理是不可逆操作，建议在清理前先导出日志备份。

---

## 7. 诊断工具（Diagnose）

### 7.1 系统诊断

```bash
cyber-pulse diagnose system
```

**输出示例：**
```
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

**注意：** API Service 和 Task Queue 检查在本地开发环境中可能显示为"not reachable"，这是正常的。

### 7.2 源诊断

```bash
cyber-pulse diagnose sources [OPTIONS]

Options:
  --pending, -p            仅显示待审核源
  --tier [T0|T1|T2|T3]     按分级筛选
```

**示例：**

```bash
# 诊断所有源
cyber-pulse diagnose sources

# 仅显示待审核源
cyber-pulse diagnose sources --pending

# 按分级筛选
cyber-pulse diagnose sources --tier T1
```

**输出包含：**
- 源状态汇总（Active/Frozen/Removed）
- 待审核源列表（含原因）
- 观察期即将结束的源
- **Recent Collection Activity 表格**（显示最后采集时间、Items 数量、状态）

**采集状态说明：**
| 状态 | 说明 |
|------|------|
| Fresh | 最近 1 小时内采集 |
| Recent | 最近 24 小时内采集 |
| Stale | 超过 24 小时未采集 |
| Never | 从未采集 |

### 7.3 错误诊断

```bash
cyber-pulse diagnose errors [OPTIONS]

Options:
  --since, -s TEXT         时间范围（如 '1h', '24h', '7d'）
  --source TEXT            按源 ID 过滤
```

**示例：**

```bash
# 诊断最近 24 小时错误
cyber-pulse diagnose errors

# 诊断最近 72 小时错误
cyber-pulse diagnose errors --since 72h

# 按源过滤
cyber-pulse diagnose errors --source src_a1b2c3d4
```

**输出示例：**
```
Error Analysis
==============

Rejected Items:
  Found 5 rejected items
  ┌─────────────┬──────────┬────────────────────┬──────────────────────────┬─────────────────┐
  │ Item ID     │ Source   │ Title              │ Rejection Reason         │ Fetched         │
  ├─────────────┼──────────┼────────────────────┼──────────────────────────┼─────────────────┤
  │ item_abc123 │ src_xyz  │ Test Item Title    │ Title too short; Empty... │ 2026-03-19 14:30│
  └─────────────┴──────────┴────────────────────┴──────────────────────────┴─────────────────┘

Recent Errors from Logs:
  Found 3 error entries
  ERROR   2026-03-19 15:45:00,123 cyberpulse.tasks - Connection timeout...
```

**注意：** `diagnose errors` 现在会显示 Rejection Reason 列，展示 Item 被拒绝的具体原因（从 `raw_metadata["rejection_reason"]` 提取）。

---

## 最佳实践

### 日常运维

```bash
# 1. 检查系统健康状态
cyber-pulse diagnose system

# 2. 查看错误日志
cyber-pulse log errors --limit 20

# 3. 检查失败任务
cyber-pulse job list --status failed

# 4. 查看内容统计
cyber-pulse content stats --days 1
```

### 新源接入流程

```bash
# 1. 添加源
cyber-pulse source add "新源名称" rss "https://example.com/feed.xml" --tier T2 --yes

# 2. 测试连接
cyber-pulse source test src_xxxxxxxx

# 3. 手动运行一次采集
cyber-pulse job run src_xxxxxxxx

# 4. 确认采集成功后设置调度
cyber-pulse job schedule src_xxxxxxxx --interval 3600

# 5. 观察一段时间后调整分级
cyber-pulse source update src_xxxxxxxx --tier T1
```

### 问题排查流程

```bash
# 1. 系统诊断
cyber-pulse diagnose system

# 2. 查看错误分析
cyber-pulse diagnose errors --hours 72

# 3. 检查特定源状态
cyber-pulse diagnose sources --source-id src_xxxxxxxx

# 4. 搜索相关日志
cyber-pulse log search "src_xxxxxxxx" --level ERROR

# 5. 查看任务状态
cyber-pulse job list --source-id src_xxxxxxxx --status failed
```

### 客户端管理流程

```bash
# 1. 创建客户端
cyber-pulse client create "分析系统" --description "下游分析系统"
# 保存输出的 API Key

# 2. 验证客户端
curl -H "Authorization: Bearer cp_live_xxx" http://localhost:8000/api/v1/contents

# 3. 定期审计客户端
cyber-pulse client list

# 4. 禁用不再使用的客户端
cyber-pulse client disable cli_xxxxxxxxxxxxxxxx
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