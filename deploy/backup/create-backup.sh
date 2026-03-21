#!/usr/bin/env bash
#
# create-backup.sh - 创建完整备份
#
# 功能:
#   - 创建数据库备份 (plain SQL format)
#   - 备份配置文件 (.env)
#   - 备份版本信息
#   - 备份应用数据（如存在）
#   - 生成备份元数据
#   - 打包压缩备份
#
# 用法:
#   create-backup.sh [--output-dir <dir>] [--no-compress]
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 默认配置
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy"
ENV_FILE="$PROJECT_ROOT/.env"
BACKUPS_DIR="$PROJECT_ROOT/backups"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
DATA_DIR="$PROJECT_ROOT/data"
MAX_BACKUPS=5

# Docker Compose 命令
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 打印函数
print_step() { echo -e "${BLUE}[→]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_info() { echo -e "${BLUE}[i]${NC} $1"; }

# 获取当前版本
get_current_version() {
    local version_file="$PROJECT_ROOT/.version"
    if [[ -f "$version_file" ]]; then
        cat "$version_file"
    else
        cd "$PROJECT_ROOT"
        git describe --tags --always 2>/dev/null || echo "unknown"
    fi
}

# 创建备份目录
create_backup_dir() {
    local backup_name="backup-$(date +%Y%m%d-%H%M%S)"
    local backup_dir="$BACKUPS_DIR/$backup_name"

    mkdir -p "$backup_dir"
    echo "$backup_dir"
}

# 导出数据库 (plain SQL format)
export_database() {
    local backup_dir="$1"
    local sql_file="$backup_dir/database.sql"

    print_step "正在导出数据库 (plain SQL format)..."

    cd "$DEPLOY_DIR"

    # 检查 PostgreSQL 容器是否运行
    if ! $DOCKER_COMPOSE ps postgres 2>/dev/null | grep -q "running"; then
        print_error "PostgreSQL 容器未运行"
        print_warning "请先启动服务: cyber-pulse.sh start"
        return 1
    fi

    # 使用 pg_dump 导出数据库 (plain SQL format)
    if $DOCKER_COMPOSE exec -T postgres pg_dump \
        -U cyberpulse \
        -d cyberpulse \
        --no-owner \
        --no-privileges \
        > "$sql_file" 2>/dev/null; then

        local size
        size=$(du -h "$sql_file" | cut -f1)
        print_success "数据库已导出 ($size)"
    else
        print_error "数据库导出失败"
        return 1
    fi
}

# 备份配置文件
backup_config() {
    local backup_dir="$1"

    print_step "正在备份配置文件..."

    # 备份 .env 文件
    if [[ -f "$ENV_FILE" ]]; then
        cp "$ENV_FILE" "$backup_dir/backup.env"
        print_success ".env 配置已备份"
    else
        print_warning ".env 文件不存在，跳过"
    fi

    # 备份版本信息
    local version_file="$PROJECT_ROOT/.version"
    if [[ -f "$version_file" ]]; then
        cp "$version_file" "$backup_dir/backup.version"
        print_success "版本信息已备份"
    fi
}

# 备份应用数据
backup_data() {
    local backup_dir="$1"

    if [[ -d "$DATA_DIR" ]]; then
        # 检查目录是否非空
        if [[ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]]; then
            print_step "正在备份应用数据..."
            mkdir -p "$backup_dir/data"
            cp -r "$DATA_DIR"/* "$backup_dir/data/" 2>/dev/null || true
            print_success "应用数据已备份"
        fi
    fi
}

# 生成备份元数据
generate_metadata() {
    local backup_dir="$1"
    local current_version="$2"
    local metadata_file="$backup_dir/backup.json"

    print_step "正在生成备份元数据..."

    # 获取数据库大小
    local db_size="unknown"
    if [[ -f "$backup_dir/database.sql" ]]; then
        db_size=$(du -h "$backup_dir/database.sql" | cut -f1)
    fi

    # 获取 git 信息
    local git_branch="unknown"
    local git_commit="unknown"
    cd "$PROJECT_ROOT"
    git_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
    git_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

    # 获取系统信息
    local hostname
    hostname=$(hostname 2>/dev/null || echo "unknown")

    # 生成 JSON 元数据
    cat > "$metadata_file" << EOF
{
    "backup_name": "$(basename "$backup_dir")",
    "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "version": "$current_version",
    "git_branch": "$git_branch",
    "git_commit": "$git_commit",
    "hostname": "$hostname",
    "database_size": "$db_size",
    "backup_type": "full",
    "components": {
        "database": "$([ -f "$backup_dir/database.sql" ] && echo "included" || echo "skipped")",
        "env_config": "$([ -f "$backup_dir/backup.env" ] && echo "included" || echo "skipped")",
        "version_info": "$([ -f "$backup_dir/backup.version" ] && echo "included" || echo "skipped")",
        "app_data": "$([ -d "$backup_dir/data" ] && echo "included" || echo "skipped")"
    }
}
EOF

    print_success "元数据已生成"
}

# 打包压缩备份
compress_backup() {
    local backup_dir="$1"

    print_step "正在打包压缩备份..."

    local backup_name=$(basename "$backup_dir")
    local archive_file="$BACKUPS_DIR/${backup_name}.tar.gz"

    if tar -czf "$archive_file" -C "$BACKUPS_DIR" "$backup_name"; then
        local size
        size=$(du -h "$archive_file" | cut -f1)
        print_success "备份已打包: ${backup_name}.tar.gz ($size)"
        echo "$archive_file"
    else
        print_error "打包失败"
        return 1
    fi
}

# 清理旧备份
cleanup_old_backups() {
    print_step "清理旧备份（保留最近 $MAX_BACKUPS 个）..."

    local count=0
    local total=0

    # 统计备份数量
    for backup in "$BACKUPS_DIR"/backup-*; do
        if [[ -d "$backup" ]]; then
            ((total++)) || true
        fi
    done

    # 如果超过最大数量，删除最旧的
    if [[ $total -gt $MAX_BACKUPS ]]; then
        local to_delete=$((total - MAX_BACKUPS))

        # 按时间排序删除最旧的
        for backup in $(ls -t "$BACKUPS_DIR" | grep "^backup-[0-9]" | tail -n $to_delete); do
            local backup_path="$BACKUPS_DIR/$backup"

            # 删除目录
            if [[ -d "$backup_path" ]]; then
                rm -rf "$backup_path"
                print_info "已删除旧备份: $backup"
                ((count++)) || true
            fi

            # 删除对应的压缩包
            if [[ -f "${backup_path}.tar.gz" ]]; then
                rm -f "${backup_path}.tar.gz"
                print_info "已删除旧备份压缩包: ${backup}.tar.gz"
            fi
        done
    fi

    # 同样清理压缩包
    local archive_count=0
    for archive in "$BACKUPS_DIR"/backup-*.tar.gz; do
        if [[ -f "$archive" ]]; then
            ((archive_count++)) || true
        fi
    done

    if [[ $archive_count -gt $MAX_BACKUPS ]]; then
        local to_delete=$((archive_count - MAX_BACKUPS))
        for archive in $(ls -t "$BACKUPS_DIR"/backup-*.tar.gz 2>/dev/null | tail -n $to_delete); do
            rm -f "$archive"
            print_info "已删除旧备份压缩包: $(basename "$archive")"
        done
    fi

    if [[ $count -gt 0 ]]; then
        print_success "已清理 $count 个旧备份"
    else
        print_info "无需清理旧备份"
    fi
}

# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "创建完整备份，包含数据库、配置和应用数据。"
    echo ""
    echo "选项:"
    echo "  --output-dir <dir>   备份输出目录 (默认: backups/)"
    echo "  --no-compress        不创建压缩包"
    echo "  --help, -h           显示此帮助信息"
    echo ""
    echo "备份内容:"
    echo "  database.sql         数据库备份 (plain SQL format)"
    echo "  backup.env           配置文件备份"
    echo "  backup.version       版本信息备份"
    echo "  data/                应用数据（如存在）"
    echo "  backup.json          备份元数据"
    echo ""
    echo "备份策略:"
    echo "  - 保留最近 $MAX_BACKUPS 个备份"
    echo "  - 自动打包压缩为 .tar.gz"
    echo "  - 压缩包可用于迁移到其他服务器"
    echo ""
    echo "恢复命令:"
    echo "  bash $DEPLOY_DIR/backup/restore-backup.sh <backup_name>"
}

# 主函数
main() {
    local output_dir="$BACKUPS_DIR"
    local no_compress="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --output-dir)
                output_dir="$2"
                BACKUPS_DIR="$output_dir"
                shift 2
                ;;
            --no-compress)
                no_compress="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Cyber Pulse 备份创建工具                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 确保备份目录存在
    mkdir -p "$BACKUPS_DIR"

    # 获取当前版本
    local current_version
    current_version=$(get_current_version)
    print_info "当前版本: $current_version"

    # 创建备份目录
    local backup_dir
    backup_dir=$(create_backup_dir)
    print_info "备份目录: $backup_dir"

    # 执行备份
    export_database "$backup_dir" || {
        print_error "数据库导出失败，备份创建失败"
        rm -rf "$backup_dir"
        exit 1
    }

    backup_config "$backup_dir"
    backup_data "$backup_dir"
    generate_metadata "$backup_dir" "$current_version"

    # 打包压缩
    local archive_file=""
    if [[ "$no_compress" != "true" ]]; then
        archive_file=$(compress_backup "$backup_dir") || {
            print_warning "压缩失败，但备份目录仍然可用"
        }
    fi

    # 清理旧备份
    cleanup_old_backups

    # 显示备份信息
    echo ""
    print_success "备份创建成功!"
    echo ""
    echo -e "${BOLD}备份信息:${NC}"
    echo "  目录: $backup_dir"
    echo "  大小: $(du -sh "$backup_dir" | cut -f1)"

    if [[ -n "$archive_file" ]]; then
        echo "  压缩包: $archive_file"
        echo "  压缩包大小: $(du -sh "$archive_file" | cut -f1)"
    fi

    echo ""
    echo -e "${YELLOW}恢复命令:${NC}"
    echo "  cyber-pulse.sh restore $(basename "$backup_dir")"
    echo ""

    if [[ -n "$archive_file" ]]; then
        echo -e "${CYAN}迁移到其他服务器:${NC}"
        echo "  1. 复制压缩包: scp $archive_file user@server:/path/to/backups/"
        echo "  2. 在目标服务器解压: tar -xzf $(basename "$archive_file")"
        echo "  3. 执行恢复: cyber-pulse.sh restore $(basename "$backup_dir")"
        echo ""
    fi
}

main "$@"