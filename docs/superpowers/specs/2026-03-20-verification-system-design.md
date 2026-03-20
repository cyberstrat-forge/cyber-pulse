# cyber-pulse 验证系统设计文档

**版本：** v1.0
**日期：** 2026-03-20
**作者：** 老罗
**状态：** 待批准

---

## 1. 概述

### 1.1 目标

构建 cyber-pulse 验证系统，用于：

1. **部署验证** - 确认系统部署/配置正确
2. **功能验证** - 确认完整 workflow 正常运行
3. **持续迭代** - 支持后续版本迭代时的回归验证

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| 复用现有能力 | 利用现有 CLI 命令，不开发新的验证工具 |
| 环境分离 | 验证脚本与生产环境独立，不影响部署 |
| 详细日志 | 验证失败时输出完整日志，便于定位问题 |
| 渐进式验证 | 分级验证，问题早发现早解决 |

---

## 2. 验证标准

### 2.1 分级验证模型

```
┌─────────────────────────────────────────────────────────────────┐
│ Level 1: 系统就绪                                                │
├─────────────────────────────────────────────────────────────────┤
│ 验证目标：应用部署/配置是否正确                                   │
│                                                                 │
│ 检查项：                                                         │
│ □ 数据库连接正常                                                 │
│ □ Redis 连接正常                                                 │
│ □ API 服务响应                                                   │
│ □ Worker 运行中                                                  │
│ □ Scheduler 运行中                                               │
│                                                                 │
│ 失败原因：部署/配置问题                                           │
│ 失败处理：停止验证，输出错误日志                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Level 2: 功能验证                                                │
├─────────────────────────────────────────────────────────────────┤
│ 验证目标：完整 workflow 是否正常                                  │
│                                                                 │
│ 检查项：                                                         │
│ □ API Client 管理（create/list/disable/enable/delete）           │
│ □ 情报源添加 + 连接测试                                          │
│ □ 采集任务执行                                                   │
│ □ 标准化 + 质量检查流程                                          │
│ □ Content 数据生成                                               │
│ □ CLI 查询数据                                                   │
│ □ API 查询数据（认证 + 数据接口）                                 │
│                                                                 │
│ 失败原因：应用逻辑问题                                            │
│ 失败处理：输出详细日志，定位问题                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 验证流程

```
Level 1: 系统就绪
    │
    ├─ 通过 → 继续 Level 2
    │
    └─ 失败 → 停止，输出错误日志，定位部署/配置问题

Level 2: 功能验证
    │
    ├─ 通过 → 验证完成，系统可用
    │
    └─ 失败 → 输出详细日志，定位应用逻辑问题
```

### 2.3 通过/失败判定

| 等级 | 通过条件 | 失败含义 |
|------|----------|----------|
| Level 1 | 所有检查项 ✓ | 部署/配置有误 |
| Level 2 | 所有检查项 ✓ | 应用逻辑有误 |

**注意：** 数据质量（REJECTED items）不作为验证失败条件。REJECTED items 是正常的业务结果，反映情报源内容质量问题，非 cyber-pulse 应用问题。

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        验证系统架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  宿主机                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Makefile                                                 │   │
│  │   └── make verify → 调用 scripts/verify.sh              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ scripts/verify.sh                                        │   │
│  │   ├── Level 1: 系统就绪检查                              │   │
│  │   ├── Level 2: 功能验证                                  │   │
│  │   └── 输出验证报告                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ sources.yaml                                             │   │
│  │   └── 预设情报源清单                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼ docker exec                         │
│                                                                 │
│  Docker 容器                                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ cyber-pulse CLI                                          │   │
│  │   ├── diagnose system                                    │   │
│  │   ├── client create/list/disable/enable/delete           │   │
│  │   ├── source add --test                                  │   │
│  │   ├── job run                                            │   │
│  │   └── content list                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 文件结构

```
cyber-pulse/
├── Makefile                    # 任务入口
├── scripts/
│   └── verify.sh               # 验证脚本
└── sources.yaml                # 预设情报源清单
```

### 3.3 与生产环境的关系

| 环境 | 文件 | 说明 |
|------|------|------|
| 生产环境 | `docker-compose.yml` | 核心服务，无验证组件 |
| 验证环境 | `scripts/verify.sh` | 验证脚本，独立于生产 |

验证脚本在宿主机运行，通过 `docker exec` 调用容器内的 CLI 命令，无需修改生产部署配置。

---

## 4. 详细设计

### 4.1 验证脚本 (scripts/verify.sh)

#### 4.1.1 脚本结构

```bash
#!/bin/bash
set -e

# 配置
CONTAINER_API="cyberpulse-api"
CONTAINER_WORKER="cyberpulse-worker"
CONTAINER_SCHEDULER="cyberpulse-scheduler"
SOURCES_FILE="sources.yaml"
OUTPUT_FILE=""

# 解析参数
parse_args() { ... }

# Level 1: 系统就绪
verify_level1() { ... }

# Level 2: 功能验证
verify_level2() { ... }

# 主流程
main() {
    verify_level1
    verify_level2
    print_report
}

main "$@"
```

#### 4.1.2 Level 1 验证逻辑

```bash
verify_level1() {
    echo "=== Level 1: 系统就绪 ==="

    # 数据库 + Redis 检查
    docker exec $CONTAINER_API cyber-pulse diagnose system || {
        log_error "Level 1 失败: 系统诊断未通过"
        exit 1
    }

    # Worker 运行检查
    docker ps --filter "name=$CONTAINER_WORKER" --filter "status=running" | grep -q $CONTAINER_WORKER || {
        log_error "Level 1 失败: Worker 未运行"
        exit 1
    }

    # Scheduler 运行检查
    docker ps --filter "name=$CONTAINER_SCHEDULER" --filter "status=running" | grep -q $CONTAINER_SCHEDULER || {
        log_error "Level 1 失败: Scheduler 未运行"
        exit 1
    }

    echo "Level 1: ✓ 通过"
}
```

#### 4.1.3 Level 2 验证逻辑

```bash
verify_level2() {
    echo "=== Level 2: 功能验证 ==="

    # 1. API Client 管理
    verify_api_client_management

    # 2. 情报源管理
    verify_source_management

    # 3. 数据采集
    verify_data_collection

    # 4. API 查询
    verify_api_query

    # 5. 清理
    cleanup_verify_client

    echo "Level 2: ✓ 通过"
}
```

#### 4.1.4 API Client 验证

```bash
verify_api_client_management() {
    # 创建测试 Client
    RESULT=$(docker exec $CONTAINER_API cyber-pulse client create verify_client)
    API_KEY=$(echo "$RESULT" | grep "API Key:" | awk '{print $3}')

    # 列出 Client
    docker exec $CONTAINER_API cyber-pulse client list | grep -q "verify_client"

    # 暂停 Client
    CLIENT_ID=$(docker exec $CONTAINER_API cyber-pulse client list | grep "verify_client" | awk '{print $2}')
    docker exec $CONTAINER_API cyber-pulse client disable $CLIENT_ID

    # 启用 Client
    docker exec $CONTAINER_API cyber-pulse client enable $CLIENT_ID

    # 保存 API Key 供后续使用
    echo $API_KEY > /tmp/cyberpulse_verify.key
}
```

#### 4.1.5 情报源验证

```bash
verify_source_management() {
    # 从 sources.yaml 读取情报源
    # 使用 yq 或 Python 解析 YAML

    # 添加每个情报源
    for source in $SOURCES; do
        docker exec $CONTAINER_API cyber-pulse source add \
            "$name" "$connector_type" "$url" --tier "$tier" --test
    done
}
```

### 4.2 情报源清单 (sources.yaml)

#### 4.2.1 格式定义

```yaml
# sources.yaml - 验证用情报源清单
#
# 说明：
# - 这些情报源用于验证 cyber-pulse 功能是否正常
# - 应选择稳定、公开、可访问的情报源
# - 由人工筛选，确保采集失败是应用问题而非情报源问题

sources:
  # RSS 源示例
  - name: 安全客
    connector_type: rss
    config:
      feed_url: https://www.anquanke.com/vul/rss.xml
    tier: T2

  - name: FreeBuf
    connector_type: rss
    config:
      feed_url: https://www.freebuf.com/feed
    tier: T2

  # 更多情报源...
```

#### 4.2.2 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | ✅ | 情报源名称，唯一 |
| `connector_type` | ✅ | 类型：rss / api / web / media |
| `config` | ✅ | Connector 配置 |
| `tier` | 可选 | T0-T3，默认 T2 |

#### 4.2.3 config 字段结构

```yaml
# RSS
config:
  feed_url: https://example.com/feed.xml

# API
config:
  url: https://api.example.com/data
  api_key: xxx

# Web
config:
  url: https://example-blog.com

# Media (YouTube 等)
config:
  url: https://youtube.com/channel/xxx
  api_key: xxx
```

### 4.3 Makefile 入口

```makefile
# Makefile

.PHONY: verify

# 验证系统
verify:
	@echo "开始验证 cyber-pulse..."
	@./scripts/verify.sh

# 验证并保存报告
verify-report:
	@echo "验证并生成报告..."
	@./scripts/verify.sh --output logs/verify-report.md
```

---

## 5. 验证报告

### 5.1 终端输出格式

```
╭─────────────────────────────────────────────────────────────────╮
│                  cyber-pulse 验证报告                           │
│                    2026-03-20 15:30:00                         │
╰─────────────────────────────────────────────────────────────────╯

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Level 1: 系统就绪 ──────────────────────────────────────── ✓ 通过
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ Database: connected
  ✓ Redis: connected
  ✓ API: healthy
  ✓ Worker: running
  ✓ Scheduler: running

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Level 2: 功能验证 ──────────────────────────────────────── ✓ 通过
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[API Client 管理]
  ✓ client create: verify_client created
  ✓ client list: 1 client found
  ✓ client disable: suspended
  ✓ client enable: activated

[情报源管理]
  ✓ 安全客: added, connection test passed
  ✓ FreeBuf: added, connection test passed
  ✓ Hacker News: added, connection test passed

[数据采集]
  ✓ 安全客: 20 items collected, 18 passed quality gate
  ✓ FreeBuf: 15 items collected, 15 passed quality gate
  ✓ Hacker News: 30 items collected, 28 passed quality gate

[数据统计]
  总采集:    65 items
  质量通过:  61 items (93.8%)
  质量拒绝:  4 items (6.2%)
  去重后:    58 contents

[API 查询]
  ✓ Content API: 58 items returned
  ✓ Cursor pagination: working

[清理]
  ✓ verify_client deleted

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
结论: 验证通过 ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 5.2 Markdown 文件格式

```markdown
# cyber-pulse 验证报告

**时间：** 2026-03-20 15:30:00
**结果：** ✓ 通过

---

## Level 1: 系统就绪

| 检查项 | 状态 |
|--------|------|
| Database | ✓ connected |
| Redis | ✓ connected |
| API | ✓ healthy |
| Worker | ✓ running |
| Scheduler | ✓ running |

**结果：** ✓ 通过

---

## Level 2: 功能验证

### API Client 管理

| 操作 | 状态 |
|------|------|
| create | ✓ verify_client created |
| list | ✓ 1 client found |
| disable | ✓ suspended |
| enable | ✓ activated |

### 情报源管理

| 情报源 | 状态 | 采集数 | 通过数 |
|--------|------|--------|--------|
| 安全客 | ✓ | 20 | 18 |
| FreeBuf | ✓ | 15 | 15 |
| Hacker News | ✓ | 30 | 28 |

### 数据统计

| 指标 | 值 |
|------|-----|
| 总采集 | 65 items |
| 质量通过 | 61 items (93.8%) |
| 质量拒绝 | 4 items (6.2%) |
| 去重后 | 58 contents |

### API 查询

| 接口 | 状态 |
|------|------|
| Content API | ✓ 58 items returned |
| Cursor pagination | ✓ working |

**结果：** ✓ 通过

---

## 结论

验证通过，系统可用。
```

### 5.3 输出控制

```bash
# 默认：终端输出
make verify

# 保存到文件（Markdown 格式）
./scripts/verify.sh --output logs/verify-report.md

# 指定情报源清单
./scripts/verify.sh --sources custom-sources.yaml
```

---

## 6. 错误处理

### 6.1 验证失败处理

```
验证失败时：
├── 立即停止后续步骤
├── 输出详细错误信息
├── 显示相关日志命令提示
└── 返回非零退出码
```

### 6.2 错误输出示例

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Level 1: 系统就绪 ──────────────────────────────────────── ✗ 失败
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ Database: connected
  ✗ Redis: connection refused

错误详情：
  Error: Redis connection failed
  URL: redis://localhost:6379/0
  Reason: Connection refused

排查建议：
  1. 检查 Redis 服务是否启动: docker ps | grep redis
  2. 检查 Redis 配置: echo $REDIS_URL
  3. 查看 API 日志: docker logs cyberpulse-api

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
结论: 验证失败 ✗
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 7. 实现计划

### 7.1 开发任务

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 创建验证脚本 | `scripts/verify.sh` | P0 |
| 创建情报源清单 | `sources.yaml` | P0 |
| 更新 Makefile | `Makefile` | P0 |
| 编写使用文档 | `docs/verification-guide.md` | P1 |

### 7.2 测试要点

- [ ] Level 1 各项检查能正确识别失败
- [ ] Level 2 完整流程验证通过
- [ ] 验证报告正确输出
- [ ] Markdown 文件格式正确
- [ ] 错误信息清晰可定位

---

## 8. 后续演进

### 8.1 短期改进

- 集成 Issue #15 诊断命令增强功能
- 集成 Issue #16 日志功能增强功能

### 8.2 长期演进

- 定时健康检查（Cron）
- 监控系统集成（Prometheus）
- 告警通知（邮件/Slack）

---

## 附录

### A. 相关文档

- [技术规格说明书](./2026-03-18-cyber-pulse-design.md)
- [CLI 使用手册](../cli-usage-manual.md)
- Issue #15: 诊断命令增强
- Issue #16: 日志功能增强

### B. 修订记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-03-20 | 老罗 | 初始版本 |