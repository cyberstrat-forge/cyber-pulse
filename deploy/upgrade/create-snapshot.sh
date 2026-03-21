#!/usr/bin/env bash
#
# create-snapshot.sh - 创建升级快照
#
# 功能:
#   - 创建数据库快照 (pg_dump custom format)
#   - 备份配置文件 (.env)
#   - 备份版本信息
#   - 生成快照元数据
#
# 用法:
#   create-snapshot.sh [--output-dir <dir>] [--retention <days>]
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
SNAPSHOTS_DIR="$PROJECT_ROOT/.snapshots"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
RETENTION_DAYS=7

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

# 获取当前版本
get_current_version() {
    local version_file="$PROJECT_ROOT/.version"
    if [[ -f "$version_file" ]]; then
        cat "$version_file"
    else
        # 尝试从 git 获取
        cd "$PROJECT_ROOT"
        git describe --tags --always 2>/dev/null || echo "unknown"
    fi
}

# 创建快照目录
create_snapshot_dir() {
    local snapshot_name="snapshot_$(date +%Y%m%d_%H%M%S)"
    local snapshot_dir="$SNAPSHOTS_DIR/$snapshot_name"

    mkdir -p "$snapshot_dir"
    echo "$snapshot_dir"
}

# 导出数据库
export_database() {
    local snapshot_dir="$1"
    local dump_file="$snapshot_dir/database.dump"

    print_step "正在导出数据库..."

    cd "$DEPLOY_DIR"

    # 检查 PostgreSQL 容器是否运行
    if ! $DOCKER_COMPOSE ps postgres 2>/dev/null | grep -q "running"; then
        print_error "PostgreSQL 容器未运行"
        return 1
    fi

    # 使用 pg_dump 导出数据库 (custom format)
    if $DOCKER_COMPOSE exec -T postgres pg_dump \
        -U cyberpulse \
        -d cyberpulse \
        -F c \
        -f /tmp/database.dump 2>/dev/null; then

        # 从容器复制到主机
        $DOCKER_COMPOSE exec -T postgres cat /tmp/database.dump > "$dump_file"

        # 清理容器内的临时文件
        $DOCKER_COMPOSE exec -T postgres rm -f /tmp/database.dump 2>/dev/null || true

        local size
        size=$(du -h "$dump_file" | cut -f1)
        print_success "数据库已导出 ($size)"
    else
        print_error "数据库导出失败"
        return 1
    fi
}

# 备份配置文件
backup_config() {
    local snapshot_dir="$1"

    print_step "正在备份配置文件..."

    # 备份 .env 文件
    if [[ -f "$ENV_FILE" ]]; then
        cp "$ENV_FILE" "$snapshot_dir/.env.backup"
        print_success ".env 配置已备份"
    else
        print_warning ".env 文件不存在，跳过"
    fi

    # 备份版本信息
    local version_file="$PROJECT_ROOT/.version"
    if [[ -f "$version_file" ]]; then
        cp "$version_file" "$snapshot_dir/.version.backup"
        print_success "版本信息已备份"
    fi

    # 备份 docker-compose.yml (用于记录部署配置)
    if [[ -f "$COMPOSE_FILE" ]]; then
        cp "$COMPOSE_FILE" "$snapshot_dir/docker-compose.yml.backup"
        print_success "docker-compose.yml 已备份"
    fi
}

# 生成元数据
generate_metadata() {
    local snapshot_dir="$1"
    local current_version="$2"
    local metadata_file="$snapshot_dir/metadata.json"

    print_step "正在生成快照元数据..."

    # 获取数据库大小
    local db_size="unknown"
    if [[ -f "$snapshot_dir/database.dump" ]]; then
        db_size=$(du -h "$snapshot_dir/database.dump" | cut -f1)
    fi

    # 获取 git 信息
    local git_branch="unknown"
    local git_commit="unknown"
    cd "$PROJECT_ROOT"
    git_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
    git_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

    # 生成 JSON 元数据
    cat > "$metadata_file" << EOF
{
    "snapshot_name": "$(basename "$snapshot_dir")",
    "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "version": "$current_version",
    "git_branch": "$git_branch",
    "git_commit": "$git_commit",
    "database_size": "$db_size",
    "components": {
        "database": "$([ -f "$snapshot_dir/database.dump" ] && echo "included" || echo "skipped")",
        "env_config": "$([ -f "$snapshot_dir/.env.backup" ] && echo "included" || echo "skipped")",
        "version_info": "$([ -f "$snapshot_dir/.version.backup" ] && echo "included" || echo "skipped")"
    }
}
EOF

    print_success "元数据已生成"
}

# 清理旧快照
cleanup_old_snapshots() {
    local retention_days="$1"

    if [[ ! -d "$SNAPSHOTS_DIR" ]]; then
        return 0
    fi

    print_step "清理超过 $retention_days 天的旧快照..."

    local count=0
    local now=$(date +%s)

    for snapshot in "$SNAPSHOTS_DIR"/snapshot_*; do
        if [[ ! -d "$snapshot" ]]; then
            continue
        fi

        # 获取快照时间
        local snapshot_name=$(basename "$snapshot")
        local snapshot_date=$(echo "$snapshot_name" | sed 's/snapshot_\([0-9_]*\).*/\1/')
        local snapshot_ts

        # 转换时间戳
        if snapshot_ts=$(date -j -f "%Y%m%d_%H%M%S" "$snapshot_date" +%s 2>/dev/null); then
            local age_days=$(( (now - snapshot_ts) / 86400 ))

            if [[ $age_days -gt $retention_days ]]; then
                rm -rf "$snapshot"
                ((count++)) || true
            fi
        fi
    done

    if [[ $count -gt 0 ]]; then
        print_success "已清理 $count 个旧快照"
    else
        print_info "无需清理旧快照"
    fi
}

# 打印信息
print_info() { echo -e "${BLUE}[i]${NC} $1"; }

# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "创建升级快照，包含数据库和配置文件。"
    echo ""
    echo "选项:"
    echo "  --output-dir <dir>   快照输出目录 (默认: .snapshots/)"
    echo "  --retention <days>   快照保留天数 (默认: 7)"
    echo "  --help, -h           显示此帮助信息"
    echo ""
    echo "快照内容:"
    echo "  database.dump        数据库快照 (pg_dump custom format)"
    echo "  .env.backup          配置文件备份"
    echo "  .version.backup      版本信息备份"
    echo "  metadata.json        快照元数据"
}

# 主函数
main() {
    local output_dir="$SNAPSHOTS_DIR"
    local retention="$RETENTION_DAYS"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --output-dir)
                output_dir="$2"
                SNAPSHOTS_DIR="$output_dir"
                shift 2
                ;;
            --retention)
                retention="$2"
                shift 2
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
    echo "║              Cyber Pulse 快照创建工具                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 确保快照目录存在
    mkdir -p "$SNAPSHOTS_DIR"

    # 获取当前版本
    local current_version
    current_version=$(get_current_version)
    print_info "当前版本: $current_version"

    # 创建快照目录
    local snapshot_dir
    snapshot_dir=$(create_snapshot_dir)
    print_info "快照目录: $snapshot_dir"

    # 执行备份
    export_database "$snapshot_dir" || {
        print_error "数据库导出失败，快照创建失败"
        rm -rf "$snapshot_dir"
        exit 1
    }

    backup_config "$snapshot_dir"
    generate_metadata "$snapshot_dir" "$current_version"

    # 清理旧快照
    cleanup_old_snapshots "$retention"

    # 显示快照信息
    echo ""
    print_success "快照创建成功!"
    echo ""
    echo -e "${BOLD}快照信息:${NC}"
    echo "  目录: $snapshot_dir"
    echo "  大小: $(du -sh "$snapshot_dir" | cut -f1)"
    echo ""
    echo -e "${YELLOW}恢复命令:${NC}"
    echo "  bash $DEPLOY_DIR/upgrade/restore-snapshot.sh $(basename "$snapshot_dir")"
    echo ""
}

main "$@"