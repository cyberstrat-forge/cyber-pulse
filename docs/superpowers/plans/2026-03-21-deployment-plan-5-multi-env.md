# 部署优化计划5：多环境支持

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持开发、测试、生产三种环境的配置分离和部署。

**Architecture:** 使用 Docker Compose 多文件覆盖机制，基础配置在 docker-compose.yml，环境特定配置在 docker-compose.{env}.yml。

**Tech Stack:** Bash, Docker Compose

**依赖:** 计划2 (cyber-pulse.sh 框架)

---

## 文件结构

```
cyber-pulse/
├── deploy/
│   ├── docker-compose.yml       # 基础配置（已存在，需移动）
│   ├── docker-compose.dev.yml   # 新建：开发环境覆盖
│   ├── docker-compose.test.yml  # 新建：测试环境覆盖
│   └── docker-compose.prod.yml  # 新建：生产环境覆盖
└── scripts/
    └── cyber-pulse.sh           # 修改：增强环境支持
```

---

## Task 1: 创建环境覆盖配置文件

**Files:**
- Create: `deploy/docker-compose.dev.yml`
- Create: `deploy/docker-compose.test.yml`
- Create: `deploy/docker-compose.prod.yml`

- [ ] **Step 1: 创建开发环境覆盖配置**

```yaml
# docker-compose.dev.yml
# 开发环境覆盖配置
#
# 特点：
# - 挂载本地代码支持热重载
# - 详细日志输出
# - 单进程模式

services:
  api:
    volumes:
      - ../src:/app/src:ro
    environment:
      - LOG_LEVEL=DEBUG
      - RELOAD=true
    command: uvicorn cyberpulse.api.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"

  worker:
    environment:
      - LOG_LEVEL=DEBUG
    command: dramatiq cyberpulse.tasks --processes 1 --threads 2 --watch /app/src

  scheduler:
    environment:
      - LOG_LEVEL=DEBUG

  postgres:
    ports:
      - "5432:5432"

  redis:
    ports:
      - "6379:6379"
```

- [ ] **Step 2: 创建测试环境覆盖配置**

```yaml
# docker-compose.test.yml
# 测试环境覆盖配置
#
# 特点：
# - 中等资源限制
# - 标准日志级别
# - 端口对外暴露（便于测试）

services:
  api:
    environment:
      - LOG_LEVEL=INFO
      - TESTING=true
    command: uvicorn cyberpulse.api.main:app --host 0.0.0.0 --port 8000 --workers 2
    deploy:
      resources:
        limits:
          memory: 512M
    ports:
      - "8000:8000"

  worker:
    environment:
      - LOG_LEVEL=INFO
    command: dramatiq cyberpulse.tasks --processes 1 --threads 4
    deploy:
      resources:
        limits:
          memory: 512M

  scheduler:
    environment:
      - LOG_LEVEL=INFO

  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
    ports:
      - "5432:5432"

  redis:
    deploy:
      resources:
        limits:
          memory: 256M
    ports:
      - "6379:6379"
```

- [ ] **Step 3: 创建生产环境覆盖配置**

```yaml
# docker-compose.prod.yml
# 生产环境覆盖配置
#
# 特点：
# - 多进程、多线程
# - 资源限制
# - 最小日志（WARN）
# - 端口不对外暴露（仅 API）

services:
  api:
    environment:
      - LOG_LEVEL=WARNING
    command: uvicorn cyberpulse.api.main:app --host 0.0.0.0 --port 8000 --workers 4
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  worker:
    environment:
      - LOG_LEVEL=WARNING
    command: dramatiq cyberpulse.tasks --processes 2 --threads 4
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 256M
    restart: unless-stopped

  scheduler:
    environment:
      - LOG_LEVEL=WARNING
    deploy:
      resources:
        limits:
          memory: 256M
    restart: unless-stopped

  postgres:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cyberpulse"]
      interval: 30s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 128M
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 5
    restart: unless-stopped
```

- [ ] **Step 4: 提交环境配置文件**

```bash
git add deploy/docker-compose.dev.yml deploy/docker-compose.test.yml deploy/docker-compose.prod.yml
git commit -m "$(cat <<'EOF'
feat(deploy): add multi-environment docker-compose overlays

Add environment-specific Docker Compose configurations:

dev environment:
- Source code volume mount for hot reload
- DEBUG log level
- Exposed ports for debugging
- Single process mode

test environment:
- INFO log level
- Moderate resource limits
- Exposed ports for testing
- 2 API workers

prod environment:
- WARNING log level
- Strict resource limits with reservations
- 4 API workers
- Health checks for all services
- Restart policies

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 增强 cyber-pulse.sh 环境支持

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 添加环境变量和配置**

在脚本配置部分添加：

```bash
# 环境配置
DEFAULT_ENV="dev"
CURRENT_ENV=""

# 环境文件映射
declare -A ENV_FILES=(
    ["dev"]="$DEPLOY_DIR/docker-compose.dev.yml"
    ["test"]="$DEPLOY_DIR/docker-compose.test.yml"
    ["prod"]="$DEPLOY_DIR/docker-compose.prod.yml"
)
```

- [ ] **Step 2: 添加环境辅助函数**

在工具函数部分添加：

```bash
# ============================================================================
# 环境管理
# ============================================================================

get_env_compose_args() {
    local env="$1"
    local args="-f $COMPOSE_FILE"

    if [ -n "$env" ] && [ -f "${ENV_FILES[$env]}" ]; then
        args="$args -f ${ENV_FILES[$env]}"
    fi

    echo "$args"
}

get_current_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        grep -E "^ENVIRONMENT=" "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "$DEFAULT_ENV"
    else
        echo "$DEFAULT_ENV"
    fi
}

save_env_to_config() {
    local env="$1"

    if [ -f "$PROJECT_ROOT/.env" ]; then
        # 更新或添加 ENVIRONMENT 变量
        if grep -q "^ENVIRONMENT=" "$PROJECT_ROOT/.env"; then
            sed -i.bak "s/^ENVIRONMENT=.*/ENVIRONMENT=$env/" "$PROJECT_ROOT/.env" && rm -f "$PROJECT_ROOT/.env.bak"
        else
            echo "ENVIRONMENT=$env" >> "$PROJECT_ROOT/.env"
        fi
    fi
}
```

- [ ] **Step 3: 更新 deploy 命令**

替换原有的 `cmd_deploy` 函数：

```bash
# ============================================================================
# deploy 命令
# ============================================================================

cmd_deploy() {
    local env=""

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env)
                env="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    # 默认环境
    env="${env:-$DEFAULT_ENV}"

    # 验证环境
    if [[ ! "$env" =~ ^(dev|test|prod)$ ]]; then
        log_error "无效的环境: $env"
        echo ""
        echo "支持的环境: dev, test, prod"
        exit 1
    fi

    local compose_args
    compose_args=$(get_env_compose_args "$env")

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

    # 3. 保存环境配置
    save_env_to_config "$env"

    # 4. 启动服务
    log_info "启动服务..."
    docker compose $compose_args up -d --build

    # 5. 等待服务就绪
    log_info "等待服务就绪..."
    sleep 10

    # 6. 数据库迁移
    log_info "执行数据库迁移..."
    docker compose $compose_args exec -T api alembic upgrade head 2>/dev/null || true

    # 7. 保存版本
    save_version

    # 8. 显示完成信息
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
    echo "│ 配置文件: .env                                              │"
    echo "│ 查看状态: ./scripts/cyber-pulse.sh status                   │"
    echo "╰─────────────────────────────────────────────────────────────╯"
}
```

- [ ] **Step 4: 更新 start/stop/restart 命令**

替换原有的 `cmd_start`、`cmd_stop`、`cmd_restart` 函数：

```bash
# ============================================================================
# start/stop/restart 命令
# ============================================================================

cmd_start() {
    local env=$(get_current_env)
    local compose_args=$(get_env_compose_args "$env")

    log_info "启动服务 (环境: $env)..."
    cd_project
    docker compose $compose_args up -d
    log_info "服务已启动"
}

cmd_stop() {
    local env=$(get_current_env)
    local compose_args=$(get_env_compose_args "$env")

    log_info "停止服务..."
    cd_project
    docker compose $compose_args down
    log_info "服务已停止"
}

cmd_restart() {
    log_info "重启服务..."
    cmd_stop
    cmd_start
}
```

- [ ] **Step 5: 更新 status 命令**

替换原有的 `cmd_status` 函数：

```bash
# ============================================================================
# status 命令
# ============================================================================

cmd_status() {
    cd_project

    local version
    local env

    version=$(get_version)
    env=$(get_current_env)

    echo "╭──────────────────────────────────────────╮"
    echo "│ cyber-pulse Status                        │"
    echo "├──────────────────────────────────────────┤"
    printf "│ %-11s %s\\n" "Version:" "$version"
    printf "│ %-11s %s\\n" "Environment:" "$env"
    echo "├──────────────────────────────────────────┤"
    echo "│ Service     Status                       │"
    echo "│ ─────────────────────────────────────────│"

    # 检查各服务状态
    for service in postgres redis api worker scheduler; do
        local status
        status=$(docker compose -f "$COMPOSE_FILE" ps --status running "$service" 2>/dev/null | grep -c "running" || echo "0")
        if [ "$status" -gt 0 ]; then
            printf "│ %-12s ${GREEN}● running${NC}\\n" "$service"
        else
            printf "│ %-12s ${RED}○ stopped${NC}\\n" "$service"
        fi
    done

    echo "╰──────────────────────────────────────────╯"

    # 健康检查
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "API 健康检查: ${GREEN}通过${NC}"
    else
        echo -e "API 健康检查: ${YELLOW}未响应${NC}"
    fi

    # 检查更新
    local latest
    latest=$("$DEPLOY_DIR/upgrade/check-update.sh" 2>/dev/null | grep "最新版本" | awk '{print $2}' | tr -d '\033[0m' || echo "")

    if [ -n "$latest" ] && [ "$latest" != "$version" ]; then
        echo -e "更新提醒: ${YELLOW}有新版本 $latest 可用${NC}"
        echo "  运行 ./scripts/cyber-pulse.sh upgrade 升级"
    fi
}
```

- [ ] **Step 6: 更新 logs 命令**

替换原有的 `cmd_logs` 函数：

```bash
# ============================================================================
# logs 命令
# ============================================================================

cmd_logs() {
    local service="$1"
    local env=$(get_current_env)
    local compose_args=$(get_env_compose_args "$env")

    cd_project
    docker compose $compose_args logs -f --tail 100 ${service:-}
}
```

- [ ] **Step 7: 测试多环境部署**

Run: `./scripts/cyber-pulse.sh deploy --env dev`

Expected: 使用开发环境配置部署

- [ ] **Step 8: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(deploy): enhance multi-environment support

Enhance cyber-pulse.sh with full environment support:

- --env flag for deploy command (dev/test/prod)
- Environment persistence in .env file
- Environment-aware start/stop/restart/status/logs
- get_env_compose_args() for compose file overlay
- status shows current environment and update reminder

Environment configuration:
- dev: Development with hot reload and debug logs
- test: Testing with moderate resources
- prod: Production with strict limits and health checks

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 更新帮助信息

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 更新 show_help 函数**

```bash
show_help() {
    cat << EOF
cyber-pulse 部署管理脚本

用法:
  ./scripts/cyber-pulse.sh <command> [options]

命令:
  deploy [--env ENV]      一键部署 (默认 dev 环境)
                          ENV: dev, test, prod

  start                   启动服务
  stop                    停止服务
  restart                 重启服务
  status                  查看状态 (含健康检查和更新提醒)
  logs [SERVICE]          查看日志

  upgrade [VERSION]       升级到指定版本 (默认最新)
  check-update            检查是否有新版本

  backup                  备份数据和配置
  restore <file>          从备份恢复

  config show [--reveal]  查看配置 (--reveal 显示敏感信息)
  uninstall               完全卸载
  help                    显示此帮助

环境说明:
  dev   开发环境，支持热重载，详细日志，端口暴露
  test  测试环境，中等资源，标准日志
  prod  生产环境，多进程，资源限制，健康检查

示例:
  ./scripts/cyber-pulse.sh deploy
  ./scripts/cyber-pulse.sh deploy --env prod
  ./scripts/cyber-pulse.sh logs api
  ./scripts/cyber-pulse.sh status
  ./scripts/cyber-pulse.sh backup

EOF
}
```

- [ ] **Step 2: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
docs: update help with environment documentation

Add environment documentation to help output:
- --env flag usage and values
- Environment descriptions (dev/test/prod)
- Updated examples

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `./scripts/cyber-pulse.sh deploy --env dev` 使用开发配置部署
- [ ] `./scripts/cyber-pulse.sh deploy --env test` 使用测试配置部署
- [ ] `./scripts/cyber-pulse.sh deploy --env prod` 使用生产配置部署
- [ ] `./scripts/cyber-pulse.sh status` 显示当前环境
- [ ] 无效环境参数时报错退出
- [ ] 帮助信息包含环境说明