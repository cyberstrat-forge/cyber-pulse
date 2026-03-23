#!/usr/bin/env bash
#
# generate-env.sh - 安全配置生成脚本
#
# 功能:
#   - 生成安全的数据库密码 (POSTGRES_PASSWORD)
#   - 生成 JWT 密钥 (SECRET_KEY)
#   - 创建 .env 配置文件
#   - 设置安全文件权限
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认配置
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# .env 文件放在 deploy 目录，docker-compose 在此目录执行
ENV_FILE="$PROJECT_ROOT/deploy/.env"
BACKUP_SUFFIX=".backup.$(date +%Y%m%d%H%M%S)"

# 生成安全密码的函数
generate_password() {
    local length="${1:-32}"

    # 优先使用 Python secrets 模块（更安全）
    if command -v python3 &>/dev/null; then
        python3 -c "import secrets; print(secrets.token_urlsafe($length))" 2>/dev/null && return
    fi

    # 备选方案：使用 openssl
    if command -v openssl &>/dev/null; then
        openssl rand -base64 "$((length * 3 / 4))" 2>/dev/null | tr -d '\n' && return
    fi

    # 最后备选：使用 /dev/urandom
    if [[ -r /dev/urandom ]]; then
        LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length" && return
    fi

    echo "Error: 无法生成安全密码" >&2
    return 1
}

# 生成数据库密码 (32 字符)
generate_db_password() {
    generate_password 32
}

# 生成 JWT 密钥 (64 字符，更强的安全性)
generate_secret_key() {
    generate_password 64
}

# 备份现有配置
backup_existing_env() {
    if [[ -f "$ENV_FILE" ]]; then
        echo -e "${YELLOW}发现现有 .env 文件，正在备份...${NC}"
        cp "$ENV_FILE" "$ENV_FILE$BACKUP_SUFFIX"
        echo -e "${GREEN}已备份到: $ENV_FILE$BACKUP_SUFFIX${NC}"
    fi
}

# 从现有配置中提取值
extract_existing_value() {
    local key="$1"
    local file="$2"

    if [[ -f "$file" ]]; then
        grep "^${key}=" "$file" 2>/dev/null | cut -d'=' -f2- || true
    fi
}

# 生成 .env 文件
generate_env_file() {
    local force="${1:-false}"
    local postgres_password=""
    local secret_key=""
    local db_user="cyberpulse"
    local db_name="cyberpulse"

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse 配置文件生成器                          ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 检查是否已存在配置
    if [[ -f "$ENV_FILE" && "$force" != "true" ]]; then
        echo -e "${YELLOW}.env 文件已存在。${NC}"
        echo -e "使用 --force 参数强制重新生成（将保留数据库密码）。"
        echo ""
        read -r -p "是否覆盖现有配置? (y/N): " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}操作已取消。${NC}"
            return 0
        fi
        backup_existing_env
    fi

    # 尝试保留现有密码（防止重新部署后无法访问数据）
    if [[ -f "$ENV_FILE" ]]; then
        local existing_password
        existing_password=$(extract_existing_value "POSTGRES_PASSWORD" "$ENV_FILE")
        if [[ -n "$existing_password" && "$existing_password" != "cyberpulse123" ]]; then
            echo -e "${BLUE}保留现有数据库密码...${NC}"
            postgres_password="$existing_password"
        fi
    fi

    # 生成新密码（如果需要）
    if [[ -z "$postgres_password" ]]; then
        echo -e "${BLUE}正在生成安全密码...${NC}"
        postgres_password=$(generate_db_password)
    fi

    secret_key=$(generate_secret_key)

    # 生成配置文件
    echo -e "${BLUE}正在生成配置文件...${NC}"

    cat > "$ENV_FILE" << EOF
# ==============================================
# Cyber Pulse 配置文件
# 自动生成于: $(date '+%Y-%m-%d %H:%M:%S')
# ==============================================

# 数据库配置
POSTGRES_USER=${db_user}
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_DB=${db_name}

# 数据库连接 URL（Docker 内部使用）
DATABASE_URL=postgresql://${db_user}:${postgres_password}@postgres:5432/${db_name}

# Redis 配置
REDIS_URL=redis://redis:6379/0

# Dramatiq 消息队列
DRAMATIQ_BROKER_URL=redis://redis:6379/1

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# JWT 安全配置
SECRET_KEY=${secret_key}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/cyber_pulse.log

# 环境
ENVIRONMENT=production
EOF

    # 设置安全权限
    chmod 600 "$ENV_FILE"

    echo ""
    echo -e "${GREEN}✓ 配置文件已生成: $ENV_FILE${NC}"
    echo ""
    echo -e "${BLUE}配置摘要:${NC}"
    echo -e "  数据库用户: ${db_user}"
    echo -e "  数据库名称: ${db_name}"
    echo -e "  数据库密码: ${YELLOW}********${NC} (${#postgres_password} 字符)"
    echo -e "  JWT 密钥:   ${YELLOW}********${NC} (${#secret_key} 字符)"
    echo -e "  文件权限:   600"
    echo ""
    echo -e "${YELLOW}⚠ 重要提示:${NC}"
    echo "  1. 请妥善保管此配置文件，不要提交到版本控制"
    echo "  2. 数据库密码仅在首次部署时生成，后续会保留"
    echo "  3. 如需重置密码，请手动删除 .env 文件后重新运行"
    echo ""
}

# 显示帮助信息
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --force, -f    强制重新生成配置（保留数据库密码）"
    echo "  --help, -h     显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0              交互式生成配置"
    echo "  $0 --force      强制重新生成配置"
}

# 主函数
main() {
    local force="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)
                force="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                echo -e "${RED}未知参数: $1${NC}"
                show_help
                exit 1
                ;;
        esac
    done

    generate_env_file "$force"
}

main "$@"