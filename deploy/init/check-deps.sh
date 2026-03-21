#!/usr/bin/env bash
#
# check-deps.sh - 环境依赖检查脚本
#
# 功能:
#   - 检查 git 仓库
#   - 检查 Docker 安装
#   - 检查 Docker Compose 安装
#   - 检查端口可用性
#   - 检查磁盘空间
#   - 检查服务状态
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检查状态
ERRORS=0
WARNINGS=0

# 工具函数
print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_ok() {
    echo -e "  ${GREEN}[OK]${NC} $1"
}

print_error() {
    echo -e "  ${RED}[ERROR]${NC} $1"
    ((ERRORS++)) || true
}

print_warning() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++)) || true
}

print_info() {
    echo -e "  ${BLUE}[INFO]${NC} $1"
}

# 获取项目根目录
get_project_root() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$script_dir/../.." && pwd
}

PROJECT_ROOT=$(get_project_root)

# 1. 检查 git 仓库
check_git_repo() {
    print_header "Git 仓库检查"

    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        print_ok "Git 仓库存在"

        # 检查是否有未提交的更改（仅提示，不报错）
        if ! git -C "$PROJECT_ROOT" diff --quiet 2>/dev/null; then
            print_warning "存在未提交的更改"
        else
            print_ok "工作目录干净"
        fi

        # 显示当前分支
        local branch
        branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo "unknown")
        print_info "当前分支: $branch"
    else
        print_error "不是 Git 仓库"
    fi
}

# 2. 检查 Docker 安装
check_docker() {
    print_header "Docker 检查"

    if command -v docker &>/dev/null; then
        print_ok "Docker 已安装"

        local docker_version
        docker_version=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')
        print_info "Docker 版本: $docker_version"

        # 检查 Docker 服务是否运行
        if docker info &>/dev/null; then
            print_ok "Docker 服务正在运行"
        else
            print_error "Docker 服务未运行，请启动 Docker"
        fi
    else
        print_error "Docker 未安装"
        print_info "安装指南: https://docs.docker.com/get-docker/"
    fi
}

# 3. 检查 Docker Compose 安装
check_docker_compose() {
    print_header "Docker Compose 检查"

    # Docker Compose V2 (作为 docker 插件)
    if docker compose version &>/dev/null; then
        local compose_version
        compose_version=$(docker compose version --short 2>/dev/null)
        print_ok "Docker Compose 已安装 (V2 插件)"
        print_info "Docker Compose 版本: $compose_version"
    # Docker Compose V1 (独立命令)
    elif command -v docker-compose &>/dev/null; then
        local compose_version
        compose_version=$(docker-compose --version 2>/dev/null | awk '{print $3}' | tr -d ',')
        print_ok "Docker Compose 已安装 (V1)"
        print_info "Docker Compose 版本: $compose_version"
        print_warning "建议升级到 Docker Compose V2"
    else
        print_error "Docker Compose 未安装"
        print_info "Docker Compose V2 通常随 Docker Desktop 自动安装"
    fi
}

# 4. 检查端口可用性
check_ports() {
    print_header "端口检查"

    local ports=("8000:API 服务")

    for port_info in "${ports[@]}"; do
        local port="${port_info%%:*}"
        local service="${port_info#*:}"

        if command -v lsof &>/dev/null; then
            if lsof -i ":$port" &>/dev/null; then
                print_warning "端口 $port ($service) 已被占用"
                local pid
                pid=$(lsof -t -i ":$port" 2>/dev/null | head -1)
                if [[ -n "$pid" ]]; then
                    local process
                    process=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                    print_info "占用进程: $process (PID: $pid)"
                fi
            else
                print_ok "端口 $port ($service) 可用"
            fi
        elif command -v ss &>/dev/null; then
            if ss -tln | grep -q ":$port "; then
                print_warning "端口 $port ($service) 已被占用"
            else
                print_ok "端口 $port ($service) 可用"
            fi
        elif command -v netstat &>/dev/null; then
            if netstat -tln | grep -q ":$port "; then
                print_warning "端口 $port ($service) 已被占用"
            else
                print_ok "端口 $port ($service) 可用"
            fi
        else
            print_warning "无法检查端口 $port (缺少 lsof/ss/netstat 工具)"
        fi
    done
}

# 5. 检查磁盘空间
check_disk_space() {
    print_header "磁盘空间检查"

    local required_gb=2
    local available_kb
    local available_gb

    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS
        available_kb=$(df -k "$PROJECT_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
    else
        # Linux
        available_kb=$(df -k "$PROJECT_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
    fi

    if [[ -n "$available_kb" ]]; then
        available_gb=$((available_kb / 1024 / 1024))

        if ((available_gb >= required_gb)); then
            print_ok "可用磁盘空间: ${available_gb}GB (需要 ${required_gb}GB)"
        else
            print_error "磁盘空间不足: ${available_gb}GB (需要 ${required_gb}GB)"
        fi
    else
        print_warning "无法获取磁盘空间信息"
    fi
}

# 6. 检查服务状态
check_service_status() {
    print_header "服务状态检查"

    local compose_file="$PROJECT_ROOT/deploy/docker-compose.yml"

    if [[ ! -f "$compose_file" ]]; then
        print_warning "docker-compose.yml 不存在，跳过服务状态检查"
        return
    fi

    cd "$PROJECT_ROOT/deploy"

    # 检查容器是否运行
    local running_containers
    running_containers=$(docker compose ps -q 2>/dev/null | wc -l | tr -d ' ')

    if ((running_containers > 0)); then
        print_info "运行中的容器数量: $running_containers"
        docker compose ps 2>/dev/null || true
    else
        print_info "没有运行中的容器"
    fi
}

# 检查配置文件
check_config() {
    print_header "配置文件检查"

    local env_file="$PROJECT_ROOT/.env"

    if [[ -f "$env_file" ]]; then
        print_ok ".env 文件存在"

        # 检查文件权限
        local perms
        perms=$(stat -f "%OLp" "$env_file" 2>/dev/null || stat -c "%a" "$env_file" 2>/dev/null)

        if [[ "$perms" == "600" ]]; then
            print_ok ".env 文件权限正确 (600)"
        else
            print_warning ".env 文件权限: $perms (建议设置为 600)"
        fi

        # 检查必要的环境变量
        local required_vars=("POSTGRES_PASSWORD" "SECRET_KEY")
        for var in "${required_vars[@]}"; do
            if grep -q "^${var}=" "$env_file" 2>/dev/null; then
                print_ok "环境变量 $var 已配置"
            else
                print_warning "环境变量 $var 未配置"
            fi
        done
    else
        print_warning ".env 文件不存在，需要运行 'cyber-pulse.sh deploy' 生成配置"
    fi
}

# 打印摘要
print_summary() {
    print_header "检查摘要"

    echo -e "  错误: ${RED}${ERRORS}${NC}"
    echo -e "  警告: ${YELLOW}${WARNINGS}${NC}"

    if ((ERRORS > 0)); then
        echo -e "\n${RED}检查失败，请修复上述错误后重试${NC}"
        return 1
    elif ((WARNINGS > 0)); then
        echo -e "\n${YELLOW}检查通过，但存在警告${NC}"
        return 0
    else
        echo -e "\n${GREEN}所有检查通过！${NC}"
        return 0
    fi
}

# 主函数
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse 环境依赖检查                            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    check_git_repo
    check_docker
    check_docker_compose
    check_ports
    check_disk_space
    check_config
    check_service_status

    print_summary
}

# 执行主函数
main "$@"