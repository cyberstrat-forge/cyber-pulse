#!/usr/bin/env bash
#
# cyber-pulse.sh - Cyber Pulse 统一管理入口
#
# 功能:
#   - deploy:      部署服务（检查依赖 + 生成配置 + 启动服务）
#   - start:       启动服务
#   - stop:        停止服务
#   - restart:     重启服务
#   - status:      查看服务状态
#   - logs:        查看日志
#   - config:      配置管理
#   - check-update: 检查更新
#   - upgrade:     升级系统（自动快照 + 失败回滚）
#   - snapshot:    快照管理
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
UPGRADE_DIR="$DEPLOY_DIR/upgrade"
SNAPSHOTS_DIR="$PROJECT_ROOT/.snapshots"

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

# check-update 命令 - 检查更新
cmd_check_update() {
    print_header "检查 Cyber Pulse 更新"

    bash "$UPGRADE_DIR/check-update.sh" "$@"
}

# upgrade 命令 - 升级系统
cmd_upgrade() {
    local target_version=""
    local force="false"
    local skip_snapshot="false"
    local dry_run="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version|-v)
                target_version="$2"
                shift 2
                ;;
            --force|-f)
                force="true"
                shift
                ;;
            --skip-snapshot)
                skip_snapshot="true"
                shift
                ;;
            --dry-run)
                dry_run="true"
                shift
                ;;
            --help|-h)
                print_upgrade_help
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                print_upgrade_help
                exit 1
                ;;
        esac
    done

    print_banner
    print_header "升级 Cyber Pulse"

    # 1. 预检查
    print_step "执行预检查..."

    # 检查 git 仓库
    if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
        die "当前目录不是 git 仓库，无法使用 upgrade 命令"
    fi

    # 检查 Docker
    check_docker
    check_docker_compose

    # 检查服务健康状态
    cd "$DEPLOY_DIR"
    if ! $DOCKER_COMPOSE ps 2>/dev/null | grep -q "running"; then
        print_warning "服务未运行，建议先启动服务"
    fi

    # 2. 确定目标版本
    if [[ -z "$target_version" ]]; then
        print_step "获取最新版本信息..."

        local version_info
        version_info=$(bash "$UPGRADE_DIR/check-update.sh" 2>/dev/null) || true

        if [[ -n "$version_info" ]]; then
            target_version=$(echo "$version_info" | grep "^LATEST_VERSION=" | cut -d= -f2)
        fi

        if [[ -z "$target_version" ]]; then
            print_warning "无法获取最新版本，使用 main 分支"
            target_version="main"
        fi
    fi

    print_info "目标版本: $target_version"

    # 3. Dry run 模式
    if [[ "$dry_run" == "true" ]]; then
        print_info "Dry run 模式，不会执行实际升级"
        echo ""
        echo -e "${BOLD}升级计划:${NC}"
        echo "  1. 创建快照"
        echo "  2. 获取代码: git fetch origin && git checkout $target_version"
        echo "  3. 构建镜像: docker compose build --no-cache"
        echo "  4. 运行迁移: alembic upgrade head"
        echo "  5. 重启服务: docker compose up -d"
        echo "  6. 健康检查"
        echo "  7. 失败时回滚"
        echo ""
        return 0
    fi

    # 4. 确认升级
    if [[ "$force" != "true" ]]; then
        echo ""
        print_warning "升级将重启所有服务，请确保已保存工作"
        read -r -p "确认升级到 $target_version? (yes/no): " response
        if [[ "$response" != "yes" ]]; then
            print_info "升级已取消"
            exit 0
        fi
    fi

    # 5. 创建快照
    local snapshot_name=""
    if [[ "$skip_snapshot" != "true" ]]; then
        print_step "创建升级快照..."

        if bash "$UPGRADE_DIR/create-snapshot.sh"; then
            # 获取最新的快照名称
            snapshot_name=$(ls -t "$SNAPSHOTS_DIR" 2>/dev/null | head -1)
            print_success "快照已创建: $snapshot_name"
        else
            print_warning "快照创建失败，继续升级"
        fi
    else
        print_warning "跳过快照创建"
    fi

    # 6. 执行升级
    local upgrade_failed="false"

    cd "$PROJECT_ROOT"

    # 获取代码
    print_step "获取最新代码..."
    if ! git fetch origin; then
        print_error "git fetch 失败"
        upgrade_failed="true"
    fi

    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "切换到版本 $target_version..."

        # 保存当前分支
        local current_branch
        current_branch=$(git branch --show-current 2>/dev/null || echo "main")

        if ! git checkout "$target_version" 2>/dev/null; then
            print_warning "无法切换到 $target_version，尝试拉取远程分支"
            if ! git checkout -b "$target_version" "origin/$target_version" 2>/dev/null; then
                print_error "无法切换到目标版本"
                upgrade_failed="true"
            fi
        fi
    fi

    # 构建镜像
    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "构建 Docker 镜像..."
        cd "$DEPLOY_DIR"

        if ! $DOCKER_COMPOSE build --no-cache; then
            print_error "Docker 镜像构建失败"
            upgrade_failed="true"
        fi
    fi

    # 停止服务
    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "停止服务..."
        cd "$DEPLOY_DIR"
        $DOCKER_COMPOSE down
    fi

    # 启动服务（会自动运行迁移）
    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "启动服务..."
        cd "$DEPLOY_DIR"

        if ! $DOCKER_COMPOSE up -d; then
            print_error "服务启动失败"
            upgrade_failed="true"
        fi
    fi

    # 运行数据库迁移
    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "运行数据库迁移..."
        sleep 5  # 等待数据库就绪

        if $DOCKER_COMPOSE exec -T api alembic upgrade head 2>/dev/null; then
            print_success "数据库迁移完成"
        else
            print_warning "数据库迁移可能已失败，请检查日志"
        fi
    fi

    # 7. 健康检查
    if [[ "$upgrade_failed" != "true" ]]; then
        print_step "执行健康检查..."
        sleep 5

        local healthy="true"
        for service in postgres redis api worker scheduler; do
            if $DOCKER_COMPOSE ps "$service" 2>/dev/null | grep -q "running"; then
                echo -e "  ${GREEN}[●]${NC} $service - 运行中"
            else
                echo -e "  ${RED}[○]${NC} $service - 未运行"
                healthy="false"
            fi
        done

        if [[ "$healthy" == "false" ]]; then
            print_warning "部分服务未正常运行"
            upgrade_failed="true"
        fi
    fi

    # 8. 结果处理
    if [[ "$upgrade_failed" == "true" ]]; then
        echo ""
        print_error "升级失败!"

        if [[ -n "$snapshot_name" ]]; then
            echo ""
            print_warning "正在自动回滚..."

            # 恢复快照（数据库和配置）
            if bash "$UPGRADE_DIR/restore-snapshot.sh" "$snapshot_name" --force; then
                print_success "快照已恢复"

                # 切换回原来的代码版本
                print_step "切换回原版本代码..."
                cd "$PROJECT_ROOT"
                if git checkout "$current_branch" 2>/dev/null; then
                    print_success "已切换回分支: $current_branch"
                else
                    print_warning "无法切换回原分支: $current_branch"
                fi

                # 重启服务
                print_step "重启服务..."
                cd "$DEPLOY_DIR"
                $DOCKER_COMPOSE down
                $DOCKER_COMPOSE up -d
                sleep 3

                print_success "回滚完成，服务已恢复"
            else
                print_error "快照恢复失败，请手动处理"
                echo "  手动回滚命令: cyber-pulse.sh snapshot restore $snapshot_name --force"
            fi
        fi

        exit 1
    else
        # 更新版本文件
        echo "$target_version" > "$PROJECT_ROOT/.version" 2>/dev/null || true

        # 清理快照（升级成功后删除）
        if [[ -n "$snapshot_name" && -d "$SNAPSHOTS_DIR/$snapshot_name" ]]; then
            print_step "清理升级快照..."
            rm -rf "$SNAPSHOTS_DIR/$snapshot_name"
            print_success "快照已清理: $snapshot_name"
        fi

        echo ""
        print_success "升级完成! 当前版本: $target_version"
        echo ""
        echo -e "${GREEN}访问地址:${NC}"
        echo -e "  API:      ${CYAN}http://localhost:8000${NC}"
        echo -e "  API 文档: ${CYAN}http://localhost:8000/docs${NC}"
    fi
}

# snapshot 命令 - 快照管理
cmd_snapshot() {
    local subcommand="${1:-list}"

    case "$subcommand" in
        create)
            bash "$UPGRADE_DIR/create-snapshot.sh" "${@:2}"
            ;;
        restore)
            bash "$UPGRADE_DIR/restore-snapshot.sh" "${@:2}"
            ;;
        list)
            bash "$UPGRADE_DIR/restore-snapshot.sh" --list
            ;;
        *)
            print_error "未知子命令: $subcommand"
            print_snapshot_help
            return 1
            ;;
    esac
}

# 打印 upgrade 帮助
print_upgrade_help() {
    echo ""
    echo "升级命令:"
    echo "  [--version <ver>]  指定目标版本 (默认: 最新版本)"
    echo "  [--force]          跳过确认提示"
    echo "  [--skip-snapshot]  跳过快照创建"
    echo "  [--dry-run]        仅显示升级计划，不执行"
    echo ""
    echo "示例:"
    echo "  cyber-pulse.sh upgrade              升级到最新版本"
    echo "  cyber-pulse.sh upgrade --dry-run    预览升级计划"
    echo "  cyber-pulse.sh upgrade -v v1.2.0    升级到指定版本"
}

# 打印 snapshot 帮助
print_snapshot_help() {
    echo ""
    echo "快照管理命令:"
    echo "  create [--retention <days>]  创建快照"
    echo "  restore <name> [--force]     恢复快照"
    echo "  list                         列出快照"
    echo ""
    echo "示例:"
    echo "  cyber-pulse.sh snapshot create           创建快照"
    echo "  cyber-pulse.sh snapshot list             列出快照"
    echo "  cyber-pulse.sh snapshot restore snap_1   恢复快照"
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
    echo "  check-update        检查更新"
    echo "  upgrade [选项]      升级系统（自动快照 + 失败回滚）"
    echo "                      --version <ver>    指定版本"
    echo "                      --dry-run          预览计划"
    echo "                      --force            跳过确认"
    echo "  snapshot <subcommand> 快照管理"
    echo "                      create             创建快照"
    echo "                      restore <name>     恢复快照"
    echo "                      list               列出快照"
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
    echo "  cyber-pulse.sh check-update      # 检查更新"
    echo "  cyber-pulse.sh upgrade           # 升级系统"
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
        check-update)
            shift || true
            cmd_check_update "$@"
            ;;
        upgrade)
            cmd_upgrade "${@:2}"
            ;;
        snapshot)
            cmd_snapshot "${@:2}"
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