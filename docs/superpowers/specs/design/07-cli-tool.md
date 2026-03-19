# CLI 工具

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 命令结构

**非交互式模式（脚本/终端直接执行）：**
```bash
./cli <模块> <子命令> [参数]
```

**交互式模式（`./cli` 或 `./cli shell`）：**
```bash
cyber-pulse> /<模块> <子命令> [参数]
```

---

## 模块与子命令

```
cyber-pulse CLI (v1.1)
├── source [子命令]
│   ├── list [--tier T0|T1|T2]
│   ├── add --name <name> --url <url> ...
│   ├── update <id> [--tier T1]
│   ├── remove <id>
│   ├── test <id>
│   └── stats
│
├── job [子命令]
│   ├── list [--status running|failed]
│   ├── run <source-id>
│   ├── cancel <job-id>
│   └── status <job-id>
│
├── content [子命令]
│   ├── list [--limit 10]
│   ├── get [--id <content-id>] [--since <timestamp>] [--until <timestamp>] [--source <name>] [--tier <T0|T1|T2>] [--limit <number>] [--format <json|markdown>]
│   └── stats
│
├── client [子命令]
│   ├── create --name <name> ...
│   ├── list
│   ├── update <id> ...
│   ├── disable <id>
│   ├── enable <id>
│   └── delete <id>
│
├── config [子命令]
│   ├── get <key>
│   ├── set <key> <value>
│   ├── list
│   └── reset
│
├── log [子命令]
│   ├── tail [-n N] [-f]
│   ├── errors [--since TIME] [--source <name>]
│   ├── search <text>
│   ├── stats
│   └── clear
│
├── diagnose [子命令]
│   ├── system
│   ├── sources [--pending]
│   ├── source <id>
│   └── errors
│
├── server [子命令]
│   ├── start
│   ├── stop
│   ├── restart
│   ├── status
│   ├── health
│   └── maintenance --generate-review-report
│
├── help
├── version
└── exit
```

---

## 交互式界面设计

**布局结构：**
```
┌─────────────────────────────────────────────────────────┐
│  🚀 cyber-pulse CLI (v1.1)                              │
│  Type '/help' for available commands                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Output Area: 命令执行结果/历史记录]                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
│  cyber-pulse> [Input Area]                              │
├─────────────────────────────────────────────────────────┤
│  Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: X │
└─────────────────────────────────────────────────────────┘
```

**初始进入时显示：**

```
┌─────────────────────────────────────────────────────────┐
│  🚀 cyber-pulse CLI (v1.1)                              │
│  Type '/help' for available commands                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Welcome to cyber-pulse!                                │
│                                                          │
│  System Status:                                         │
│  • API Server: 🟢 Running on port 8000                  │
│  • Database: 🟢 Connected                                │
│  • Redis: 🟢 Connected                                   │
│  • Active Sources: 12 (T0: 2, T1: 5, T2: 5)             │
│  • Scheduled Jobs: 1                                     │
│                                                          │
│  Recent Activity:                                       │
│  [2026-03-18 10:30:15] ✓ Source "安全客" added (T2)    │
│  [2026-03-18 10:30:20] 📅 Scheduled for collection      │
│                                                          │
│  Tips:                                                  │
│  • Run '/source list' to see all sources                │
│  • Run '/diagnose system' to check system health        │
│  • Run '/help' to see all commands                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
│  cyber-pulse>                                            │
├─────────────────────────────────────────────────────────┤
│  Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1 │
└─────────────────────────────────────────────────────────┘
```

**命令执行后显示：**

### 场景 1：成功执行（表格输出）
```
cyber-pulse> /source list --tier T1

┌──────────────────────────────────────────────┐
│  Sources (T1) - 5 items                      │
├──────────────────────────────────────────────┤
│  1. 安全客                                    │
│     URL: https://www.anquanke.com            │
│     Status: active | Score: 75.5             │
│                                              │
│  2. FreeBuf                                  │
│     URL: https://www.freebuf.com             │
│     Status: active | Score: 82.3             │
│                                              │
│  ...                                         │
└──────────────────────────────────────────────┘

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1
```

### 场景 2：失败执行（错误提示）
```
cyber-pulse> /source test invalid-id

❌ Error: Source not found

💡 Suggestion:
   • Run '/source list' to see available sources
   • Check the source ID or name

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1
```

### 场景 3：长时间任务（进度显示）
```
cyber-pulse> /job run security-news

🔄 Starting job for "安全客"...
⏳ Fetching data from source...
⏳ Processing 8 items...
✓ Job completed successfully
  • Retrieved: 8 items
  • Passed QC: 8 items
  • Failed: 0 items

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 0
```

### 场景 4：实时日志（流式输出）
```
cyber-pulse> /log tail -f

[2026-03-18 14:30:05] INFO     Task started: source_security-news
[2026-03-18 14:30:06] INFO     Fetching from RSS feed...
[2026-03-18 14:30:08] INFO     Retrieved 8 items
[2026-03-18 14:30:10] INFO     Normalizing content...
[2026-03-18 14:30:12] INFO     Quality check passed: 8/8
[2026-03-18 14:30:13] INFO     Task completed successfully
^C (Ctrl+C to stop)

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 0
```

---

## 界面行为规范

| 行为 | 说明 |
|------|------|
| **初始显示** | 欢迎信息 + 系统状态 + 最近活动 + 使用提示 |
| **命令执行** | 显示执行结果（表格/列表/错误信息） |
| **实时输出** | 长时间任务显示进度，日志显示实时流 |
| **错误提示** | 红色文字 ❌ + 修复建议 |
| **成功提示** | 绿色勾号 ✓ + 统计信息 |
| **命令历史** | ↑↓ 键浏览历史，Ctrl+R 搜索 |
| **自动补全** | Tab 键补全命令/参数 |

**状态栏字段：**
```
Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 2 | Memory: 256MB
```

---

## content get 命令详细参数

```bash
Usage: /content get [OPTIONS]

Options:
  --id <content-id>           # 按 ID 精确查询
  --since <timestamp>         # 起始时间（含），支持相对时间如 "2h"、"1d"
  --until <timestamp>         # 结束时间（含）
  --source <name>             # 按 Source 过滤
  --tier <T0|T1|T2>           # 按等级过滤
  --limit <number>            # 返回数量限制（默认 100，最大 1000）
  --format <json|markdown>    # 输出格式（默认 json）

Examples:
  /content get cnt_123                    # 精确查询
  /content get --since "2h"               # 最近 2 小时
  /content get --since "2026-03-18"       # 某天之后
  /content get --source "安全客" --limit 5
  /content get --tier T0 --limit 10       # 最新的 T0 内容
```

---

## 配置管理

**配置文件位置：**
```bash
# 默认配置
~/.cyber-pulse/config.yaml    # 用户级
./data/config.yaml            # 项目级（与数据同目录）
```

**配置示例：**
```yaml
api:
  port: 8000
  host: "0.0.0.0"
  cors_enabled: true

database:
  url: "postgresql://user:pass@localhost:5432/cyber_pulse"
  pool_size: 10

scheduler:
  enabled: true
  timezone: "Asia/Shanghai"
  unified_interval: "1h"  # 原型阶段统一调度间隔

retention:
  item_days: 365
  content_days: 365

logging:
  level: "INFO"
  format: "json"

wechat:
  use_rsshub: true  # 是否使用 RSSHub 包装微信公众号
  rsshub_url: "http://localhost:1200"
```

**CLI 操作：**
```bash
# 查看配置
./cli config get api.port

# 修改配置
./cli config set api.port 9000

# 列出所有配置
./cli config list
```