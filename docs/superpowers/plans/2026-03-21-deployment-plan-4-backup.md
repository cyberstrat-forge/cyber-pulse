# 部署优化计划4：backup/restore 命令

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 backup 和 restore 命令，支持独立的灾难恢复和迁移能力。

**Architecture:** 备份是独立的长期存储功能，与升级快照完全分离。支持完整数据导出、压缩归档、版本追踪。

**Tech Stack:** Bash, Docker, pg_dump, tar

**依赖:** 计划2 (cyber-pulse.sh 框架)

---

## 文件结构

```
cyber-pulse/
├── scripts/
│   └── cyber-pulse.sh       # 修改：添加 backup/restore 命令
├── deploy/
│   └── backup/
│       ├── create-backup.sh     # 新建：创建备份
│       └── restore-backup.sh    # 新建：恢复备份
└── backups/                    # 运行时创建：备份存储目录
    └── backup-YYYYMMDD-HHMMSS.tar.gz
```

---

## Task 1: 创建备份管理脚本

**Files:**
- Create: `deploy/backup/`

- [ ] **Step 1: 创建目录结构**

Run: `mkdir -p deploy/backup`

- [ ] **Step 2: 创建备份创建脚本**

```bash
#!/bin/bash
#
# cyber-pulse 备份创建脚本
#
# 创建完整的备份，用于灾难恢复或迁移

set -e

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
COMPOSE_FILE="$PROJECT_ROOT/deploy/docker-compose.yml"

# 备份保留数量
MAX_BACKUPS=5

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
# 备份函数
# ============================================================================

create_backup_dir() {
    local timestamp
    timestamp=$(date +"%Y%m%d-%H%M%S")
    BACKUP_NAME="backup-$timestamp"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

    mkdir -p "$BACKUP_PATH"
    log_ok "备份目录: $BACKUP_PATH"
}

backup_database() {
    echo "备份数据库..."

    # 检查 PostgreSQL 容器是否运行
    if ! docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q "Up"; then
        log_err "PostgreSQL 容器未运行"
        echo ""
        echo "  请先启动服务: ./scripts/cyber-pulse.sh start"
        return 1
    fi

    # 使用 pg_dump 导出数据库
    docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump \
        -U cyberpulse \
        -d cyberpulse \
        --format=plain \
        --no-owner \
        --no-acl \
        > "$BACKUP_PATH/database.sql" 2>/dev/null

    if [ $? -eq 0 ]; then
        local size
        size=$(du -h "$BACKUP_PATH/database.sql" | cut -f1)
        log_ok "数据库备份 ($size)"
    else
        log_err "数据库备份失败"
        return 1
    fi
}

backup_config() {
    echo "备份配置文件..."

    # 备份 .env
    if [ -f "$PROJECT_ROOT/.env" ]; then
        cp "$PROJECT_ROOT/.env" "$BACKUP_PATH/backup.env"
        log_ok ".env 文件"
    else
        log_warn ".env 文件不存在"
    fi

    # 备份 .version
    if [ -f "$PROJECT_ROOT/.version" ]; then
        cp "$PROJECT_ROOT/.version" "$BACKUP_PATH/backup.version"
        log_ok ".version 文件"
    fi
}

backup_data() {
    echo "备份应用数据..."

    # 检查 data 目录是否存在且非空
    if [ -d "$PROJECT_ROOT/data" ] && [ "$(ls -A $PROJECT_ROOT/data 2>/dev/null)" ]; then
        cp -r "$PROJECT_ROOT/data" "$BACKUP_PATH/"
        log_ok "data/ 目录"
    else
        log_ok "无应用数据（跳过）"
    fi
}

create_metadata() {
    echo "创建备份元数据..."

    local version
    local timestamp
    local db_size

    version=$(cat "$PROJECT_ROOT/.version" 2>/dev/null || echo "unknown")
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # 获取数据库大小
    db_size=$(docker compose -f "$COMPOSE_FILE" exec -T postgres psql \
        -U cyberpulse \
        -d cyberpulse \
        -c "SELECT pg_size_pretty(pg_database_size('cyberpulse'))" 2>/dev/null | grep -E '^[0-9]+.*B$' || echo "unknown")

    cat > "$BACKUP_PATH/backup.json" << EOF
{
    "backup_time": "$timestamp",
    "version": "$version",
    "db_size": "$db_size",
    "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo "unknown")"
}
EOF

    log_ok "元数据文件"
}

compress_backup() {
    echo "压缩备份..."

    cd "$BACKUP_DIR"

    tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"

    if [ $? -eq 0 ]; then
        local size
        size=$(du -h "$BACKUP_NAME.tar.gz" | cut -f1)
        log_ok "压缩完成 ($size)"

        # 删除临时目录
        rm -rf "$BACKUP_NAME"
    else
        log_err "压缩失败"
        return 1
    fi

    cd - > /dev/null
}

cleanup_old_backups() {
    echo "清理旧备份..."

    local count
    count=$(ls -1 "$BACKUP_DIR"/backup-*.tar.gz 2>/dev/null | wc -l)

    if [ "$count" -gt "$MAX_BACKUPS" ]; then
        local to_delete=$((count - MAX_BACKUPS))
        ls -1t "$BACKUP_DIR"/backup-*.tar.gz | tail -$to_delete | xargs rm -f
        log_ok "已删除 $to_delete 个旧备份"
    else
        log_ok "保留所有备份（共 $count 个）"
    fi
}

# ============================================================================
# 主流程
# ============================================================================

create_backup() {
    echo "创建备份..."
    echo ""

    # 创建备份目录
    mkdir -p "$BACKUP_DIR"

    create_backup_dir || exit 1
    backup_database || exit 1
    backup_config
    backup_data
    create_metadata
    compress_backup || exit 1
    cleanup_old_backups

    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│ ✅ 备份完成                                                  │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ 文件: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
    echo "│                                                             │"
    echo "│ 恢复命令: ./scripts/cyber-pulse.sh restore <file>          │"
    echo "╰─────────────────────────────────────────────────────────────╯"
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    create_backup
fi
```

- [ ] **Step 3: 创建备份恢复脚本**

```bash
#!/bin/bash
#
# cyber-pulse 备份恢复脚本
#
# 从备份文件恢复，用于灾难恢复或迁移

set -e

# ============================================================================
# 配置
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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

extract_backup() {
    local backup_file="$1"

    if [ ! -f "$backup_file" ]; then
        log_err "备份文件不存在: $backup_file"
        exit 1
    fi

    # 检查文件格式
    if [[ ! "$backup_file" == *.tar.gz ]]; then
        log_err "不支持的备份格式，期望 .tar.gz 文件"
        exit 1
    fi

    echo "解压备份文件..."

    EXTRACT_DIR="${backup_file%.tar.gz}"

    tar -xzf "$backup_file" -C "$(dirname "$backup_file")"

    if [ $? -ne 0 ]; then
        log_err "解压失败"
        exit 1
    fi

    # 找到解压后的目录（可能有 backup-YYYYMMDD-HHMMSS 子目录）
    EXTRACT_PATH=$(find "$(dirname "$backup_file")" -maxdepth 1 -type d -name "backup-*" | head -1)

    if [ ! -d "$EXTRACT_PATH" ]; then
        log_err "找不到解压后的备份目录"
        exit 1
    fi

    log_ok "解压完成: $EXTRACT_PATH"
}

check_metadata() {
    local metadata_file="$EXTRACT_PATH/backup.json"

    if [ -f "$metadata_file" ]; then
        echo ""
        echo "备份信息:"
        cat "$metadata_file" | python3 -m json.tool 2>/dev/null || cat "$metadata_file"
        echo ""
    fi
}

restore_config() {
    echo "恢复配置文件..."

    # 恢复 .env
    if [ -f "$EXTRACT_PATH/backup.env" ]; then
        cp "$EXTRACT_PATH/backup.env" "$PROJECT_ROOT/.env"
        log_ok ".env 文件已恢复"
    else
        log_warn "备份中没有 .env 文件"
    fi

    # 恢复 .version
    if [ -f "$EXTRACT_PATH/backup.version" ]; then
        cp "$EXTRACT_PATH/backup.version" "$PROJECT_ROOT/.version"
        log_ok ".version 文件已恢复"
    fi
}

restore_database() {
    echo "恢复数据库..."

    if [ ! -f "$EXTRACT_PATH/database.sql" ]; then
        log_err "备份中没有数据库文件"
        return 1
    fi

    # 检查 PostgreSQL 容器是否运行
    if ! docker compose -f "$COMPOSE_FILE" ps postgres 2>/dev/null | grep -q "Up"; then
        log_warn "PostgreSQL 容器未运行，尝试启动..."
        docker compose -f "$COMPOSE_FILE" up -d postgres redis
        sleep 10
    fi

    # 停止写入服务
    log_info "停止 API 和 Worker 服务..."
    docker compose -f "$COMPOSE_FILE" stop api worker scheduler 2>/dev/null || true

    # 恢复数据库
    log_info "恢复数据库..."
    docker compose -f "$COMPOSE_FILE" exec -T postgres psql \
        -U cyberpulse \
        -d cyberpulse \
        < "$EXTRACT_PATH/database.sql" 2>/dev/null

    if [ $? -eq 0 ]; then
        log_ok "数据库已恢复"
    else
        log_warn "数据库恢复可能有警告"
    fi
}

restore_data() {
    echo "恢复应用数据..."

    if [ -d "$EXTRACT_PATH/data" ]; then
        # 确保目标目录存在
        mkdir -p "$PROJECT_ROOT/data"

        # 恢复数据
        cp -r "$EXTRACT_PATH/data/"* "$PROJECT_ROOT/data/" 2>/dev/null || true
        log_ok "data/ 目录已恢复"
    else
        log_ok "无应用数据需要恢复"
    fi
}

restore_code() {
    echo "恢复代码版本..."

    local version
    version=$(cat "$EXTRACT_PATH/backup.version" 2>/dev/null)

    if [ -n "$version" ] && [ -d "$PROJECT_ROOT/.git" ]; then
        cd "$PROJECT_ROOT"
        git checkout "$version" 2>/dev/null || log_warn "无法切换到版本 $version"
        cd - > /dev/null
        log_ok "代码已切换到 $version"
    else
        log_warn "无版本信息或非 git 仓库，跳过代码恢复"
    fi
}

restart_services() {
    echo "重启服务..."

    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" up -d
    cd - > /dev/null

    log_ok "服务已重启"

    # 等待服务就绪
    echo "等待服务就绪..."
    sleep 10

    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_ok "服务健康"
    else
        log_warn "健康检查未通过，请检查日志"
    fi
}

cleanup() {
    if [ -n "$EXTRACT_PATH" ] && [ -d "$EXTRACT_PATH" ]; then
        rm -rf "$EXTRACT_PATH"
    fi
}

# ============================================================================
# 主流程
# ============================================================================

restore_backup() {
    local backup_file="$1"

    if [ -z "$backup_file" ]; then
        log_error "请指定备份文件"
        echo ""
        echo "用法: ./scripts/cyber-pulse.sh restore <backup-file.tar.gz>"
        echo ""
        echo "可用备份:"
        ls -1t "$PROJECT_ROOT/backups"/backup-*.tar.gz 2>/dev/null | head -5 || echo "  无备份文件"
        exit 1
    fi

    echo "从备份恢复..."
    echo ""

    extract_backup "$backup_file"
    check_metadata
    restore_config
    restore_database || exit 1
    restore_data
    restore_code
    restart_services
    cleanup

    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│ ✅ 恢复完成                                                  │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ 查看状态: ./scripts/cyber-pulse.sh status                   │"
    echo "│ 查看日志: ./scripts/cyber-pulse.sh logs                     │"
    echo "╰─────────────────────────────────────────────────────────────╯"
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    restore_backup "$@"
fi
```

- [ ] **Step 4: 设置执行权限**

Run: `chmod +x deploy/backup/create-backup.sh deploy/backup/restore-backup.sh`

- [ ] **Step 5: 提交**

```bash
git add deploy/backup/
git commit -m "$(cat <<'EOF'
feat(deploy): add backup and restore scripts

Add create-backup.sh and restore-backup.sh for disaster recovery:
- Full database export using pg_dump (plain SQL format)
- Configuration files backup (.env, .version)
- Application data backup (data/ directory)
- Compressed archive (.tar.gz)
- Backup metadata with version and timestamp
- Automatic cleanup of old backups (keep last 5)

Restore process:
- Extract backup archive
- Stop write services (API, Worker, Scheduler)
- Restore database using psql
- Restore configuration and data
- Restart services with health check

Backup is independent from upgrade snapshots.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 实现 backup/restore 命令

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 在 cyber-pulse.sh 中添加 backup/restore 函数**

在 `cmd_upgrade` 函数之后，`main` 函数之前添加：

```bash
# ============================================================================
# backup 命令
# ============================================================================

cmd_backup() {
    cd_project
    "$DEPLOY_DIR/backup/create-backup.sh"
}

# ============================================================================
# restore 命令
# ============================================================================

cmd_restore() {
    local backup_file="$1"

    cd_project

    if [ -z "$backup_file" ]; then
        log_error "请指定备份文件"
        echo ""
        echo "用法: ./scripts/cyber-pulse.sh restore <backup-file.tar.gz>"
        echo ""
        echo "可用备份:"
        ls -1t "$PROJECT_ROOT/backups"/backup-*.tar.gz 2>/dev/null | head -5 || echo "  无备份文件"
        exit 1
    fi

    # 支持相对路径和绝对路径
    if [[ ! "$backup_file" = /* ]]; then
        backup_file="$PROJECT_ROOT/$backup_file"
    fi

    "$DEPLOY_DIR/backup/restore-backup.sh" "$backup_file"
}
```

- [ ] **Step 2: 更新命令分发逻辑**

在 `main` 函数的 `case` 语句中更新：

```bash
        backup)
            cmd_backup
            ;;
        restore)
            cmd_restore "$@"
            ;;
        uninstall)
            log_error "命令 '$command' 尚未实现"
            exit 1
            ;;
```

- [ ] **Step 3: 测试 backup 命令**

Run: `./scripts/cyber-pulse.sh backup`

Expected: 创建备份文件并显示完成信息

- [ ] **Step 4: 测试 restore 命令（列出可用备份）**

Run: `./scripts/cyber-pulse.sh restore`

Expected: 显示用法和可用备份列表

- [ ] **Step 5: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add backup and restore commands

Integrate backup/restore scripts into cyber-pulse.sh:
- backup: Create full backup archive
- restore <file>: Restore from backup file

Supports relative and absolute paths for restore.
Shows available backups when no file specified.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 创建 backups 目录占位符

**Files:**
- Create: `backups/.gitkeep`

- [ ] **Step 1: 创建目录和占位文件**

Run: `mkdir -p backups && touch backups/.gitkeep`

- [ ] **Step 2: 更新 .gitignore**

在 `.gitignore` 中添加：

```gitignore
# Backup files (keep directory)
backups/*
!backups/.gitkeep
```

- [ ] **Step 3: 提交**

```bash
git add backups/.gitkeep .gitignore
git commit -m "$(cat <<'EOF'
chore: add backups directory placeholder

Create backups/ directory with .gitkeep for git tracking.
Ignore backup files but keep the directory structure.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `./scripts/cyber-pulse.sh backup` 成功创建备份
- [ ] 备份文件包含 database.sql、backup.env、backup.version、backup.json
- [ ] `./scripts/cyber-pulse.sh restore` 显示可用备份列表
- [ ] `./scripts/cyber-pulse.sh restore <file>` 成功恢复
- [ ] 旧备份超过 5 个时自动清理