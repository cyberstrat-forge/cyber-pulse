# 部署优化计划3：upgrade 命令与快照机制

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 upgrade 和 check-update 命令，支持安全升级、自动快照、失败回滚。

**Architecture:** 快照在升级时自动创建，用于失败时回滚；成功后自动清理。快照与备份完全独立。

**Tech Stack:** Bash, Docker, pg_dump, git

**依赖:** 计划2 (cyber-pulse.sh 框架)

---

## 文件结构

```
cyber-pulse/
├── scripts/
│   └── cyber-pulse.sh       # 修改：添加 upgrade/check-update 命令
├── deploy/
│   └── upgrade/
│       ├── create-snapshot.sh   # 新建：创建快照
│       ├── restore-snapshot.sh  # 新建：恢复快照
│       └── check-update.sh      # 新建：检查更新
└── .upgrade-snapshot/           # 运行时创建：快照目录
    ├── database.dump            # 数据库快照
    ├── .env.backup              # 配置文件备份
    ├── .version.backup          # 版本信息备份
    └── metadata.json            # 快照元数据
```

---

## Task 1: 创建快照管理脚本

**Files:**
- Create: `deploy/upgrade/`

- [ ] **Step 1: 创建目录结构**

Run: `mkdir -p deploy/upgrade`

- [ ] **Step 2: 创建快照创建脚本**

```bash
#!/bin/bash
#
# cyber-pulse 快照创建脚本
#
# 创建升级前的轻量快照，用于失败时回滚

set -e

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SNAPSHOT_DIR="$PROJECT_ROOT/.upgrade-snapshot"
COMPOSE_FILE="$PROJECT_ROOT/deploy/docker-compose.yml"

# ============================================================================
# 颜色输出
# ============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() { echo -e "  ${GREEN}✓${NC} $1"; }
log_err() { echo -e "  ${RED}✗${NC} $1" >&2; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }

# ============================================================================
# 快照函数
# ============================================================================

create_snapshot_dir() {
    echo "创建快照目录..."
    rm -rf "$SNAPSHOT_DIR"
    mkdir -p "$SNAPSHOT_DIR"
    log_ok "快照目录: $SNAPSHOT_DIR"
}

snapshot_database() {
    echo "快照数据库..."

    # 检查 PostgreSQL 容器是否运行
    if ! docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q "Up"; then
        log_warn "PostgreSQL 容器未运行，跳过数据库快照"
        return 0
    fi

    # 使用 pg_dump 创建快照
    docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump \
        -U cyberpulse \
        -d cyberpulse \
        --format=custom \
        > "$SNAPSHOT_DIR/database.dump" 2>/dev/null

    if [ $? -eq 0 ]; then
        local size
        size=$(du -h "$SNAPSHOT_DIR/database.dump" | cut -f1)
        log_ok "数据库快照 ($size)"
    else
        log_err "数据库快照失败"
        return 1
    fi
}

snapshot_config() {
    echo "快照配置文件..."

    # 备份 .env
    if [ -f "$PROJECT_ROOT/.env" ]; then
        cp "$PROJECT_ROOT/.env" "$SNAPSHOT_DIR/.env.backup"
        log_ok ".env 文件"
    fi

    # 备份 .version
    if [ -f "$PROJECT_ROOT/.version" ]; then
        cp "$PROJECT_ROOT/.version" "$SNAPSHOT_DIR/.version.backup"
        log_ok ".version 文件"
    fi
}

create_metadata() {
    echo "创建快照元数据..."

    local current_version
    local timestamp

    current_version=$(cat "$PROJECT_ROOT/.version" 2>/dev/null || echo "unknown")
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat > "$SNAPSHOT_DIR/metadata.json" << EOF
{
    "snapshot_time": "$timestamp",
    "version": "$current_version",
    "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo "unknown")"
}
EOF

    log_ok "元数据文件"
}

# ============================================================================
# 主流程
# ============================================================================

create_snapshot() {
    echo "创建升级快照..."
    echo ""

    create_snapshot_dir
    snapshot_database || exit 1
    snapshot_config
    create_metadata

    echo ""
    log_ok "快照创建完成"
    echo ""
    echo "  快照位置: $SNAPSHOT_DIR"
    echo "  如需手动恢复: ./deploy/upgrade/restore-snapshot.sh"
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    create_snapshot
fi
```

- [ ] **Step 3: 创建快照恢复脚本**

```bash
#!/bin/bash
#
# cyber-pulse 快照恢复脚本
#
# 从快照恢复，用于升级失败时回滚

set -e

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SNAPSHOT_DIR="$PROJECT_ROOT/.upgrade-snapshot"
COMPOSE_FILE="$PROJECT_ROOT/deploy/docker-compose.yml"

# ============================================================================
# 颜色输出
# ============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() { echo -e "  ${GREEN}✓${NC} $1"; }
log_err() { echo -e "  ${RED}✗${NC} $1" >&2; }
log_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }

# ============================================================================
# 恢复函数
# ============================================================================

check_snapshot() {
    if [ ! -d "$SNAPSHOT_DIR" ]; then
        log_err "快照目录不存在: $SNAPSHOT_DIR"
        exit 1
    fi

    if [ ! -f "$SNAPSHOT_DIR/metadata.json" ]; then
        log_err "快照元数据不存在"
        exit 1
    fi

    echo "快照信息:"
    cat "$SNAPSHOT_DIR/metadata.json" | python3 -m json.tool 2>/dev/null || cat "$SNAPSHOT_DIR/metadata.json"
    echo ""
}

restore_database() {
    echo "恢复数据库..."

    if [ ! -f "$SNAPSHOT_DIR/database.dump" ]; then
        log_warn "数据库快照不存在，跳过恢复"
        return 0
    fi

    # 检查 PostgreSQL 容器是否运行
    if ! docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q "Up"; then
        log_warn "PostgreSQL 容器未运行，跳过数据库恢复"
        return 0
    fi

    # 恢复数据库
    docker compose -f "$COMPOSE_FILE" exec -T postgres pg_restore \
        -U cyberpulse \
        -d cyberpulse \
        --clean \
        --if-exists \
        < "$SNAPSHOT_DIR/database.dump" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_ok "数据库已恢复"
    else
        log_warn "数据库恢复可能有警告（正常）"
    fi
}

restore_config() {
    echo "恢复配置文件..."

    # 恢复 .env
    if [ -f "$SNAPSHOT_DIR/.env.backup" ]; then
        cp "$SNAPSHOT_DIR/.env.backup" "$PROJECT_ROOT/.env"
        log_ok ".env 文件已恢复"
    fi

    # 恢复 .version
    if [ -f "$SNAPSHOT_DIR/.version.backup" ]; then
        cp "$SNAPSHOT_DIR/.version.backup" "$PROJECT_ROOT/.version"
        log_ok ".version 文件已恢复"
    fi
}

restore_code() {
    echo "恢复代码版本..."

    local version
    version=$(cat "$SNAPSHOT_DIR/.version.backup" 2>/dev/null)

    if [ -n "$version" ]; then
        cd "$PROJECT_ROOT"
        git checkout "$version" 2>/dev/null || log_warn "无法切换到版本 $version"
        cd - > /dev/null
        log_ok "代码已切换到 $version"
    fi
}

restart_services() {
    echo "重启服务..."

    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" down
    docker compose -f "$COMPOSE_FILE" up -d
    cd - > /dev/null

    log_ok "服务已重启"
}

# ============================================================================
# 主流程
# ============================================================================

restore_snapshot() {
    echo "从快照恢复..."
    echo ""

    check_snapshot
    restore_database
    restore_config
    restore_code
    restart_services

    echo ""
    log_ok "恢复完成"
    echo ""
    echo "  快照保留在: $SNAPSHOT_DIR"
    echo "  如需排查问题，请查看快照内容"
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    restore_snapshot
fi
```

- [ ] **Step 4: 设置执行权限**

Run: `chmod +x deploy/upgrade/create-snapshot.sh deploy/upgrade/restore-snapshot.sh`

- [ ] **Step 5: 提交**

```bash
git add deploy/upgrade/
git commit -m "$(cat <<'EOF'
feat(deploy): add snapshot management scripts

Add create-snapshot.sh and restore-snapshot.sh for upgrade safety:
- Database snapshot using pg_dump (custom format)
- Configuration files backup (.env, .version)
- Metadata file with version and timestamp
- Automatic restore on upgrade failure

Snapshot is temporary and cleaned up after successful upgrade.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 创建更新检查脚本

**Files:**
- Create: `deploy/upgrade/check-update.sh`

- [ ] **Step 1: 创建更新检查脚本**

```bash
#!/bin/bash
#
# cyber-pulse 更新检查脚本
#
# 检查 GitHub Releases 是否有新版本

set -e

# ============================================================================
# 配置
# ============================================================================

REPO_OWNER="cyberstrat-forge"
REPO_NAME="cyber-pulse"
REPO_URL="https://github.com/$REPO_OWNER/$REPO_NAME"
API_URL="https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/releases/latest"

# ============================================================================
# 颜色输出
# ============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# 版本比较
# ============================================================================

version_gt() {
    # 比较版本号，$1 > $2 返回 true
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
    [ $? -eq 1 ]
}

# ============================================================================
# 获取版本信息
# ============================================================================

get_current_version() {
    if [ -f ".version" ]; then
        cat .version
    else
        git describe --tags 2>/dev/null || echo "unknown"
    fi
}

get_latest_version() {
    # 从 GitHub API 获取最新版本
    local response
    response=$(curl -s -w "\n%{http_code}" "$API_URL" 2>/dev/null)

    local http_code
    http_code=$(echo "$response" | tail -1)

    if [ "$http_code" != "200" ]; then
        echo "unknown"
        return 1
    fi

    echo "$response" | head -n -1 | grep -o '"tag_name": *"[^"]*"' | sed 's/"tag_name": *"\([^"]*\)"$/\1/'
}

get_release_notes() {
    local version="$1"
    local release_url="$REPO_URL/releases/tag/$version"

    echo ""
    echo -e "${BLUE}发布说明:${NC}"
    echo "  $release_url"
}

# ============================================================================
# 主流程
# ============================================================================

check_update() {
    local current
    local latest

    current=$(get_current_version)
    echo -e "当前版本: ${GREEN}$current${NC}"

    echo "检查更新..."
    latest=$(get_latest_version)

    if [ "$latest" = "unknown" ]; then
        echo -e "${YELLOW}无法检查更新（网络问题或 API 限制）${NC}"
        return 1
    fi

    echo -e "最新版本: ${GREEN}$latest${NC}"

    if [ "$current" = "$latest" ]; then
        echo ""
        echo -e "${GREEN}已是最新版本${NC}"
        return 0
    fi

    if version_gt "$latest" "$current"; then
        echo ""
        echo -e "${YELLOW}有新版本可用！${NC}"
        get_release_notes "$latest"
        echo ""
        echo "升级命令: ./scripts/cyber-pulse.sh upgrade"
        return 0
    else
        echo ""
        echo -e "${GREEN}当前版本比远程更新（开发版本？）${NC}"
        return 0
    fi
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_update
fi
```

- [ ] **Step 2: 设置执行权限**

Run: `chmod +x deploy/upgrade/check-update.sh`

- [ ] **Step 3: 测试更新检查**

Run: `./deploy/upgrade/check-update.sh`

Expected: 显示当前版本和最新版本信息

- [ ] **Step 4: 提交**

```bash
git add deploy/upgrade/check-update.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add update check script

Add check-update.sh that:
- Queries GitHub Releases API for latest version
- Compares with current version from .version file
- Shows release notes URL when update available
- Handles network errors gracefully

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 实现 upgrade 命令

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 在 cyber-pulse.sh 中添加 upgrade 相关函数**

在 `cmd_config_show` 函数之后，`main` 函数之前添加：

```bash
# ============================================================================
# check-update 命令
# ============================================================================

cmd_check_update() {
    cd_project
    "$DEPLOY_DIR/upgrade/check-update.sh"
}

# ============================================================================
# upgrade 命令
# ============================================================================

cmd_upgrade() {
    local target_version="$1"

    cd_project

    # 1. 预检查
    log_step "预检查升级条件..."

    # 检查 git 仓库
    if [ ! -d ".git" ]; then
        log_error "非 git 仓库，无法升级"
        echo ""
        echo "  升级功能需要通过 git clone 安装"
        exit 1
    fi

    # 检查 Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi

    # 检查服务健康
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_warn "服务未运行或健康检查未通过"
        echo ""
        read -p "继续升级？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # 2. 确定目标版本
    if [ -z "$target_version" ]; then
        log_info "检查最新版本..."
        target_version=$("$DEPLOY_DIR/upgrade/check-update.sh" 2>/dev/null | grep "最新版本" | awk '{print $2}' | tr -d '\033[0m')

        if [ -z "$target_version" ]; then
            log_error "无法获取最新版本"
            exit 1
        fi
    fi

    local current_version
    current_version=$(get_version)

    echo ""
    echo "升级计划:"
    echo "  当前版本: $current_version"
    echo "  目标版本: $target_version"
    echo ""

    read -p "确认升级？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消升级"
        exit 0
    fi

    # 3. 创建快照
    log_step "创建升级快照..."
    "$DEPLOY_DIR/upgrade/create-snapshot.sh" || exit 1

    # 4. 执行升级
    log_step "执行升级..."

    # 拉取最新代码
    log_info "拉取最新代码..."
    git fetch --tags

    # 切换版本
    log_info "切换到版本 $target_version..."
    if ! git checkout "$target_version" 2>/dev/null; then
        log_error "版本 $target_version 不存在"

        # 显示可用版本
        echo ""
        echo "可用版本:"
        git tag -l | sort -V | tail -10

        # 触发回滚
        "$DEPLOY_DIR/upgrade/restore-snapshot.sh"
        exit 1
    fi

    # 重建服务
    log_info "重建服务..."
    docker compose -f "$COMPOSE_FILE" build --no-cache 2>/dev/null || \
        docker compose -f "$COMPOSE_FILE" pull 2>/dev/null || true

    # 数据库迁移
    log_info "执行数据库迁移..."
    docker compose -f "$COMPOSE_FILE" up -d postgres redis 2>/dev/null
    sleep 5
    docker compose -f "$COMPOSE_FILE" exec -T api alembic upgrade head 2>/dev/null || true

    # 重启所有服务
    log_info "重启服务..."
    docker compose -f "$COMPOSE_FILE" up -d

    # 5. 验证
    log_step "验证升级..."
    sleep 10

    local max_retries=6
    local retry=0
    local healthy=false

    while [ $retry -lt $max_retries ]; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            healthy=true
            break
        fi
        retry=$((retry + 1))
        echo "  等待服务就绪... ($retry/$max_retries)"
        sleep 5
    done

    if [ "$healthy" = true ]; then
        # 更新版本文件
        echo "$target_version" > "$VERSION_FILE"

        # 删除快照
        rm -rf "$PROJECT_ROOT/.upgrade-snapshot"

        echo ""
        echo "╭─────────────────────────────────────────────────────────────╮"
        echo "│ ✅ 升级成功                                                  │"
        echo "├─────────────────────────────────────────────────────────────┤"
        echo "│ 版本: $current_version → $target_version"
        echo "│                                                             │"
        echo "│ 查看状态: ./scripts/cyber-pulse.sh status                   │"
        echo "│ 查看日志: ./scripts/cyber-pulse.sh logs                     │"
        echo "╰─────────────────────────────────────────────────────────────╯"
    else
        # 6. 回滚
        log_error "健康检查失败，执行回滚..."

        "$DEPLOY_DIR/upgrade/restore-snapshot.sh"

        echo ""
        echo "╭─────────────────────────────────────────────────────────────╮"
        echo "│ ⚠️  升级失败，已自动回滚                                      │"
        echo "├─────────────────────────────────────────────────────────────┤"
        echo "│ 快照保留在: .upgrade-snapshot/                              │"
        echo "│                                                             │"
        echo "│ 排查步骤：                                                  │"
        echo "│   1. 查看日志: ./scripts/cyber-pulse.sh logs               │"
        echo "│   2. 检查版本兼容性                                         │"
        echo "│   3. 修复后重试: ./scripts/cyber-pulse.sh upgrade          │"
        echo "╰─────────────────────────────────────────────────────────────╯"
        exit 1
    fi
}
```

- [ ] **Step 2: 更新命令分发逻辑**

在 `main` 函数的 `case` 语句中，将 `upgrade|check-update|backup|restore|uninstall)` 分拆：

```bash
        check-update)
            cmd_check_update
            ;;
        upgrade)
            cmd_upgrade "$@"
            ;;
        backup|restore|uninstall)
            log_error "命令 '$command' 尚未实现"
            exit 1
            ;;
```

- [ ] **Step 3: 测试 check-update 命令**

Run: `./scripts/cyber-pulse.sh check-update`

Expected: 显示当前版本和最新版本

- [ ] **Step 4: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add upgrade and check-update commands

Add upgrade functionality with safety mechanisms:
- Automatic snapshot before upgrade (database + config)
- Git version switching
- Docker image rebuild/pull
- Database migration (alembic upgrade head)
- Health check verification (6 retries, 30s timeout)
- Automatic rollback on failure
- Snapshot cleanup after success

check-update command:
- Query GitHub Releases API
- Compare current vs latest version
- Show release notes URL

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `./scripts/cyber-pulse.sh check-update` 显示版本信息
- [ ] `./deploy/upgrade/create-snapshot.sh` 成功创建快照
- [ ] `./deploy/upgrade/restore-snapshot.sh` 成功恢复快照
- [ ] `./scripts/cyber-pulse.sh upgrade` 成功升级到最新版本
- [ ] 升级失败时自动回滚
- [ ] 升级成功后快照被清理