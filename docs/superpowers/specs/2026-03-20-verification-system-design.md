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
API_URL="${API_URL:-http://localhost:8000}"
OUTPUT_FILE=""
KEEP_SOURCES=false

# 解析参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --output|-o)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            --sources|-s)
                SOURCES_FILE="$2"
                shift 2
                ;;
            --keep-sources)
                KEEP_SOURCES=true
                shift
                ;;
            --cleanup)
                cleanup_verify_data
                exit 0
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --output, -o FILE    输出报告到文件"
                echo "  --sources, -s FILE   指定情报源清单"
                echo "  --keep-sources       保留测试情报源"
                echo "  --cleanup            清理测试数据并退出"
                echo "  --help, -h           显示帮助"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# 日志函数
log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

log_debug() {
    if [ "$DEBUG" = "true" ]; then
        echo "[DEBUG] $1" >&2
    fi
}

# 验证 sources.yaml
validate_sources_file() {
    if [ ! -f "$SOURCES_FILE" ]; then
        log_error "情报源清单文件不存在: $SOURCES_FILE"
        exit 1
    fi

    # 验证 YAML 语法
    python3 -c "import yaml; yaml.safe_load(open('$SOURCES_FILE'))" || {
        log_error "YAML 语法错误: $SOURCES_FILE"
        exit 1
    }

    # 验证必需字段
    python3 << 'EOF'
import yaml
import sys

with open("$SOURCES_FILE") as f:
    data = yaml.safe_load(f)

for i, source in enumerate(data.get("sources", [])):
    name = source.get("name")
    conn_type = source.get("connector_type")
    config = source.get("config", {})

    if not name:
        print(f"Error: Source #{i+1} missing 'name'", file=sys.stderr)
        sys.exit(1)
    if not conn_type:
        print(f"Error: Source '{name}' missing 'connector_type'", file=sys.stderr)
        sys.exit(1)
    if not config:
        print(f"Error: Source '{name}' missing 'config'", file=sys.stderr)
        sys.exit(1)
EOF
}

# Level 1: 系统就绪
verify_level1() { ... }

# Level 2: 功能验证
verify_level2() { ... }

# 主流程
main() {
    parse_args "$@"
    validate_sources_file

    # 设置锁机制
    LOCK_FILE="/tmp/cyberpulse_verify.lock"
    exec 200>$LOCK_FILE
    flock -n 200 || {
        log_error "另一个验证任务正在运行"
        exit 1
    }

    verify_level1
    verify_level2
    cleanup_verify_data
    print_report

    # 释放锁
    flock -u 200
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
    # 注意：CLI 使用 Rich 格式化输出，需剥离 ANSI 代码
    RESULT=$(docker exec $CONTAINER_API cyber-pulse client create verify_client 2>&1 | \
        sed 's/\x1b\[[0-9;]*m//g' | tr -d '[]')

    # 提取 API Key（剥离 Rich 格式后的格式 "API Key: cp_live_xxx"）
    API_KEY=$(echo "$RESULT" | grep -oP 'API Key:\s*\Kcp_live_[a-f0-9]{32}' || {
        log_error "无法提取 API Key，CLI 输出格式可能已变更"
        log_debug "CLI 输出: $RESULT"
        exit 1
    })

    # 提取 Client ID（格式: cli_xxxxxxxxxxxxxxxx，16 位 hex）
    CLIENT_ID=$(echo "$RESULT" | grep -oP 'Created client:\s*\Kcli_[a-f0-9]{16}' || {
        log_error "无法提取 Client ID，CLI 输出格式可能已变更"
        log_debug "CLI 输出: $RESULT"
        exit 1
    })

    # 列出 Client（使用 grep 匹配表格输出）
    docker exec $CONTAINER_API cyber-pulse client list | grep -q "verify_client"

    # 暂停 Client
    docker exec $CONTAINER_API cyber-pulse client disable $CLIENT_ID

    # 启用 Client
    docker exec $CONTAINER_API cyber-pulse client enable $CLIENT_ID

    # 保存 API Key 和 Client ID 供后续使用
    echo $API_KEY > /tmp/cyberpulse_verify.key
    echo $CLIENT_ID > /tmp/cyberpulse_verify_client_id
}
```

**关键技术说明：**

| 问题 | 解决方案 |
|------|----------|
| CLI 输出包含 Rich 格式化代码 | 使用 `sed 's/\x1b\[[0-9;]*m//g'` 剥离 ANSI 转义码 |
| Rich 标签如 `[green]` | 使用 `tr -d '[]'` 移除方括号 |
| Client ID 格式 | `cli_[a-f0-9]{16}`（16 位 hex，非 8 位） |
| API Key 格式 | `cp_live_[a-f0-9]{32}`（32 位 hex） |

**注意：** 若 CLI 输出格式变更，脚本需同步更新。长期方案是在 CLI 命令中添加 `--json` 输出选项。

#### 4.1.5 情报源验证

```bash
verify_source_management() {
    echo "[情报源管理]"

    # 使用 Python 解析 YAML 并调用 CLI
    # 通过环境变量传递配置
    export SOURCES_FILE
    python3 << 'EOF'
import yaml
import subprocess
import sys
import os

sources_file = os.environ.get('SOURCES_FILE', 'sources.yaml')
with open(sources_file) as f:
    data = yaml.safe_load(f)

source_ids = []
for source in data.get("sources", []):
    name = source["name"]
    conn_type = source["connector_type"]
    config = source.get("config", {})
    tier = source.get("tier", "T2")

    # 获取 URL
    url = config.get("feed_url") or config.get("url", "")

    # 构建 CLI 命令
    cmd = ["docker", "exec", "cyberpulse-api", "cyber-pulse", "source", "add",
           name, conn_type, url, "--tier", tier, "--test"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"✗ {name}: Failed - {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ {name}: added, connection test passed")

    # 提取 source_id 供后续使用
    # 输出格式: "ID: src_xxxxxxxx"
    for line in result.stdout.split("\n"):
        if "ID:" in line:
            source_id = line.split("ID:")[1].strip().split()[0]
            source_ids.append(f"{name}:{source_id}")

# 保存 source_ids 供数据采集使用
with open("/tmp/cyberpulse_sources.txt", "w") as f:
    f.write("\n".join(source_ids))
EOF
}
```

#### 4.1.5.1 数据采集验证

**注意：** `job run` 是异步任务，不返回采集统计。验证脚本需采用轮询策略。

```bash
verify_data_collection() {
    echo "[数据采集]"

    # 读取情报源 ID
    if [ ! -f /tmp/cyberpulse_sources.txt ]; then
        log_error "未找到情报源 ID 文件"
        exit 1
    fi

    # 记录采集前的 content 数量（使用 content stats 命令）
    BEFORE_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

    total_sources=0
    while IFS=: read -r name source_id; do
        # 执行采集任务（异步）
        docker exec $CONTAINER_API cyber-pulse job run "$source_id" 2>&1 || {
            log_error "采集任务启动失败: $name"
            exit 1
        }
        echo "  ✓ $name: 采集任务已启动"
        total_sources=$((total_sources + 1))
    done < /tmp/cyberpulse_sources.txt

    # 轮询等待采集完成（最长等待 5 分钟）
    echo "等待采集完成..."
    MAX_WAIT=300
    WAIT_INTERVAL=10
    elapsed=0

    while [ $elapsed -lt $MAX_WAIT ]; do
        # 检查 content 数量是否增加
        AFTER_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

        # 如果 content 数量增加，认为采集已完成
        if [ "$AFTER_COUNT" -gt "$BEFORE_COUNT" ]; then
            break
        fi

        sleep $WAIT_INTERVAL
        elapsed=$((elapsed + WAIT_INTERVAL))
        echo "  已等待 ${elapsed}s..."
    done

    # 获取最终统计
    FINAL_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

    NEW_CONTENTS=$((FINAL_COUNT - BEFORE_COUNT))

    echo "  总新增内容: $NEW_CONTENTS contents"

    # 获取 source 统计（source stats 无 JSON 选项，使用文本解析）
    echo "  [各情报源统计]"
    while IFS=: read -r name source_id; do
        # 从 source stats 输出中提取 Items 和 Contents
        STATS=$(docker exec $CONTAINER_API cyber-pulse source stats "$source_id" 2>/dev/null | \
            sed 's/\x1b\[[0-9;]*m//g' | grep -E "Items|Contents" | tr '\n' ',' | sed 's/,$//' || echo "")
        echo "    $name: $STATS"
    done < /tmp/cyberpulse_sources.txt

    # 保存供报告使用
    echo "new_contents=$NEW_CONTENTS" >> /tmp/cyberpulse_verify_stats.txt
}

cleanup_verify_client() {
    # 别名，调用 cleanup_verify_data 的 Client 清理部分
    if [ -f /tmp/cyberpulse_verify_client_id ]; then
        CLIENT_ID=$(cat /tmp/cyberpulse_verify_client_id)
        docker exec $CONTAINER_API cyber-pulse client delete $CLIENT_ID --force 2>/dev/null || true
        rm -f /tmp/cyberpulse_verify_client_id /tmp/cyberpulse_verify.key
    fi
}

print_report() {
    # 读取统计数据
    if [ -f /tmp/cyberpulse_verify_stats.txt ]; then
        source /tmp/cyberpulse_verify_stats.txt
    fi

    if [ -n "$OUTPUT_FILE" ]; then
        # Markdown 格式输出
        cat > "$OUTPUT_FILE" << EOF
# cyber-pulse 验证报告

**时间：** $(date '+%Y-%m-%d %H:%M:%S')
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

### 数据统计

| 指标 | 值 |
|------|-----|
| 新增内容 | ${new_contents:-0} contents |

**结果：** ✓ 通过

---

## 结论

验证通过，系统可用。
EOF
        echo "报告已保存到: $OUTPUT_FILE"
    else
        # 终端输出
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "结论: 验证通过 ✓"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi

    # 清理临时文件
    rm -f /tmp/cyberpulse_verify_stats.txt
}
```

#### 4.1.5.2 API 查询验证

```bash
verify_api_query() {
    echo "[API 查询]"

    # 读取 API Key
    if [ ! -f /tmp/cyberpulse_verify.key ]; then
        log_error "未找到 API Key"
        exit 1
    fi
    API_KEY=$(cat /tmp/cyberpulse_verify.key)

    # 测试 Content API
    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/content?limit=10")

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | head -n -1)

    if [ "$HTTP_CODE" != "200" ]; then
        log_error "Content API 返回 HTTP $HTTP_CODE"
        exit 1
    fi

    # 解析响应
    COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', 0))")
    echo "  ✓ Content API: $COUNT items returned"

    # 测试分页
    CURSOR=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('next_cursor', ''))")
    if [ -n "$CURSOR" ]; then
        echo "  ✓ Cursor pagination: working"
    else
        echo "  ✓ Cursor pagination: no more pages"
    fi
}
```

#### 4.1.6 数据清理策略

验证完成后需清理测试数据，避免污染生产环境：

```bash
cleanup_verify_data() {
    echo "=== 清理验证数据 ==="

    # 1. 删除测试 API Client
    cleanup_verify_client

    # 2. 删除验证用情报源（可选，通过 --keep-sources 参数控制）
    if [ "$KEEP_SOURCES" != "true" ]; then
        # 从保存的情报源 ID 文件读取
        if [ -f /tmp/cyberpulse_sources.txt ]; then
            while IFS=: read -r name source_id; do
                if [ -n "$source_id" ]; then
                    docker exec $CONTAINER_API cyber-pulse source remove "$source_id" --force 2>/dev/null || true
                    echo "  已删除情报源: $name"
                fi
            done < /tmp/cyberpulse_sources.txt
            rm -f /tmp/cyberpulse_sources.txt
        fi
    fi

    echo "清理完成"
}
```

**清理时机：**
- 正常完成验证后：自动清理
- 验证失败时：保留数据以便排查，提供 `--cleanup` 参数手动清理
- 用户可指定 `--keep-sources` 保留情报源用于后续测试

#### 4.1.7 并发控制

验证脚本设计为单实例运行，不处理并发场景：

**设计决策：**
- 验证操作属于运维管理任务，通常由管理员手动触发
- 生产环境中不建议并行执行多个验证任务
- 脚本通过 `flock` 实现简单互斥锁

```bash
# 脚本开头添加锁机制
LOCK_FILE="/tmp/cyberpulse_verify.lock"
exec 200>$LOCK_FILE
flock -n 200 || {
    echo "错误: 另一个验证任务正在运行"
    exit 1
}
# 脚本结束时自动释放锁
```

**如果需要并行验证：**
- 使用不同的 API Client 名称（如 `verify_client_$(date +%s)`）
- 使用不同的情报源集合
- 需自行管理数据隔离和清理

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

#### 4.2.3 config 字段与 CLI 映射

验证脚本需将 `sources.yaml` 中的配置转换为 CLI 命令：

```yaml
# RSS 源
config:
  feed_url: https://example.com/feed.xml
# CLI: cyber-pulse source add "名称" rss "$feed_url" --tier T2 --test

# API 源（api_key 需单独处理）
config:
  url: https://api.example.com/data
  api_key: xxx
# CLI: cyber-pulse source add "名称" api "$url" --tier T2 --test
# 注意: api_key 不通过 CLI 传递，需手动配置或扩展 CLI

# Web 源
config:
  url: https://example-blog.com
# CLI: cyber-pulse source add "名称" web "$url" --tier T2 --test

# Media 源（api_key 需单独处理）
config:
  url: https://youtube.com/channel/xxx
  api_key: xxx
# CLI: cyber-pulse source add "名称" media "$url" --tier T2 --test
# 注意: api_key 不通过 CLI 传递，需手动配置或扩展 CLI
```

**当前 CLI 限制：**

| connector_type | CLI 参数 | api_key 处理 |
|----------------|----------|--------------|
| `rss` | `name rss $feed_url` | 不适用 |
| `api` | `name api $url` | 需扩展 CLI 或手动配置 |
| `web` | `name web $url` | 不适用 |
| `media` | `name media $url` | 需扩展 CLI 或手动配置 |

**建议：** 为支持 API/Media 源的 api_key 配置，建议：
1. 扩展 CLI `source add` 命令添加 `--api-key` 参数
2. 或在验证脚本中使用数据库直接插入配置

**验证脚本实现示例：**

```bash
verify_source_management() {
    # 使用 Python 解析 YAML 并调用 CLI
    export SOURCES_FILE
    python3 << 'EOF'
import yaml
import subprocess
import os

sources_file = os.environ.get('SOURCES_FILE', 'sources.yaml')
with open(sources_file) as f:
    data = yaml.safe_load(f)

for source in data.get("sources", []):
    name = source["name"]
    conn_type = source["connector_type"]
    config = source.get("config", {})
    tier = source.get("tier", "T2")

    # 获取 URL（RSS 使用 feed_url，其他使用 url）
    url = config.get("feed_url") or config.get("url", "")

    # 构建 CLI 命令
    cmd = ["docker", "exec", "cyberpulse-api", "cyber-pulse", "source", "add",
           name, conn_type, url, "--tier", tier, "--test"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to add source {name}: {result.stderr}")
        exit(1)
    print(f"Added source: {name}")
EOF
}
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

# 保留测试情报源（用于后续手动测试）
./scripts/verify.sh --keep-sources

# 仅清理测试数据
./scripts/verify.sh --cleanup

# 显示帮助
./scripts/verify.sh --help
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

### 7.2 测试计划

#### 7.2.1 单元测试

| 测试项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| YAML 解析 | 提供有效/无效 sources.yaml | 有效文件正确解析，无效文件报错 |
| API Key 提取 | 模拟 CLI 输出字符串 | 正确提取 `cp_live_xxx` 格式 |
| Client ID 提取 | 模拟 CLI 输出字符串 | 正确提取 `cli_xxx` 格式 |
| 参数解析 | 传入各种参数组合 | 正确解析 `--output`, `--sources` 等 |

#### 7.2.2 集成测试

**Level 1 测试场景：**

| 场景 | 模拟方法 | 预期结果 |
|------|----------|----------|
| 全部正常 | 正常 Docker 环境 | Level 1 通过 |
| 数据库断开 | 停止 db 容器 | 输出错误，退出码非零 |
| Redis 断开 | 停止 redis 容器 | 输出错误，退出码非零 |
| Worker 停止 | 停止 worker 容器 | 输出错误，退出码非零 |
| Scheduler 停止 | 停止 scheduler 容器 | 输出错误，退出码非零 |

**Level 2 测试场景：**

| 场景 | 模拟方法 | 预期结果 |
|------|----------|----------|
| Client 创建失败 | 数据库只读模式 | 输出错误，停止验证 |
| 情报源连接失败 | 使用无效 URL | 连接测试失败，输出详细错误 |
| 采集无数据 | 使用空 RSS 源 | 正常完成，报告 0 items |
| API 认证失败 | 使用无效 API Key | 输出 401 错误 |

#### 7.2.3 端到端测试

**测试步骤：**

1. **准备环境**
   ```bash
   docker-compose up -d
   # 等待服务就绪
   sleep 10
   ```

2. **执行验证**
   ```bash
   make verify
   ```

3. **验证输出**
   - 终端输出包含 "Level 1: ✓ 通过"
   - 终端输出包含 "Level 2: ✓ 通过"
   - 终端输出包含 "结论: 验证通过 ✓"

4. **验证清理**
   ```bash
   # 确认测试 Client 已删除
   docker exec cyberpulse-api cyber-pulse client list | grep -v verify_client
   ```

5. **报告生成测试**
   ```bash
   ./scripts/verify.sh --output logs/test-report.md
   # 确认文件生成且格式正确
   cat logs/test-report.md | grep "验证通过"
   ```

#### 7.2.4 回归测试清单

每次版本迭代时执行：

- [ ] Level 1 各项检查能正确识别失败
- [ ] Level 2 完整流程验证通过
- [ ] 验证报告终端输出格式正确
- [ ] 验证报告 Markdown 文件格式正确
- [ ] 错误信息清晰可定位
- [ ] 测试数据清理完整
- [ ] `--output` 参数正常工作
- [ ] `--sources` 参数正常工作
- [ ] `--keep-sources` 参数正常工作
- [ ] 并发锁机制正常工作

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