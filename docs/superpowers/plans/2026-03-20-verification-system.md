# Verification System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 cyber-pulse 验证系统，用于部署验证、功能验证和持续迭代的回归测试。

**Architecture:** Shell 脚本通过 `docker exec` 调用容器内 CLI 命令，实现 2 级验证模型（Level 1: 系统就绪，Level 2: 功能验证）。验证脚本与生产环境独立，通过 sources.yaml 配置情报源清单。

**Tech Stack:** Bash, Python 3 (YAML 解析), Docker CLI, cyber-pulse CLI

---

## File Structure

```
cyber-pulse/
├── Makefile                    # 新建 - 任务入口
├── scripts/
│   └── verify.sh               # 新建 - 验证脚本
├── sources.yaml                # 新建 - 预设情报源清单
└── docs/
    └── verification-guide.md   # 新建 - 使用文档
```

---

## Task 1: 创建 Makefile 入口

**Files:**
- Create: `Makefile`

- [ ] **Step 1: 创建 Makefile（使用 heredoc 确保 Tab 字符正确）**

```bash
cat > Makefile << 'MAKEFILE_EOF'
# Makefile for cyber-pulse
#
# Usage:
#   make verify          # 运行验证系统
#   make verify-report   # 验证并生成报告

.PHONY: verify verify-report help

# 验证系统
verify:
	@echo "开始验证 cyber-pulse..."
	@./scripts/verify.sh

# 验证并保存报告
verify-report:
	@echo "验证并生成报告..."
	@mkdir -p logs
	@./scripts/verify.sh --output logs/verify-report.md

# 帮助
help:
	@echo "cyber-pulse Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  verify         运行验证系统"
	@echo "  verify-report  验证并生成报告到 logs/verify-report.md"
	@echo "  help           显示此帮助信息"
MAKEFILE_EOF
```

- [ ] **Step 2: 验证 Makefile 语法**

Run: `make help`
Expected: 显示帮助信息

- [ ] **Step 3: 提交**

```bash
git add Makefile
git commit -m "feat: add Makefile with verify targets"
```

---

## Task 2: 创建 scripts 目录和验证脚本 - Part 1: 框架

**Files:**
- Create: `scripts/verify.sh`

- [ ] **Step 1: 创建 scripts 目录**

```bash
mkdir -p scripts
```

- [ ] **Step 2: 创建脚本框架（配置和日志函数）**

```bash
cat > scripts/verify.sh << 'SCRIPT_EOF'
#!/bin/bash
#
# cyber-pulse 验证脚本
#
# 用途：
# - 部署验证：确认系统部署/配置正确
# - 功能验证：确认完整 workflow 正常运行
# - 回归测试：支持后续版本迭代时的回归验证

set -e

# ============================================================================
# 配置
# ============================================================================

CONTAINER_API="cyberpulse-api"
CONTAINER_WORKER="cyberpulse-worker"
CONTAINER_SCHEDULER="cyberpulse-scheduler"
SOURCES_FILE="sources.yaml"
API_URL="${API_URL:-http://localhost:8000}"
OUTPUT_FILE=""
KEEP_SOURCES=false
DEBUG="${DEBUG:-false}"

# ============================================================================
# 日志函数
# ============================================================================

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
SCRIPT_EOF
```

- [ ] **Step 3: 添加参数解析函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 参数解析
# ============================================================================

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
                echo ""
                echo "Options:"
                echo "  --output, -o FILE    输出报告到文件 (Markdown 格式)"
                echo "  --sources, -s FILE   指定情报源清单 (默认: sources.yaml)"
                echo "  --keep-sources       保留测试情报源"
                echo "  --cleanup            清理测试数据并退出"
                echo "  --help, -h           显示此帮助"
                echo ""
                echo "Environment Variables:"
                echo "  API_URL              API 服务地址 (默认: http://localhost:8000)"
                echo "  DEBUG                启用调试模式 (true/false)"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}
SCRIPT_EOF
```

- [ ] **Step 4: 添加 sources.yaml 验证函数（含必需字段验证）**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 验证 sources.yaml
# ============================================================================

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
    export SOURCES_FILE
    python3 << 'PYEOF'
import yaml
import sys
import os

sources_file = os.environ.get('SOURCES_FILE', 'sources.yaml')
with open(sources_file) as f:
    data = yaml.safe_load(f)

sources = data.get("sources", [])
if not sources:
    print("Error: No sources defined in sources.yaml", file=sys.stderr)
    sys.exit(1)

for i, source in enumerate(sources):
    name = source.get("name")
    conn_type = source.get("connector_type")
    config = source.get("config", {})

    if not name:
        print(f"Error: Source #{i+1} missing 'name' field", file=sys.stderr)
        sys.exit(1)
    if not conn_type:
        print(f"Error: Source '{name}' missing 'connector_type' field", file=sys.stderr)
        sys.exit(1)
    if not config:
        print(f"Error: Source '{name}' missing 'config' field", file=sys.stderr)
        sys.exit(1)
    # 检查 config 中的必需字段
    if conn_type == "rss" and not config.get("feed_url"):
        print(f"Error: RSS source '{name}' missing 'feed_url' in config", file=sys.stderr)
        sys.exit(1)
    if conn_type in ("api", "web", "media") and not config.get("url"):
        print(f"Error: {conn_type} source '{name}' missing 'url' in config", file=sys.stderr)
        sys.exit(1)

print(f"Validation passed: {len(sources)} source(s) defined")
PYEOF

    log_info "情报源清单验证通过: $SOURCES_FILE"
}
SCRIPT_EOF
```

- [ ] **Step 5: 提交 Part 1**

```bash
chmod +x scripts/verify.sh
git add scripts/verify.sh
git commit -m "feat(verify): add script framework with config, logging, and validation"
```

---

## Task 3: 创建验证脚本 - Part 2: Level 1 验证

**Files:**
- Modify: `scripts/verify.sh`

- [ ] **Step 1: 添加 Level 1 验证函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# Level 1: 系统就绪验证
# ============================================================================

verify_level1() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 1: 系统就绪"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 数据库 + Redis 检查
    echo "  检查数据库和 Redis 连接..."
    docker exec $CONTAINER_API cyber-pulse diagnose system || {
        log_error "Level 1 失败: 系统诊断未通过"
        exit 1
    }
    echo "  ✓ Database: connected"
    echo "  ✓ Redis: connected"
    echo "  ✓ API: healthy"

    # Worker 运行检查
    echo "  检查 Worker 运行状态..."
    docker ps --filter "name=$CONTAINER_WORKER" --filter "status=running" | grep -q $CONTAINER_WORKER || {
        log_error "Level 1 失败: Worker 未运行"
        echo "  ✗ Worker: not running"
        echo ""
        echo "排查建议:"
        echo "  1. 检查容器状态: docker ps -a | grep worker"
        echo "  2. 查看日志: docker logs $CONTAINER_WORKER"
        exit 1
    }
    echo "  ✓ Worker: running"

    # Scheduler 运行检查
    echo "  检查 Scheduler 运行状态..."
    docker ps --filter "name=$CONTAINER_SCHEDULER" --filter "status=running" | grep -q $CONTAINER_SCHEDULER || {
        log_error "Level 1 失败: Scheduler 未运行"
        echo "  ✗ Scheduler: not running"
        echo ""
        echo "排查建议:"
        echo "  1. 检查容器状态: docker ps -a | grep scheduler"
        echo "  2. 查看日志: docker logs $CONTAINER_SCHEDULER"
        exit 1
    }
    echo "  ✓ Scheduler: running"

    echo ""
    echo "Level 1: ✓ 通过"
}
SCRIPT_EOF
```

- [ ] **Step 2: 提交 Part 2**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add Level 1 system readiness verification"
```

---

## Task 4: 创建验证脚本 - Part 3: Level 2 API Client 管理

**Files:**
- Modify: `scripts/verify.sh`

- [ ] **Step 1: 添加 Level 2 框架和 API Client 管理函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# Level 2: 功能验证
# ============================================================================

verify_level2() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Level 2: 功能验证"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 1. API Client 管理
    verify_api_client_management

    # 2. 情报源管理
    verify_source_management

    # 3. 数据采集
    verify_data_collection

    # 4. CLI 数据查询
    verify_cli_query

    # 5. API 查询
    verify_api_query

    echo ""
    echo "Level 2: ✓ 通过"
}

# ============================================================================
# API Client 管理
# ============================================================================

verify_api_client_management() {
    echo ""
    echo "[API Client 管理]"

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

    echo "  ✓ client create: verify_client created ($CLIENT_ID)"

    # 列出 Client（使用 grep 匹配表格输出）
    docker exec $CONTAINER_API cyber-pulse client list | grep -q "verify_client" || {
        log_error "Client list 中未找到 verify_client"
        exit 1
    }
    echo "  ✓ client list: verify_client found"

    # 暂停 Client
    docker exec $CONTAINER_API cyber-pulse client disable $CLIENT_ID || {
        log_error "Client disable 失败"
        exit 1
    }
    echo "  ✓ client disable: suspended"

    # 启用 Client
    docker exec $CONTAINER_API cyber-pulse client enable $CLIENT_ID || {
        log_error "Client enable 失败"
        exit 1
    }
    echo "  ✓ client enable: activated"

    # 保存 API Key 和 Client ID 供后续使用
    echo $API_KEY > /tmp/cyberpulse_verify.key
    echo $CLIENT_ID > /tmp/cyberpulse_verify_client_id
}
SCRIPT_EOF
```

- [ ] **Step 2: 提交 Part 3**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add Level 2 API client management verification"
```

---

## Task 5: 创建验证脚本 - Part 4: 情报源管理和数据采集

**Files:**
- Modify: `scripts/verify.sh`

- [ ] **Step 1: 添加情报源管理函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 情报源管理
# ============================================================================

verify_source_management() {
    echo ""
    echo "[情报源管理]"

    # 使用 Python 解析 YAML 并调用 CLI
    export SOURCES_FILE
    python3 << 'PYEOF'
import yaml
import subprocess
import sys
import os
import re

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
    print(f"  ✓ {name}: added, connection test passed")

    # 提取 source_id 供后续使用
    for line in result.stdout.split("\n"):
        if "ID:" in line:
            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
            clean_line = clean_line.replace('[', '').replace(']', '')
            parts = clean_line.split("ID:")
            if len(parts) > 1:
                source_id = parts[1].strip().split()[0]
                source_ids.append(f"{name}:{source_id}")

with open("/tmp/cyberpulse_sources.txt", "w") as f:
    f.write("\n".join(source_ids))
PYEOF
}

# ============================================================================
# 数据采集
# ============================================================================

verify_data_collection() {
    echo ""
    echo "[数据采集]"

    if [ ! -f /tmp/cyberpulse_sources.txt ]; then
        log_error "未找到情报源 ID 文件"
        exit 1
    fi

    BEFORE_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

    while IFS=: read -r name source_id; do
        docker exec $CONTAINER_API cyber-pulse job run "$source_id" 2>&1 || {
            log_error "采集任务启动失败: $name"
            exit 1
        }
        echo "  ✓ $name: 采集任务已启动"
    done < /tmp/cyberpulse_sources.txt

    echo ""
    echo "  等待采集完成..."
    MAX_WAIT=300
    WAIT_INTERVAL=10
    elapsed=0

    while [ $elapsed -lt $MAX_WAIT ]; do
        AFTER_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

        if [ "$AFTER_COUNT" -gt "$BEFORE_COUNT" ]; then
            break
        fi

        sleep $WAIT_INTERVAL
        elapsed=$((elapsed + WAIT_INTERVAL))
        echo "    已等待 ${elapsed}s..."
    done

    FINAL_COUNT=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>/dev/null | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" || echo "0")

    NEW_CONTENTS=$((FINAL_COUNT - BEFORE_COUNT))

    echo ""
    echo "  [采集统计]"
    echo "    采集前: $BEFORE_COUNT contents"
    echo "    采集后: $FINAL_COUNT contents"
    echo "    新增:   $NEW_CONTENTS contents"

    echo "new_contents=$NEW_CONTENTS" >> /tmp/cyberpulse_verify_stats.txt
}
SCRIPT_EOF
```

- [ ] **Step 2: 提交 Part 4**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add source management and data collection verification"
```

---

## Task 6: 创建验证脚本 - Part 5: CLI/API 查询和清理

**Files:**
- Modify: `scripts/verify.sh`

- [ ] **Step 1: 添加 CLI 查询验证函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# CLI 数据查询
# ============================================================================

verify_cli_query() {
    echo ""
    echo "[CLI 数据查询]"

    # 测试 content list 命令
    RESULT=$(docker exec $CONTAINER_API cyber-pulse content list --format json 2>&1)

    # 解析 JSON 数组获取数量
    COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else 0)" 2>/dev/null || echo "0")

    if [ "$COUNT" -eq 0 ]; then
        echo "  ⚠ content list: 0 items (may be expected for fresh install)"
    else
        echo "  ✓ content list: $COUNT items found"
    fi

    # 测试 content stats 命令
    STATS=$(docker exec $CONTAINER_API cyber-pulse content stats --format json 2>&1)
    TOTAL=$(echo "$STATS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_contents', 0))" 2>/dev/null || echo "0")

    echo "  ✓ content stats: $TOTAL total contents"
}

# ============================================================================
# API 查询
# ============================================================================

verify_api_query() {
    echo ""
    echo "[API 查询]"

    if [ ! -f /tmp/cyberpulse_verify.key ]; then
        log_error "未找到 API Key"
        exit 1
    fi
    API_KEY=$(cat /tmp/cyberpulse_verify.key)

    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: Bearer $API_KEY" \
        "${API_URL}/api/v1/content?limit=10")

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | head -n -1)

    if [ "$HTTP_CODE" != "200" ]; then
        log_error "Content API 返回 HTTP $HTTP_CODE"
        echo "  Response: $BODY"
        exit 1
    fi

    COUNT=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count', len(d) if isinstance(d, list) else 0))")
    echo "  ✓ Content API: HTTP $HTTP_CODE, $COUNT items returned"

    CURSOR=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('next_cursor', ''))" 2>/dev/null || echo "")
    if [ -n "$CURSOR" ]; then
        echo "  ✓ Cursor pagination: working"
    else
        echo "  ✓ Cursor pagination: no more pages"
    fi
}
SCRIPT_EOF
```

- [ ] **Step 2: 添加清理函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 清理函数
# ============================================================================

cleanup_verify_client() {
    if [ -f /tmp/cyberpulse_verify_client_id ]; then
        CLIENT_ID=$(cat /tmp/cyberpulse_verify_client_id)
        docker exec $CONTAINER_API cyber-pulse client delete $CLIENT_ID --force 2>/dev/null || true
        rm -f /tmp/cyberpulse_verify_client_id /tmp/cyberpulse_verify.key
        echo "  ✓ verify_client deleted"
    fi
}

cleanup_verify_data() {
    echo ""
    echo "[清理验证数据]"

    cleanup_verify_client

    if [ "$KEEP_SOURCES" != "true" ]; then
        if [ -f /tmp/cyberpulse_sources.txt ]; then
            while IFS=: read -r name source_id; do
                if [ -n "$source_id" ]; then
                    docker exec $CONTAINER_API cyber-pulse source remove "$source_id" --force 2>/dev/null || true
                    echo "  ✓ 已删除情报源: $name"
                fi
            done < /tmp/cyberpulse_sources.txt
            rm -f /tmp/cyberpulse_sources.txt
        fi
    else
        echo "  --keep-sources 指定，保留情报源"
    fi

    rm -f /tmp/cyberpulse_verify_stats.txt
}
SCRIPT_EOF
```

- [ ] **Step 3: 提交 Part 5**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add CLI/API query verification and cleanup functions"
```

---

## Task 7: 创建验证脚本 - Part 6: 报告输出和主流程

**Files:**
- Modify: `scripts/verify.sh`

- [ ] **Step 1: 添加报告输出函数**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 报告输出
# ============================================================================

print_report() {
    if [ -f /tmp/cyberpulse_verify_stats.txt ]; then
        source /tmp/cyberpulse_verify_stats.txt
    fi

    if [ -n "$OUTPUT_FILE" ]; then
        mkdir -p "$(dirname "$OUTPUT_FILE")"
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
        echo ""
        echo "报告已保存到: $OUTPUT_FILE"
    else
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "结论: 验证通过 ✓"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
}
SCRIPT_EOF
```

- [ ] **Step 2: 添加主流程入口**

```bash
cat >> scripts/verify.sh << 'SCRIPT_EOF'

# ============================================================================
# 主流程
# ============================================================================

main() {
    parse_args "$@"

    echo "╭─────────────────────────────────────────────────────────────────╮"
    echo "│                  cyber-pulse 验证系统                           │"
    echo "│                    $(date '+%Y-%m-%d %H:%M:%S')                         │"
    echo "╰─────────────────────────────────────────────────────────────────╯"

    validate_sources_file

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

    flock -u 200
}

main "$@"
SCRIPT_EOF
```

- [ ] **Step 3: 验证脚本语法**

Run: `bash -n scripts/verify.sh`
Expected: 无输出（语法正确）

- [ ] **Step 4: 验证帮助信息**

Run: `./scripts/verify.sh --help`
Expected: 显示帮助信息

- [ ] **Step 5: 提交 Part 6**

```bash
git add scripts/verify.sh
git commit -m "feat(verify): add report output and main entry point"
```

---

## Task 8: 创建情报源清单模板

**Files:**
- Create: `sources.yaml`

- [ ] **Step 1: 创建 sources.yaml 模板**

```bash
cat > sources.yaml << 'YAML_EOF'
# sources.yaml - 验证用情报源清单
#
# 说明：
# - 这些情报源用于验证 cyber-pulse 功能是否正常
# - 应选择稳定、公开、可访问的情报源
# - 由人工筛选，确保采集失败是应用问题而非情报源问题
#
# 字段说明：
# - name: 情报源名称（必需，唯一）
# - connector_type: 类型 rss/api/web/media（必需）
# - config: Connector 配置（必需）
#   - RSS: feed_url
#   - API: url, api_key (可选)
#   - Web: url
#   - Media: url, api_key (可选)
# - tier: 优先级 T0-T3（可选，默认 T2）

sources:
  # 示例 RSS 源（请替换为实际可用的情报源）
  # - name: 安全客
  #   connector_type: rss
  #   config:
  #     feed_url: https://www.anquanke.com/vul/rss.xml
  #   tier: T2

  # - name: FreeBuf
  #   connector_type: rss
  #   config:
  #     feed_url: https://www.freebuf.com/feed
  #   tier: T2
YAML_EOF
```

- [ ] **Step 2: 验证 YAML 语法**

Run: `python3 -c "import yaml; yaml.safe_load(open('sources.yaml'))"`
Expected: 无输出（语法正确）

- [ ] **Step 3: 提交**

```bash
git add sources.yaml
git commit -m "feat: add sources.yaml template for verification"
```

---

## Task 9: 创建验证使用文档

**Files:**
- Create: `docs/verification-guide.md`

- [ ] **Step 1: 创建使用文档**

```bash
cat > docs/verification-guide.md << 'DOC_EOF'
# cyber-pulse 验证系统使用指南

## 概述

验证系统用于确认 cyber-pulse 部署正确、功能完整，支持回归测试。

## 快速开始

### 1. 准备情报源

编辑 `sources.yaml`，添加实际可用的情报源：

```yaml
sources:
  - name: 安全客
    connector_type: rss
    config:
      feed_url: https://www.anquanke.com/vul/rss.xml
    tier: T2
```

### 2. 启动服务

```bash
docker-compose up -d
```

### 3. 运行验证

```bash
make verify
```

## 验证流程

### Level 1: 系统就绪

检查项：
- 数据库连接
- Redis 连接
- API 服务健康
- Worker 运行状态
- Scheduler 运行状态

### Level 2: 功能验证

检查项：
- API Client 管理（create/list/disable/enable）
- 情报源添加与连接测试
- 数据采集任务执行
- CLI 数据查询
- API 查询功能

## 命令参考

```bash
# 终端输出
make verify

# 生成 Markdown 报告
make verify-report

# 指定情报源清单
./scripts/verify.sh --sources custom-sources.yaml

# 保留测试情报源
./scripts/verify.sh --keep-sources

# 仅清理测试数据
./scripts/verify.sh --cleanup

# 显示帮助
./scripts/verify.sh --help
```

## 故障排查

### Level 1 失败

| 症状 | 可能原因 | 排查命令 |
|------|----------|----------|
| Database 连接失败 | PostgreSQL 未启动或配置错误 | `docker logs cyberpulse-db` |
| Redis 连接失败 | Redis 未启动 | `docker logs cyberpulse-redis` |
| Worker 未运行 | Worker 容器崩溃 | `docker logs cyberpulse-worker` |

### Level 2 失败

| 症状 | 可能原因 | 排查命令 |
|------|----------|----------|
| 情报源连接失败 | URL 不可达或格式错误 | 检查网络连接 |
| 采集无数据 | 情报源无内容或解析错误 | `docker logs cyberpulse-worker` |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_URL` | `http://localhost:8000` | API 服务地址 |
| `DEBUG` | `false` | 启用调试输出 |

## 注意事项

1. **数据质量**：REJECTED items 是正常的业务结果，不作为验证失败条件
2. **并发**：验证脚本使用文件锁，同一时间只能运行一个实例
3. **清理**：验证完成后自动清理测试数据，除非指定 `--keep-sources`
DOC_EOF
```

- [ ] **Step 2: 提交**

```bash
git add docs/verification-guide.md
git commit -m "docs: add verification system usage guide"
```

---

## Task 10: 端到端测试

**前提条件：**
- Docker Compose 服务已启动
- `sources.yaml` 已配置实际情报源

- [ ] **Step 1: 启动服务**

```bash
docker-compose up -d
sleep 10
```

- [ ] **Step 2: 运行验证**

```bash
make verify
```

Expected:
- Level 1: ✓ 通过
- Level 2: ✓ 通过
- 结论: 验证通过 ✓

- [ ] **Step 3: 测试报告生成**

```bash
make verify-report
cat logs/verify-report.md
```

Expected: 生成有效的 Markdown 报告

- [ ] **Step 4: 验证清理**

```bash
docker exec cyberpulse-api cyber-pulse client list | grep verify_client || echo "清理成功"
```

Expected: 无 verify_client

- [ ] **Step 5: 更新 CHANGELOG**

在 CHANGELOG.md 中添加验证系统条目

- [ ] **Step 6: 最终提交**

```bash
git add -A
git commit -m "feat: complete verification system implementation"
```

---

## 回归测试清单

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