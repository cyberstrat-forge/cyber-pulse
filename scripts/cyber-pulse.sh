#!/usr/bin/env bash
#
# cyber-pulse.sh - Cyber Pulse 统一管理入口
#
# 功能:
#   - deploy:  部署服务（检查依赖 + 生成配置 + 启动服务）
#   - start:   启动服务
#   - stop:    停止服务
#   - restart: 重启服务
#   - status:  查看服务状态
#   - logs:    查看日志
#   - config:  配置管理
#

set -euo pipefail

# ============================================
# 全局配置
# ============================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 获取项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# Docker Compose 命令
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# ============================================
# 工具函数
# ============================================

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║   ██████╗██╗   ██╗██████╗ ███████╗██████╗                   ║"
    echo "║  ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗                  ║"
    echo "║  ██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝                  ║"
    echo "║  ██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗                  ║"
    echo "║  ╚██████╗   ██║   ██████╔╝███████╗██║  ██║                  ║"
    echo "║   ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝                  ║"
    echo "║                                                              ║"
    echo "║        Cyber Pulse - 战略情报采集系统                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
}

print_step() {
    echo -e "\n${CYAN}[→]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

die() {
    print_error "$1"
    exit 1
}

# 检查 Docker 是否可用
check_docker() {
    if ! command -v docker &>/dev/null; then
        die "Docker 未安装。请先安装 Docker。"
    fi

    if ! docker info &>/dev/null; then
        die "Docker 服务未运行。请启动 Docker。"
    fi
}

# 检查 Docker Compose 是否可用
check_docker_compose() {
    if ! docker compose version &>/dev/null && ! command -v docker-compose &>/dev/null; then
        die "Docker Compose 未安装。"
    fi
}

# 确保 .env 文件存在
ensure_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        print_warning ".env 文件不存在，正在生成..."
        bash "$DEPLOY_DIR/init/generate-env.sh" --force
    fi
}

# ============================================
# 命令实现
# ============================================

# deploy 命令 - 完整部署
cmd_deploy() {
    print_banner
    print_header "部署 Cyber Pulse"

    # 1. 检查依赖
    print_step "检查系统依赖..."
    if ! bash "$DEPLOY_DIR/init/check-deps.sh"; then
        die "依赖检查失败，请修复上述问题后重试"
    fi

    # 2. 生成配置
    print_step "生成安全配置..."
    if [[ -f "$ENV_FILE" ]]; then
        print_warning ".env 文件已存在，跳过配置生成"
        print_info "使用 --force 重新生成配置: cyber-pulse.sh config generate --force"
    else
        bash "$DEPLOY_DIR/init/generate-env.sh" --force
    fi

    # 3. 创建必要目录
    print_step "创建数据目录..."
    mkdir -p "$PROJECT_ROOT/data"
    mkdir -p "$PROJECT_ROOT/logs"

    # 4. 拉取/构建镜像
    print_step "构建 Docker 镜像..."
    cd "$DEPLOY_DIR"
    $DOCKER_COMPOSE build --no-cache

    # 5. 启动服务
    print_step "启动服务..."
    $DOCKER_COMPOSE up -d

    # 6. 等待服务就绪
    print_step "等待服务启动..."
    sleep 5

    # 7. 显示状态
    print_step "服务状态:"
    $DOCKER_COMPOSE ps

    echo ""
    print_success "部署完成！"
    echo ""
    echo -e "${GREEN}访问地址:${NC}"
    echo -e "  API:      ${CYAN}http://localhost:8000${NC}"
    echo -e "  API 文档: ${CYAN}http://localhost:8000/docs${NC}"
    echo ""
    echo -e "${YELLOW}常用命令:${NC}"
    echo -e "  查看状态: ${CYAN}cyber-pulse.sh status${NC}"
    echo -e "  查看日志: ${CYAN}cyber-pulse.sh logs${NC}"
    echo -e "  停止服务: ${CYAN}cyber-pulse.sh stop${NC}"
}

# start 命令 - 启动服务
cmd_start() {
    print_header "启动 Cyber Pulse 服务"

    check_docker
    check_docker_compose
    ensure_env_file

    cd "$DEPLOY_DIR"

    print_step "启动服务..."
    $DOCKER_COMPOSE up -d

    sleep 3
    print_step "服务状态:"
    $DOCKER_COMPOSE ps

    print_success "服务已启动"
}

# stop 命令 - 停止服务
cmd_stop() {
    print_header "停止 Cyber Pulse 服务"

    check_docker
    check_docker_compose

    cd "$DEPLOY_DIR"

    print_step "停止服务..."
    $DOCKER_COMPOSE down

    print_success "服务已停止"
}

# restart 命令 - 重启服务
cmd_restart() {
    print_header "重启 Cyber Pulse 服务"

    check_docker
    check_docker_compose
    ensure_env_file

    cd "$DEPLOY_DIR"

    print_step "重启服务..."
    $DOCKER_COMPOSE down
    $DOCKER_COMPOSE up -d

    sleep 3
    print_step "服务状态:"
    $DOCKER_COMPOSE ps

    print_success "服务已重启"
}

# status 命令 - 查看服务状态
cmd_status() {
    print_header "Cyber Pulse 服务状态"

    check_docker

    cd "$DEPLOY_DIR"

    # 检查容器状态
    echo -e "${BOLD}容器状态:${NC}"
    $DOCKER_COMPOSE ps

    echo ""

    # 检查健康状态
    echo -e "${BOLD}健康检查:${NC}"
    local services=("postgres" "redis" "api" "worker" "scheduler")

    for service in "${services[@]}"; do
        local status
        status=$($DOCKER_COMPOSE ps --status running "$service" 2>/dev/null | grep -c "$service" 2>/dev/null || echo "0")
        status=$(echo "$status" | tr -d '[:space:]')

        if [[ "$status" -gt 0 ]]; then
            echo -e "  ${GREEN}[●]${NC} $service - 运行中"
        else
            echo -e "  ${RED}[○]${NC} $service - 未运行"
        fi
    done

    echo ""

    # 显示资源使用
    echo -e "${BOLD}资源使用:${NC}"
    $DOCKER_COMPOSE top 2>/dev/null || echo "  (无运行中的容器)"
}

# logs 命令 - 查看日志
cmd_logs() {
    local service="${1:-}"
    local follow="${2:-false}"
    local tail="${3:-100}"

    check_docker
    cd "$DEPLOY_DIR"

    local cmd_args=()
    cmd_args+=("logs")
    cmd_args+=("--tail" "$tail")

    if [[ "$follow" == "true" ]]; then
        cmd_args+=("-f")
    fi

    if [[ -n "$service" ]]; then
        cmd_args+=("$service")
    fi

    $DOCKER_COMPOSE "${cmd_args[@]}"
}

# config 命令 - 配置管理
cmd_config() {
    local subcommand="${1:-show}"
    local reveal="${2:-false}"

    case "$subcommand" in
        show)
            print_header "配置信息"

            if [[ ! -f "$ENV_FILE" ]]; then
                print_error ".env 文件不存在"
                print_info "运行 'cyber-pulse.sh deploy' 生成配置"
                return 1
            fi

            echo -e "${BOLD}配置文件: $ENV_FILE${NC}\n"

            if [[ "$reveal" == "--reveal" || "$reveal" == "-r" ]]; then
                cat "$ENV_FILE"
            else
                # 隐藏敏感信息
                grep -E "^(POSTGRES_USER|POSTGRES_DB|API_HOST|API_PORT|LOG_LEVEL|ENVIRONMENT)=" "$ENV_FILE" 2>/dev/null || true
                echo "POSTGRES_PASSWORD=********"
                echo "SECRET_KEY=********"
                echo ""
                print_info "使用 --reveal 参数查看完整配置"
            fi
            ;;

        generate)
            local force="false"
            if [[ "${2:-}" == "--force" || "${2:-}" == "-f" ]]; then
                force="true"
            fi
            bash "$DEPLOY_DIR/init/generate-env.sh" ${force:+--force}
            ;;

        check)
            print_header "配置检查"
            bash "$DEPLOY_DIR/init/check-deps.sh"
            ;;

        *)
            print_error "未知子命令: $subcommand"
            print_config_help
            return 1
            ;;
    esac
}

# 打印 config 帮助
print_config_help() {
    echo ""
    echo "配置管理命令:"
    echo "  show [--reveal]    显示配置信息（--reveal 显示敏感信息）"
    echo "  generate [--force] 生成新配置（--force 强制覆盖）"
    echo "  check              检查配置和依赖"
}

# 显示帮助信息
show_help() {
    print_banner

    echo "用法: cyber-pulse.sh <命令> [选项]"
    echo ""
    echo -e "${BOLD}命令:${NC}"
    echo "  deploy              部署服务（完整部署流程）"
    echo "  start               启动服务"
    echo "  stop                停止服务"
    echo "  restart             重启服务"
    echo "  status              查看服务状态"
    echo "  logs [service]      查看日志（可选指定服务）"
    echo "                      服务: api, worker, scheduler, postgres, redis"
    echo "  config <subcommand> 配置管理"
    echo "                      show [--reveal]    显示配置"
    echo "                      generate [--force] 生成配置"
    echo "                      check              检查配置"
    echo "  help                显示此帮助信息"
    echo ""
    echo -e "${BOLD}日志选项:${NC}"
    echo "  cyber-pulse.sh logs              查看所有服务日志"
    echo "  cyber-pulse.sh logs api          查看指定服务日志"
    echo "  cyber-pulse.sh logs api -f       实时跟踪日志"
    echo ""
    echo -e "${BOLD}示例:${NC}"
    echo "  cyber-pulse.sh deploy            # 首次部署"
    echo "  cyber-pulse.sh status            # 查看状态"
    echo "  cyber-pulse.sh logs api -f       # 实时查看 API 日志"
    echo "  cyber-pulse.sh config show       # 查看配置"
}

# 打印简短帮助
print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# ============================================
# 主入口
# ============================================

main() {
    local command="${1:-help}"

    case "$command" in
        deploy)
            cmd_deploy
            ;;
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart
            ;;
        status)
            cmd_status
            ;;
        logs)
            local service="${2:-}"
            local follow="false"
            if [[ "${3:-}" == "-f" || "${3:-}" == "--follow" ]]; then
                follow="true"
            fi
            cmd_logs "$service" "$follow" "100"
            ;;
        config)
            cmd_config "${2:-show}" "${3:-}"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"