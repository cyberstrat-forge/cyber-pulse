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