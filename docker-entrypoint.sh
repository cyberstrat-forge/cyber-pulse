#!/bin/bash
#
# docker-entrypoint.sh - Cyber Pulse 容器入口点
#
# 功能:
#   - 自动执行数据库迁移（带重试机制）
#   - 执行传入的命令
#
# 环境变量:
#   MIGRATION_RETRY_COUNT  - 迁移重试次数（默认: 5）
#   MIGRATION_RETRY_DELAY  - 初始重试延迟秒数（默认: 2）
#   ALLOW_MIGRATION_FAILURE - 是否允许迁移失败后继续（默认: false）
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# 配置（可通过环境变量覆盖）
RETRY_COUNT="${MIGRATION_RETRY_COUNT:-5}"
RETRY_DELAY="${MIGRATION_RETRY_DELAY:-2}"
ALLOW_FAILURE="${ALLOW_MIGRATION_FAILURE:-false}"

echo -e "${GREEN}[entrypoint] Cyber Pulse starting...${NC}"

# 检测是否为可重试的错误（通常是连接问题）
is_retryable_error() {
    local error_output="$1"

    # 连接相关错误（数据库未就绪）
    if echo "$error_output" | grep -qiE "connection refused|could not connect|no such file|socket|network is unreachable|host is down|timeout expired"; then
        return 0  # 可重试
    fi

    return 1  # 不可重试
}

# 运行数据库迁移（带重试）
run_migrations() {
    echo -e "${YELLOW}[entrypoint] Running database migrations...${NC}"

    local attempt=1
    local delay=$RETRY_DELAY
    local last_error=""

    while [[ $attempt -le $RETRY_COUNT ]]; do
        echo -e "${YELLOW}[entrypoint] Migration attempt $attempt/$RETRY_COUNT${NC}"

        # 捕获输出和错误
        local output
        if output=$(alembic upgrade head 2>&1); then
            echo -e "${GREEN}[entrypoint] Migrations completed successfully${NC}"
            return 0
        fi

        last_error="$output"

        # 检查是否为可重试错误
        if is_retryable_error "$output"; then
            echo -e "${RED}[entrypoint] Connection error detected${NC}"

            if [[ $attempt -lt $RETRY_COUNT ]]; then
                echo -e "${YELLOW}[entrypoint] Retrying in ${delay}s...${NC}"
                sleep $delay
                delay=$((delay * 2))  # 指数退避
                ((attempt++))
                continue
            fi
        else
            # 非连接错误，不重试
            echo -e "${RED}[entrypoint] Non-retryable migration error:${NC}"
            echo "$output" | sed 's/^/  /'
            break
        fi

        ((attempt++))
    done

    # 所有重试都失败
    echo -e "${RED}[entrypoint] Migration failed after $attempt attempts${NC}"

    if [[ "$ALLOW_FAILURE" == "true" ]]; then
        echo -e "${YELLOW}[entrypoint] ALLOW_MIGRATION_FAILURE=true, continuing anyway...${NC}"
        return 0
    fi

    echo -e "${RED}[entrypoint] Set ALLOW_MIGRATION_FAILURE=true to continue on failure${NC}"
    return 1
}

# 运行迁移
if ! run_migrations; then
    exit 1
fi

# 执行传入的命令
echo -e "${GREEN}[entrypoint] Starting service: $*${NC}"
exec "$@"