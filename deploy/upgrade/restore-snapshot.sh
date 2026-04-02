#!/usr/bin/env bash
#
# restore-snapshot.sh - 从快照恢复
#
# 功能:
#   - 恢复数据库快照
#   - 恢复配置文件
#   - 验证恢复结果
#
# 用法:
#   restore-snapshot.sh <snapshot_name> [--force]
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
ENV_FILE="$PROJECT_ROOT/deploy/.env"
SNAPSHOTS_DIR="$PROJECT_ROOT/.snapshots"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"

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

# 列出可用快照
list_snapshots() {
    echo -e "${BOLD}可用的快照:${NC}"
    echo ""

    if [[ ! -d "$SNAPSHOTS_DIR" ]]; then
        print_warning "快照目录不存在: $SNAPSHOTS_DIR"
        return 1
    fi

    local found=0
    for snapshot in "$SNAPSHOTS_DIR"/snapshot_*; do
        if [[ -d "$snapshot" ]]; then
            local name=$(basename "$snapshot")
            local metadata="$snapshot/metadata.json"

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

    if [[ $found -eq 0 ]]; then
        print_warning "没有找到快照"
        return 1
    fi
}

# 验证快照
validate_snapshot() {
    local snapshot_dir="$1"

    print_step "验证快照完整性..."

    # 检查必要文件
    local required_files=("database.dump" "metadata.json")
    local missing=0

    for file in "${required_files[@]}"; do
        if [[ ! -f "$snapshot_dir/$file" ]]; then
            print_error "缺少文件: $file"
            ((missing++)) || true
        fi
    done

    if [[ $missing -gt 0 ]]; then
        print_error "快照不完整"
        return 1
    fi

    print_success "快照验证通过"
}

# 恢复数据库
restore_database() {
    local snapshot_dir="$1"
    local dump_file="$snapshot_dir/database.dump"

    print_step "正在恢复数据库..."

    cd "$DEPLOY_DIR"

    # 检查 PostgreSQL 容器是否运行
    if ! $DOCKER_COMPOSE ps postgres 2>/dev/null | grep -q "Up"; then
        print_error "PostgreSQL 容器未运行"
        return 1
    fi

    # 复制备份文件到容器
    $DOCKER_COMPOSE exec -T postgres sh -c "cat > /tmp/database.dump" < "$dump_file"

    # 恢复数据库
    # 注意: pg_restore 需要数据库存在，我们使用 --clean 来删除现有对象
    local restore_output
    local restore_exit_code

    restore_output=$($DOCKER_COMPOSE exec -T postgres pg_restore \
        -U cyberpulse \
        -d cyberpulse \
        --clean \
        --if-exists \
        --no-owner \
        --no-privileges \
        /tmp/database.dump 2>&1) || restore_exit_code=$?

    # pg_restore 可能输出警告但实际成功，需要区分真正的错误
    # 常见警告: "ERROR: must be owner of" (权限警告，可忽略)
    # 真正的错误: "FATAL", "PANIC", 或 "ERROR" 相关致命错误
    if [[ -z "${restore_exit_code:-}" ]]; then
        # 退出码为 0，成功
        print_success "数据库已恢复"
    elif echo "$restore_output" | grep -qiE "(FATAL|PANIC|could not|connection.*failed|database.*does not exist)"; then
        # 真正的错误
        print_error "数据库恢复失败"
        echo "$restore_output"
        return 1
    else
        # 只有警告，恢复成功
        print_warning "数据库已恢复，存在警告:"
        echo "$restore_output" | grep -i "warning\|error" | head -5 || true
    fi

    # 清理容器内的临时文件
    $DOCKER_COMPOSE exec -T postgres rm -f /tmp/database.dump 2>/dev/null || true
}

# 恢复配置文件
restore_config() {
    local snapshot_dir="$1"

    print_step "正在恢复配置文件..."

    # 恢复 .env 文件
    if [[ -f "$snapshot_dir/.env.backup" ]]; then
        # 备份当前配置
        if [[ -f "$ENV_FILE" ]]; then
            cp "$ENV_FILE" "$ENV_FILE.before_restore"
            print_info "当前 .env 已备份到 .env.before_restore"
        fi

        cp "$snapshot_dir/.env.backup" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        print_success ".env 配置已恢复"
    fi

    # 恢复版本信息
    if [[ -f "$snapshot_dir/.version.backup" ]]; then
        cp "$snapshot_dir/.version.backup" "$PROJECT_ROOT/.version"
        print_success "版本信息已恢复"
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
}

# 显示帮助
show_help() {
    echo "用法: $0 <snapshot_name> [选项]"
    echo ""
    echo "从快照恢复数据库和配置。"
    echo ""
    echo "参数:"
    echo "  snapshot_name    快照名称 (如 snapshot_20260321_120000)"
    echo ""
    echo "选项:"
    echo "  --force, -f      跳过确认提示"
    echo "  --list, -l       列出可用快照"
    echo "  --help, -h       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 snapshot_20260321_120000      恢复指定快照"
    echo "  $0 snapshot_20260321_120000 -f   强制恢复（跳过确认）"
    echo "  $0 --list                        列出可用快照"
}

# 主函数
main() {
    local snapshot_name=""
    local force="false"
    local list_only="false"

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
                if [[ -z "$snapshot_name" ]]; then
                    snapshot_name="$1"
                fi
                shift
                ;;
        esac
    done

    # 仅列出快照
    if [[ "$list_only" == "true" ]]; then
        list_snapshots
        exit $?
    fi

    # 检查快照名称
    if [[ -z "$snapshot_name" ]]; then
        print_error "请指定快照名称"
        echo ""
        list_snapshots
        exit 1
    fi

    local snapshot_dir="$SNAPSHOTS_DIR/$snapshot_name"

    # 检查快照是否存在
    if [[ ! -d "$snapshot_dir" ]]; then
        print_error "快照不存在: $snapshot_dir"
        echo ""
        list_snapshots
        exit 1
    fi

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Cyber Pulse 快照恢复工具                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 显示快照信息
    print_info "快照: $snapshot_name"

    if [[ -f "$snapshot_dir/metadata.json" ]]; then
        local created=$(grep -o '"created_at": *"[^"]*"' "$snapshot_dir/metadata.json" | cut -d'"' -f4)
        local version=$(grep -o '"version": *"[^"]*"' "$snapshot_dir/metadata.json" | cut -d'"' -f4)
        print_info "创建时间: $created"
        print_info "版本: $version"
    fi

    echo ""

    # 确认操作
    if [[ "$force" != "true" ]]; then
        echo -e "${YELLOW}警告: 此操作将覆盖当前数据库和配置！${NC}"
        echo ""
        read -r -p "确认恢复? (yes/no): " response
        if [[ "$response" != "yes" ]]; then
            print_info "操作已取消"
            exit 0
        fi
    fi

    echo ""

    # 验证快照
    validate_snapshot "$snapshot_dir" || exit 1

    # 恢复配置
    restore_config "$snapshot_dir"

    # 恢复数据库
    restore_database "$snapshot_dir"

    # 验证恢复
    verify_restore

    echo ""
    print_success "快照恢复完成!"
    echo ""
    echo -e "${YELLOW}建议操作:${NC}"
    echo "  1. 重启服务: cyber-pulse.sh restart"
    echo "  2. 检查日志: cyber-pulse.sh logs"
    echo "  3. 验证功能: 访问 API 文档确认服务正常"
    echo ""
}

main "$@"