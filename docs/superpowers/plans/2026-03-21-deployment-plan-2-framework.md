# 部署优化计划2：cyber-pulse.sh 框架与核心命令

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建统一入口脚本 cyber-pulse.sh，实现 deploy、start、stop、restart、status、logs 命令。

**Architecture:** Bash 脚本，作为所有部署管理操作的统一入口。调用 docker-compose 和其他子脚本完成任务。

**Tech Stack:** Bash, Docker, Docker Compose

**依赖:** 计划1 (install.sh)

---

## 文件结构

```
cyber-pulse/
├── scripts/
│   ├── cyber-pulse.sh           # 新建：统一入口脚本
│   └── verify.sh                # 已存在：验证脚本
├── deploy/
│   ├── docker-compose.yml       # 新建：基础配置（从根目录移动）
│   ├── docker-compose.dev.yml   # 新建：开发环境覆盖
│   ├── docker-compose.test.yml  # 新建：测试环境覆盖
│   ├── docker-compose.prod.yml  # 新建：生产环境覆盖
│   └── init/
│       ├── check-deps.sh        # 新建：依赖检查
│       └── generate-env.sh      # 新建：安全配置生成
├── .env.example                 # 修改：更新配置模板
└── docker-compose.yml           # 移动到 deploy/
```

---

## Task 1: 创建目录结构和移动 docker-compose.yml

**Files:**
- Create: `deploy/` 目录
- Move: `docker-compose.yml` → `deploy/docker-compose.yml`

- [ ] **Step 1: 创建 deploy 目录结构**

Run: `mkdir -p deploy/init`

- [ ] **Step 2: 移动 docker-compose.yml 到 deploy 目录**

Run: `mv docker-compose.yml deploy/docker-compose.yml`

- [ ] **Step 3: 提交目录结构变更**

```bash
git add deploy/
git rm docker-compose.yml
git commit -m "$(cat <<'EOF'
refactor(deploy): reorganize deployment files into deploy/ directory

Move docker-compose.yml to deploy/ directory for better organization.
Prepare structure for multi-environment support.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 创建依赖检查脚本

**Files:**
- Create: `deploy/init/check-deps.sh`

- [ ] **Step 1: 创建依赖检查脚本**

```bash
#!/bin/bash
#
# cyber-pulse 依赖检查脚本
#
# 检查 Docker、Docker Compose、git、端口、磁盘空间等

set -e

# ============================================================================
# 配置
# ============================================================================

MIN_DOCKER_VERSION="20.10"
MIN_DISK_SPACE_GB=2
REQUIRED_PORT=8000

# ============================================================================
# 颜色输出
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() { echo -e "  ${GREEN}✓${NC} $1"; }
log_err() { echo -e "  ${RED}✗${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }

# ============================================================================
# 检查函数
# ============================================================================

check_git_repo() {
    echo "检查 git 仓库..."
    if [ -d ".git" ]; then
        log_ok "git 仓库"
    else
        log_err "非 git 仓库"
        echo ""
        echo "  请使用 git clone 安装 cyber-pulse"
        echo "  不支持 ZIP 下载安装"
        return 1
    fi
}

check_docker() {
    echo "检查 Docker..."
    if ! command -v docker &> /dev/null; then
        log_err "Docker 未安装"
        echo ""
        echo "  安装 Docker: https://docs.docker.com/get-docker/"
        return 1
    fi

    local version
    version=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    log_ok "Docker 已安装 (版本 $version)"
}

check_docker_compose() {
    echo "检查 Docker Compose..."
    if docker compose version &> /dev/null; then
        local version
        version=$(docker compose version --short)
        log_ok "Docker Compose 已安装 (版本 $version)"
    elif command -v docker-compose &> /dev/null; then
        local version
        version=$(docker-compose version --short)
        log_ok "docker-compose 已安装 (版本 $version)"
    else
        log_err "Docker Compose 未安装"
        echo ""
        echo "  安装 Docker Compose: https://docs.docker.com/compose/install/"
        return 1
    fi
}

check_port() {
    echo "检查端口 $REQUIRED_PORT..."
    if lsof -i ":$REQUIRED_PORT" &> /dev/null; then
        log_err "端口 $REQUIRED_PORT 已被占用"
        echo ""
        echo "  解决方案:"
        echo "    1. 释放端口: lsof -i :$REQUIRED_PORT"
        echo "    2. 修改配置: 在 .env 中设置 API_PORT=其他端口"
        return 1
    else
        log_ok "端口 $REQUIRED_PORT 可用"
    fi
}

check_disk_space() {
    echo "检查磁盘空间..."
    local available_gb

    if [[ "$OSTYPE" == "darwin"* ]]; then
        available_gb=$(df -g . | awk 'NR==2 {print $4}')
    else
        available_gb=$(df -BG . | awk 'NR==2 {print $4}' | tr -d 'G')
    fi

    if [ "$available_gb" -ge "$MIN_DISK_SPACE_GB" ]; then
        log_ok "磁盘空间充足 (${available_gb}GB 可用)"
    else
        log_err "磁盘空间不足 (需要 ${MIN_DISK_SPACE_GB}GB，当前 ${available_gb}GB)"
        return 1
    fi
}

check_services_running() {
    echo "检查服务状态..."
    if docker compose -f deploy/docker-compose.yml ps 2>/dev/null | grep -q "Up"; then
        log_warn "服务正在运行"
    else
        log_ok "服务未运行（可部署）"
    fi
}

# ============================================================================
# 主流程
# ============================================================================

check_all() {
    local errors=0

    check_git_repo || ((errors++))
    check_docker || ((errors++))
    check_docker_compose || ((errors++))
    check_port || ((errors++))
    check_disk_space || ((errors++))
    check_services_running

    echo ""
    if [ $errors -eq 0 ]; then
        echo -e "${GREEN}所有检查通过${NC}"
        return 0
    else
        echo -e "${RED}发现 $errors 个问题，请修复后重试${NC}"
        return 1
    fi
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_all
fi
```

- [ ] **Step 2: 设置执行权限**

Run: `chmod +x deploy/init/check-deps.sh`

- [ ] **Step 3: 测试依赖检查**

Run: `./deploy/init/check-deps.sh`

Expected: 显示各项检查结果

- [ ] **Step 4: 提交**

```bash
git add deploy/init/check-deps.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add dependency check script

Add check-deps.sh that verifies:
- Git repository
- Docker installation
- Docker Compose installation
- Port 8000 availability
- Disk space (min 2GB)
- Service status

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 创建安全配置生成脚本

**Files:**
- Create: `deploy/init/generate-env.sh`

- [ ] **Step 1: 创建配置生成脚本**

```bash
#!/bin/bash
#
# cyber-pulse 安全配置生成脚本
#
# 生成 .env 文件，包含随机密码和密钥

set -e

# ============================================================================
# 配置
# ============================================================================

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

# ============================================================================
# 颜色输出
# ============================================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# 密码生成
# ============================================================================

generate_password() {
    # 生成 32 字符的安全密码
    python3 -c "import secrets; print(secrets.token_urlsafe(24))"
}

generate_secret_key() {
    # 生成 64 字符的 JWT 密钥
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

# ============================================================================
# 配置生成
# ============================================================================

generate_env() {
    echo "生成安全配置..."

    local db_password
    local secret_key

    db_password=$(generate_password)
    secret_key=$(generate_secret_key)

    cat > "$ENV_FILE" << EOF
# cyber-pulse 配置文件
# 由部署脚本自动生成

# 数据库配置
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=${db_password}

# 安全密钥 (JWT 签名)
SECRET_KEY=${secret_key}

# 服务连接配置 (容器内部网络)
DATABASE_URL=postgresql://cyberpulse:${db_password}@postgres:5432/cyberpulse
REDIS_URL=redis://redis:6379/0
DRAMATIQ_BROKER_URL=redis://redis:6379/1

# API 配置
API_HOST=0.0.0.0
API_PORT=8000

# 日志配置
LOG_LEVEL=INFO
EOF

    # 设置文件权限
    chmod 600 "$ENV_FILE"

    echo -e "  ${GREEN}✓${NC} 配置已生成并保存到 $ENV_FILE"
    echo -e "  ${BLUE}ℹ${NC} 查看配置: ./scripts/cyber-pulse.sh config show --reveal"
}

# ============================================================================
# 主流程
# ============================================================================

main() {
    if [ -f "$ENV_FILE" ]; then
        echo "配置文件已存在: $ENV_FILE"
        return 0
    fi

    generate_env
}

main "$@"
```

- [ ] **Step 2: 设置执行权限**

Run: `chmod +x deploy/init/generate-env.sh`

- [ ] **Step 3: 测试配置生成**

Run: `./deploy/init/generate-env.sh && cat .env`

Expected: 显示生成的配置文件

- [ ] **Step 4: 清理测试文件**

Run: `rm -f .env`

- [ ] **Step 5: 提交**

```bash
git add deploy/init/generate-env.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add secure configuration generation script

Add generate-env.sh that:
- Generates random POSTGRES_PASSWORD (32 chars)
- Generates random SECRET_KEY for JWT (64 chars)
- Creates .env file with proper permissions (600)

Uses secrets.token_urlsafe for cryptographically secure random generation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 创建统一入口脚本框架

**Files:**
- Create: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 创建脚本框架和基础命令**

```bash
#!/bin/bash
#
# cyber-pulse 统一入口脚本
#
# 用法: ./scripts/cyber-pulse.sh <command> [options]

set -e

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
ENV_FILE="$PROJECT_ROOT/.env"
VERSION_FILE="$PROJECT_ROOT/.version"

# Docker Compose 文件
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"

# 容器名称
CONTAINER_PREFIX="cyber-pulse"

# ============================================================================
# 颜色输出
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step() { echo -e "${CYAN}==>${NC} $1"; }

# ============================================================================
# 帮助信息
# ============================================================================

show_help() {
    cat << EOF
cyber-pulse 部署管理脚本

用法:
  ./scripts/cyber-pulse.sh <command> [options]

命令:
  deploy [--env ENV]      一键部署 (默认 dev 环境)
  start                   启动服务
  stop                    停止服务
  restart                 重启服务
  status                  查看状态 (含健康检查)
  logs [SERVICE]          查看日志
  upgrade [VERSION]       升级到指定版本 (默认最新)
  check-update            检查是否有新版本
  backup                  备份数据和配置
  restore <file>          从备份恢复
  config show [--reveal]  查看配置 (--reveal 显示敏感信息)
  uninstall               完全卸载
  help                    显示此帮助

示例:
  ./scripts/cyber-pulse.sh deploy
  ./scripts/cyber-pulse.sh deploy --env prod
  ./scripts/cyber-pulse.sh logs api
  ./scripts/cyber-pulse.sh status

EOF
}

# ============================================================================
# 工具函数
# ============================================================================

cd_project() {
    cd "$PROJECT_ROOT"
}

dc() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

get_version() {
    if [ -f "$VERSION_FILE" ]; then
        cat "$VERSION_FILE"
    else
        git describe --tags 2>/dev/null || echo "unknown"
    fi
}

save_version() {
    git describe --tags > "$VERSION_FILE" 2>/dev/null || true
}

# ============================================================================
# deploy 命令
# ============================================================================

cmd_deploy() {
    local env="${1:-dev}"
    local compose_files="-f $COMPOSE_FILE"

    # 添加环境覆盖文件
    if [ "$env" != "dev" ] && [ -f "$DEPLOY_DIR/docker-compose.$env.yml" ]; then
        compose_files="$compose_files -f $DEPLOY_DIR/docker-compose.$env.yml"
    fi

    log_step "部署 cyber-pulse (环境: $env)"

    cd_project

    # 1. 依赖检查
    log_info "检查依赖..."
    "$DEPLOY_DIR/init/check-deps.sh" || exit 1

    # 2. 配置初始化
    if [ ! -f "$ENV_FILE" ]; then
        log_info "生成配置..."
        "$DEPLOY_DIR/init/generate-env.sh"
    fi

    # 3. 启动服务
    log_info "启动服务..."
    docker compose $compose_files up -d --build

    # 4. 等待服务就绪
    log_info "等待服务就绪..."
    sleep 10

    # 5. 数据库迁移
    log_info "执行数据库迁移..."
    docker compose $compose_files exec -T api alembic upgrade head 2>/dev/null || true

    # 6. 保存版本
    save_version

    # 7. 显示完成信息
    local version
    version=$(get_version)

    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│ ✅ cyber-pulse 部署成功                                      │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ 版本:     $version"
    echo "│ 环境:     $env"
    echo "│ API:      http://localhost:8000"
    echo "│ 文档:     http://localhost:8000/docs"
    echo "│                                                             │"
    echo "│ 配置文件: .env"
    echo "│ 查看状态: ./scripts/cyber-pulse.sh status                   │"
    echo "╰─────────────────────────────────────────────────────────────╯"
}

# ============================================================================
# start/stop/restart 命令
# ============================================================================

cmd_start() {
    log_info "启动服务..."
    cd_project
    dc up -d
    log_info "服务已启动"
}

cmd_stop() {
    log_info "停止服务..."
    cd_project
    dc down
    log_info "服务已停止"
}

cmd_restart() {
    log_info "重启服务..."
    cmd_stop
    cmd_start
}

# ============================================================================
# status 命令
# ============================================================================

cmd_status() {
    cd_project

    local version
    version=$(get_version)

    echo "╭──────────────────────────────────────────╮"
    echo "│ cyber-pulse Status                        │"
    echo "├──────────────────────────────────────────┤"
    printf "│ %-11s %s\n" "Version:" "$version"
    echo "├──────────────────────────────────────────┤"
    echo "│ Service     Status                       │"
    echo "│ ─────────────────────────────────────────│"

    # 检查各服务状态
    for service in postgres redis api worker scheduler; do
        local status
        status=$(dc ps --status running "$service" 2>/dev/null | grep -c "running" || echo "0")
        if [ "$status" -gt 0 ]; then
            printf "│ %-12s ${GREEN}● running${NC}\n" "$service"
        else
            printf "│ %-12s ${RED}○ stopped${NC}\n" "$service"
        fi
    done

    echo "╰──────────────────────────────────────────╯"

    # 健康检查
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "API 健康检查: ${GREEN}通过${NC}"
    else
        echo -e "API 健康检查: ${YELLOW}未响应${NC}"
    fi
}

# ============================================================================
# logs 命令
# ============================================================================

cmd_logs() {
    local service="$1"
    cd_project
    dc logs -f --tail 100 ${service:-}
}

# ============================================================================
# config 命令
# ============================================================================

cmd_config_show() {
    local reveal="$1"

    if [ ! -f "$ENV_FILE" ]; then
        log_error "配置文件不存在: $ENV_FILE"
        exit 1
    fi

    echo "配置文件: $ENV_FILE"
    echo ""

    if [ "$reveal" == "--reveal" ]; then
        cat "$ENV_FILE"
    else
        # 隐藏敏感信息
        cat "$ENV_FILE" | sed -E 's/(PASSWORD|SECRET_KEY|KEY)=.*/\1=*****/'
    fi
}

# ============================================================================
# 命令分发
# ============================================================================

main() {
    local command="${1:-help}"
    shift || true

    case "$command" in
        deploy)
            cmd_deploy "$@"
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
            cmd_logs "$@"
            ;;
        config)
            local subcmd="${1:-show}"
            shift || true
            case "$subcmd" in
                show)
                    cmd_config_show "$@"
                    ;;
                *)
                    log_error "未知 config 子命令: $subcmd"
                    exit 1
                    ;;
            esac
            ;;
        upgrade|check-update|backup|restore|uninstall)
            log_error "命令 '$command' 尚未实现"
            exit 1
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
```

- [ ] **Step 2: 设置执行权限**

Run: `chmod +x scripts/cyber-pulse.sh`

- [ ] **Step 3: 测试帮助命令**

Run: `./scripts/cyber-pulse.sh help`

Expected: 显示帮助信息

- [ ] **Step 4: 测试 status 命令（服务未运行）**

Run: `./scripts/cyber-pulse.sh status`

Expected: 显示各服务状态为 stopped

- [ ] **Step 5: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add unified entry script cyber-pulse.sh

Add cyber-pulse.sh as the single entry point for all deployment operations:

Commands:
- deploy: One-click deployment with dependency check and config generation
- start/stop/restart: Service management
- status: Show service status and health check
- logs: View container logs
- config show: View configuration (with --reveal for secrets)

Features:
- Color-coded output
- Multi-environment support via --env flag
- Secure configuration generation
- Version tracking via .version file

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 更新 .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: 更新配置模板**

```bash
# cyber-pulse 配置文件模板
# 复制此文件为 .env 并修改配置
# 部署时会自动生成安全配置，无需手动填写

# 数据库配置
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=changeme

# 安全密钥 (JWT 签名)
SECRET_KEY=changeme

# 服务连接配置 (容器内部网络，无需修改)
DATABASE_URL=postgresql://cyberpulse:changeme@postgres:5432/cyberpulse
REDIS_URL=redis://redis:6379/0
DRAMATIQ_BROKER_URL=redis://redis:6379/1

# API 配置
API_HOST=0.0.0.0
API_PORT=8000

# 日志配置
LOG_LEVEL=INFO
```

- [ ] **Step 2: 提交**

```bash
git add .env.example
git commit -m "$(cat <<'EOF'
docs: update .env.example with clear documentation

Update config template to reflect auto-generated values during deployment.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `./scripts/cyber-pulse.sh help` 显示帮助信息
- [ ] `./scripts/cyber-pulse.sh deploy` 成功部署服务
- [ ] `./scripts/cyber-pulse.sh status` 显示服务状态
- [ ] `./scripts/cyber-pulse.sh stop` 停止服务
- [ ] `./scripts/cyber-pulse.sh start` 启动服务
- [ ] `./scripts/cyber-pulse.sh logs api` 显示 API 日志
- [ ] `./scripts/cyber-pulse.sh config show` 显示配置（隐藏敏感信息）
- [ ] `./scripts/cyber-pulse.sh config show --reveal` 显示完整配置