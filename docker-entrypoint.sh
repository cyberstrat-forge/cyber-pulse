#!/bin/bash
#
# docker-entrypoint.sh - Cyber Pulse 容器入口点
#
# 功能:
#   - 自动执行数据库迁移
#   - 执行传入的命令
#
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${GREEN}[entrypoint] Cyber Pulse starting...${NC}"

# 运行数据库迁移
echo -e "${YELLOW}[entrypoint] Running database migrations...${NC}"
if alembic upgrade head; then
    echo -e "${GREEN}[entrypoint] Migrations completed successfully${NC}"
else
    echo -e "${RED}[entrypoint] Migration failed, continuing anyway...${NC}"
    # 不退出，允许服务继续启动（可能是首次启动，数据库还未就绪）
fi

# 执行传入的命令
echo -e "${GREEN}[entrypoint] Starting service: $*${NC}"
exec "$@"