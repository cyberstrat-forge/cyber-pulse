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

CONTAINER_API="cyber-pulse-api-1"
CONTAINER_WORKER="cyber-pulse-worker-1"
CONTAINER_SCHEDULER="cyber-pulse-scheduler-1"
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

# ============================================================================
# 情报源管理
# ============================================================================

verify_source_management() {
    echo ""
    echo "[情报源管理]"

    # 使用 Python 解析 YAML 并调用 CLI
    export SOURCES_FILE
    export CONTAINER_API
    python3 << 'PYEOF'
import yaml
import subprocess
import sys
import os
import re

sources_file = os.environ.get('SOURCES_FILE', 'sources.yaml')
container_api = os.environ.get('CONTAINER_API', 'cyber-pulse-api-1')

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
    cmd = ["docker", "exec", container_api, "cyber-pulse", "source", "add",
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