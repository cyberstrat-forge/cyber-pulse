#!/usr/bin/env bash
#
# restore-backup.sh - 从备份恢复
#
# 功能:
#   - 恢复数据库备份
#   - 恢复配置文件
#   - 恢复应用数据
#   - 验证恢复结果
#
# 用法:
#   restore-backup.sh <backup_name> [--force]
#   restore-backup.sh --list
#   restore-backup.sh --from-archive <archive.tar.gz>
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

# 列出可用备份
list_backups() {
    echo -e "${BOLD}可用的备份:${NC}"
    echo ""

    if [[ ! -d "$BACKUPS_DIR" ]]; then
        print_warning "备份目录不存在: $BACKUPS_DIR"
        return 1
    fi

    local found=0

    # 列出备份目录
    for backup in "$BACKUPS_DIR"/backup-*; do
        if [[ -d "$backup" ]]; then
            local name=$(basename "$backup")
            local metadata="$backup/backup.json"

            if [[ -f "$metadata" ]]; then
                local created=$(grep -o '"created_at": *"[^"]*"' "$metadata" | cut -d'"' -f4)
                local version=$(grep -o '"version": *"[^"]*"' "$metadata" | cut -d'"' -f4)
                local db_size=$(grep -o '"database_size": *"[^"]*"' "$metadata" | cut -d'"' -f4)

                echo "  $name"
                echo "    创建时间: $created"
                echo "    版本: $version"
                echo "    数据库大小: $db_size"
                echo ""
            else
                echo "  $name (无元数据)"
                echo ""
            fi
            ((found++)) || true
        fi
    done

    # 列出压缩包
    local archives=0
    for archive in "$BACKUPS_DIR"/backup-*.tar.gz; do
        if [[ -f "$archive" ]]; then
            if [[ $archives -eq 0 ]]; then
                echo -e "${BOLD}压缩包备份:${NC}"
                echo ""
            fi
            local name=$(basename "$archive" .tar.gz)
            local size=$(du -h "$archive" | cut -f1)
            echo "  $name.tar.gz ($size)"
            ((archives++)) || true
        fi
    done

    if [[ $archives -gt 0 ]]; then
        echo ""
        echo -e "${CYAN}提示: 使用 --from-archive 解压压缩包后恢复${NC}"
        echo ""
    fi

    if [[ $found -eq 0 && $archives -eq 0 ]]; then
        print_warning "没有找到备份"
        return 1
    fi
}

# 验证备份
validate_backup() {
    local backup_dir="$1"

    print_step "验证备份完整性..."

    # 检查必要文件
    local required_files=("database.sql" "backup.json")
    local missing=0

    for file in "${required_files[@]}"; do
        if [[ ! -f "$backup_dir/$file" ]]; then
            print_error "缺少文件: $file"
            ((missing++)) || true
        fi
    done

    if [[ $missing -gt 0 ]]; then
        print_error "备份不完整"
        return 1
    fi

    print_success "备份验证通过"
}

# 解压压缩包
extract_archive() {
    local archive_file="$1"

    print_step "正在解压备份压缩包..."

    if [[ ! -f "$archive_file" ]]; then
        print_error "压缩包不存在: $archive_file"
        return 1
    fi

    local backup_name=$(basename "$archive_file" .tar.gz)
    local backup_dir="$BACKUPS_DIR/$backup_name"

    if [[ -d "$backup_dir" ]]; then
        print_warning "备份目录已存在: $backup_dir"
        print_info "将使用现有目录"
    else
        if tar -xzf "$archive_file" -C "$BACKUPS_DIR"; then
            print_success "解压完成: $backup_dir"
        else
            print_error "解压失败"
            return 1
        fi
    fi

    echo "$backup_dir"
}

# 恢复数据库
restore_database() {
    local backup_dir="$1"
    local sql_file="$backup_dir/database.sql"

    print_step "正在恢复数据库..."

    cd "$DEPLOY_DIR"

    # 检查 PostgreSQL 容器是否运行
    if ! $DOCKER_COMPOSE ps postgres 2>/dev/null | grep -q "running"; then
        print_error "PostgreSQL 容器未运行"
        print_warning "请先启动服务: cyber-pulse.sh start"
        return 1
    fi

    # 检查数据库是否为空或确认覆盖
    local table_count
    table_count=$($DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d cyberpulse \
        -t \
        -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

    if [[ -n "$table_count" && "$table_count" -gt 0 ]]; then
        print_warning "目标数据库包含 $table_count 个表"
    fi

    # 先终止所有连接，然后恢复
    print_info "终止现有数据库连接..."

    $DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d postgres \
        -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = 'cyberpulse' AND pid <> pg_backend_pid();" 2>/dev/null || true

    # 删除并重建数据库
    print_info "重建数据库..."

    $DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d postgres \
        -c "DROP DATABASE IF EXISTS cyberpulse;" 2>/dev/null

    $DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d postgres \
        -c "CREATE DATABASE cyberpulse;" 2>/dev/null

    # 恢复 SQL
    print_info "导入数据库..."

    local restore_output
    local restore_exit_code

    restore_output=$($DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d cyberpulse \
        < "$sql_file" 2>&1) || restore_exit_code=$?

    # psql 可能输出警告但实际成功
    if [[ -z "${restore_exit_code:-}" ]]; then
        print_success "数据库已恢复"
    elif echo "$restore_output" | grep -qiE "(FATAL|PANIC|could not|connection.*failed)"; then
        print_error "数据库恢复失败"
        echo "$restore_output"
        return 1
    else
        # 警告可以忽略
        print_success "数据库已恢复"
    fi
}

# 恢复配置文件
restore_config() {
    local backup_dir="$1"

    print_step "正在恢复配置文件..."

    # 恢复 .env 文件
    if [[ -f "$backup_dir/backup.env" ]]; then
        # 备份当前配置
        if [[ -f "$ENV_FILE" ]]; then
            cp "$ENV_FILE" "$ENV_FILE.before_restore"
            print_info "当前 .env 已备份到 .env.before_restore"
        fi

        cp "$backup_dir/backup.env" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        print_success ".env 配置已恢复"
    fi

    # 恢复版本信息
    if [[ -f "$backup_dir/backup.version" ]]; then
        cp "$backup_dir/backup.version" "$PROJECT_ROOT/.version"
        print_success "版本信息已恢复"
    fi
}

# 恢复应用数据
restore_data() {
    local backup_dir="$1"

    if [[ -d "$backup_dir/data" ]]; then
        print_step "正在恢复应用数据..."

        # 确保目标目录存在
        mkdir -p "$DATA_DIR"

        # 备份现有数据
        if [[ -d "$DATA_DIR" && -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]]; then
            local backup_data_dir="$DATA_DIR.before_restore"
            if [[ -d "$backup_data_dir" ]]; then
                rm -rf "$backup_data_dir"
            fi
            mv "$DATA_DIR" "$backup_data_dir"
            mkdir -p "$DATA_DIR"
            print_info "现有数据已备份到 $backup_data_dir"
        fi

        # 恢复数据
        cp -r "$backup_dir/data"/* "$DATA_DIR/" 2>/dev/null || true
        print_success "应用数据已恢复"
    fi
}

# 验证恢复
verify_restore() {
    print_step "验证恢复结果..."

    cd "$DEPLOY_DIR"

    # 检查数据库连接
    if $DOCKER_COMPOSE exec -T postgres pg_isready -U cyberpulse -d cyberpulse 2>/dev/null; then
        print_success "数据库连接正常"
    else
        print_warning "数据库连接检查失败"
    fi

    # 检查数据库表
    local table_count
    table_count=$($DOCKER_COMPOSE exec -T postgres psql \
        -U cyberpulse \
        -d cyberpulse \
        -t \
        -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

    if [[ -n "$table_count" && "$table_count" -gt 0 ]]; then
        print_success "数据库表数量: $table_count"
    else
        print_warning "数据库表检查失败或表为空"
    fi

    # 检查配置文件
    if [[ -f "$ENV_FILE" ]]; then
        print_success "配置文件已存在"
    else
        print_warning "配置文件不存在"
    fi
}

# 显示帮助
show_help() {
    echo "用法: $0 <backup_name> [选项]"
    echo ""
    echo "从备份恢复数据库、配置和应用数据。"
    echo ""
    echo "参数:"
    echo "  backup_name         备份名称 (如 backup-20260321-120000)"
    echo ""
    echo "选项:"
    echo "  --force, -f         跳过确认提示"
    echo "  --list, -l          列出可用备份"
    echo "  --from-archive <file>  从压缩包恢复"
    echo "  --help, -h          显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 backup-20260321-120000         恢复指定备份"
    echo "  $0 backup-20260321-120000 -f      强制恢复（跳过确认）"
    echo "  $0 --list                         列出可用备份"
    echo "  $0 --from-archive backup.tar.gz   从压缩包恢复"
}

# 主函数
main() {
    local backup_name=""
    local force="false"
    local list_only="false"
    local from_archive=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)
                force="true"
                shift
                ;;
            --list|-l)
                list_only="true"
                shift
                ;;
            --from-archive)
                from_archive="$2"
                shift 2
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            -*)
                print_error "未知参数: $1"
                show_help
                exit 1
                ;;
            *)
                if [[ -z "$backup_name" ]]; then
                    backup_name="$1"
                fi
                shift
                ;;
        esac
    done

    # 仅列出备份
    if [[ "$list_only" == "true" ]]; then
        list_backups
        exit $?
    fi

    # 从压缩包恢复
    if [[ -n "$from_archive" ]]; then
        # 确保备份目录存在
        mkdir -p "$BACKUPS_DIR"

        backup_name=$(extract_archive "$from_archive") || exit 1
        backup_name=$(basename "$backup_name")
    fi

    # 检查备份名称
    if [[ -z "$backup_name" ]]; then
        print_error "请指定备份名称"
        echo ""
        list_backups
        exit 1
    fi

    local backup_dir="$BACKUPS_DIR/$backup_name"

    # 检查备份是否存在
    if [[ ! -d "$backup_dir" ]]; then
        print_error "备份不存在: $backup_dir"
        echo ""
        list_backups
        exit 1
    fi

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Cyber Pulse 备份恢复工具                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 显示备份信息
    print_info "备份: $backup_name"

    if [[ -f "$backup_dir/backup.json" ]]; then
        local created=$(grep -o '"created_at": *"[^"]*"' "$backup_dir/backup.json" | cut -d'"' -f4)
        local version=$(grep -o '"version": *"[^"]*"' "$backup_dir/backup.json" | cut -d'"' -f4)
        print_info "创建时间: $created"
        print_info "版本: $version"
    fi

    echo ""

    # 确认操作
    if [[ "$force" != "true" ]]; then
        echo -e "${YELLOW}警告: 此操作将覆盖当前数据库、配置和应用数据！${NC}"
        echo ""
        read -r -p "确认恢复? (yes/no): " response
        if [[ "$response" != "yes" ]]; then
            print_info "操作已取消"
            exit 0
        fi
    fi

    echo ""

    # 验证备份
    validate_backup "$backup_dir" || exit 1

    # 恢复配置
    restore_config "$backup_dir"

    # 恢复数据库
    restore_database "$backup_dir"

    # 恢复应用数据
    restore_data "$backup_dir"

    # 验证恢复
    verify_restore

    echo ""
    print_success "备份恢复完成!"
    echo ""
    echo -e "${YELLOW}建议操作:${NC}"
    echo "  1. 重启服务: cyber-pulse.sh restart"
    echo "  2. 检查日志: cyber-pulse.sh logs"
    echo "  3. 验证功能: 访问 API 文档确认服务正常"
    echo ""
}

main "$@"