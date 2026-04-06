#!/usr/bin/env bash
#
# api.sh - Cyber Pulse API 管理脚本
#
# 功能:
#   配置 API 连接、管理情报源、任务、客户端、日志、诊断
#   支持多环境配置（prod/dev/test）
#
# 使用:
#   ./scripts/api.sh configure --env dev    # 配置开发环境
#   ./scripts/api.sh env switch prod        # 切换到生产环境
#   ./scripts/api.sh --env dev sources list # 临时使用 dev 环境
#   ./scripts/api.sh sources list           # 使用当前环境
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

# 配置文件路径
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/cyber-pulse"
ENV_DIR="$CONFIG_DIR/environments"
CURRENT_ENV_FILE="$CONFIG_DIR/current_env"
LEGACY_CONFIG="$CONFIG_DIR/config"  # 旧版单环境配置

# 默认值
DEFAULT_ENV="prod"
DEFAULT_API_URL="http://localhost:8000"
VALID_ENVS=("prod" "dev" "test")

# 当前环境（全局变量，由 parse_env_override 设置）
CURRENT_ENV=""

# ============================================
# 环境管理函数
# ============================================

# 获取当前环境
get_current_env() {
    if [[ -f "$CURRENT_ENV_FILE" ]]; then
        cat "$CURRENT_ENV_FILE"
    else
        echo "$DEFAULT_ENV"
    fi
}

# 获取指定环境的配置文件路径
get_env_config_file() {
    local env="${1:-$(get_current_env)}"
    echo "$ENV_DIR/${env}.conf"
}

# 检查环境名是否有效
validate_env() {
    local env="$1"
    for valid_env in "${VALID_ENVS[@]}"; do
        if [[ "$env" == "$valid_env" ]]; then
            return 0
        fi
    done
    return 1
}

# ============================================
# 工具函数
# ============================================

print_error() {
    echo -e "${RED}[✗]${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

die() {
    print_error "$1"
    exit 1
}

# 检查依赖
check_dependencies() {
    local missing=()

    if ! command -v curl &>/dev/null; then
        missing+=("curl")
    fi

    if ! command -v jq &>/dev/null; then
        missing+=("jq")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing dependencies: ${missing[*]}. Please install them first."
    fi
}

# 加载配置（支持多环境）
load_config() {
    local env="${CURRENT_ENV:-$(get_current_env)}"
    local env_config
    env_config=$(get_env_config_file "$env")

    # 优先使用新的多环境配置
    if [[ -f "$env_config" ]]; then
        # shellcheck source=/dev/null
        source "$env_config"
    # 兼容旧版单配置文件（自动迁移到 prod 环境）
    elif [[ -f "$LEGACY_CONFIG" && "$env" == "prod" ]]; then
        print_info "检测到旧版配置文件，自动迁移到 prod 环境..."
        mkdir -p "$ENV_DIR"
        mv "$LEGACY_CONFIG" "$env_config"
        echo "prod" > "$CURRENT_ENV_FILE"
        # shellcheck source=/dev/null
        source "$env_config"
    else
        die "环境 '$env' 未配置。运行 './scripts/api.sh configure --env $env' 配置。"
    fi

    if [[ -z "${api_url:-}" ]]; then
        die "api_url not set in config. Run './scripts/api.sh configure' first."
    fi

    if [[ -z "${admin_key:-}" ]]; then
        die "admin_key not set in config. Run './scripts/api.sh configure' first."
    fi
}

# API 请求函数
api_request() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local url="${api_url}${endpoint}"
    local args=(-s -X "$method" -H "Authorization: Bearer $admin_key" -H "Content-Type: application/json")

    if [[ -n "$data" ]]; then
        args+=(-d "$data")
    fi

    curl "${args[@]}" "$url"
}

# GET 请求
api_get() {
    api_request "GET" "$1"
}

# POST 请求
api_post() {
    api_request "POST" "$1" "${2:-}"
}

# DELETE 请求
api_delete() {
    api_request "DELETE" "$1"
}

# 检查 API 错误
check_api_error() {
    local response="$1"

    if echo "$response" | jq -e '.detail' &>/dev/null; then
        local detail
        detail=$(echo "$response" | jq -r '.detail')
        die "API error: $detail"
    fi
}

# ============================================
# Configure 命令
# ============================================

cmd_configure() {
    local input_api_url=""
    local input_admin_key=""
    local input_env=""
    local non_interactive="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --env)
                input_env="$2"
                shift 2
                ;;
            --url)
                input_api_url="$2"
                non_interactive="true"
                shift 2
                ;;
            --key)
                input_admin_key="$2"
                non_interactive="true"
                shift 2
                ;;
            --help|-h)
                echo "用法: api.sh configure [选项]"
                echo ""
                echo "选项:"
                echo "  --env ENV      环境名 (prod/dev/test, 默认: prod 或当前环境)"
                echo "  --url URL      API URL (非交互式)"
                echo "  --key KEY      Admin API Key (非交互式)"
                echo ""
                echo "示例:"
                echo "  api.sh configure                              # 交互式配置当前环境"
                echo "  api.sh configure --env dev                    # 配置开发环境"
                echo "  api.sh configure --env dev --url http://localhost:8002 --key cp_live_xxx"
                return 0
                ;;
            *)
                shift
                ;;
        esac
    done

    # 确定目标环境
    local target_env="${input_env:-${CURRENT_ENV:-$(get_current_env)}}"
    if ! validate_env "$target_env"; then
        die "无效的环境名: $target_env。有效值: ${VALID_ENVS[*]}"
    fi

    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 配置                               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    print_info "配置环境: $target_env"
    echo ""

    # 创建配置目录
    mkdir -p "$ENV_DIR"

    # 根据环境设置默认 URL
    local default_url="$DEFAULT_API_URL"
    case "$target_env" in
        dev)  default_url="http://localhost:8002" ;;
        test) default_url="http://localhost:8001" ;;
    esac

    # 交互式模式
    if [[ "$non_interactive" != "true" ]]; then
        # 提示输入 API URL
        echo -e "${BLUE}API URL${NC} (按 Enter 使用默认值: $default_url)"
        read -r -p "> " input_api_url
        local final_api_url="${input_api_url:-$default_url}"

        # 提示输入 Admin Key
        echo ""
        echo -e "${BLUE}Admin API Key${NC} (格式: cp_live_xxxx)"
        read -r -p "> " input_admin_key

        if [[ -z "$input_admin_key" ]]; then
            die "Admin API Key 不能为空"
        fi
    else
        # 非交互式模式：使用参数
        local final_api_url="${input_api_url:-$default_url}"

        if [[ -z "$input_admin_key" ]]; then
            die "非交互式模式需要 --key 参数"
        fi
    fi

    # 验证 Key 格式
    if [[ ! "$input_admin_key" =~ ^cp_live_[a-f0-9]{32}$ ]]; then
        print_warning "Key 格式可能不正确，预期格式: cp_live_ + 32 位十六进制字符"
    fi

    # 测试连接
    echo ""
    print_info "测试连接..."

    local test_response
    test_response=$(curl -s -H "Authorization: Bearer $input_admin_key" "${final_api_url}/api/v1/admin/diagnose" 2>/dev/null || echo '{"detail":"Connection failed"}')

    if echo "$test_response" | jq -e '.status' &>/dev/null; then
        print_success "连接成功"
    else
        local detail
        detail=$(echo "$test_response" | jq -r '.detail // "Unknown error"')
        print_warning "连接测试失败: $detail"
        if [[ "$non_interactive" != "true" ]]; then
            echo ""
            read -r -p "仍要保存配置吗? (y/N): " save_anyway
            if [[ ! "$save_anyway" =~ ^[Yy]$ ]]; then
                die "配置已取消"
            fi
        fi
    fi

    # 写入环境配置文件
    local env_config
    env_config=$(get_env_config_file "$target_env")
    cat > "$env_config" << EOF
# Cyber Pulse API Configuration - $target_env environment
# Generated by: api.sh configure
# Date: $(date '+%Y-%m-%d %H:%M:%S')

api_url=${final_api_url}
admin_key=${input_admin_key}
EOF

    chmod 600 "$env_config"

    # 如果是第一个配置的环境，设为当前环境
    if [[ ! -f "$CURRENT_ENV_FILE" ]]; then
        echo "$target_env" > "$CURRENT_ENV_FILE"
        print_info "已设置 '$target_env' 为当前环境"
    fi

    echo ""
    print_success "配置已保存到: $env_config"
    print_info "文件权限: 600"
}

# ============================================
# Environment 命令
# ============================================

cmd_env() {
    local subcommand="${1:-current}"
    shift || true

    case "$subcommand" in
        current)
            cmd_env_current
            ;;
        list)
            cmd_env_list
            ;;
        switch)
            cmd_env_switch "$@"
            ;;
        --help|-h)
            echo "用法: api.sh env <命令>"
            echo ""
            echo "命令:"
            echo "  current    显示当前环境"
            echo "  list       列出所有已配置的环境"
            echo "  switch ENV 切换到指定环境"
            echo ""
            echo "示例:"
            echo "  api.sh env current"
            echo "  api.sh env list"
            echo "  api.sh env switch dev"
            ;;
        *)
            print_error "未知命令: env $subcommand"
            echo "运行 'api.sh env --help' 查看帮助"
            return 1
            ;;
    esac
}

cmd_env_current() {
    local current="${CURRENT_ENV:-$(get_current_env)}"
    echo "当前环境: $current"

    local env_config
    env_config=$(get_env_config_file "$current")

    if [[ -f "$env_config" ]]; then
        # shellcheck source=/dev/null
        source "$env_config"
        echo "API URL: ${api_url}"
    else
        print_warning "环境 '$current' 未配置"
        echo "运行 'api.sh configure --env $current' 配置"
    fi
}

cmd_env_list() {
    local current="${CURRENT_ENV:-$(get_current_env)}"

    echo "已配置的环境:"
    echo ""

    local found=0
    for env in "${VALID_ENVS[@]}"; do
        local env_config
        env_config=$(get_env_config_file "$env")

        local marker="  "
        if [[ "$env" == "$current" ]]; then
            marker="* "
        fi

        if [[ -f "$env_config" ]]; then
            # shellcheck source=/dev/null
            source "$env_config"
            echo -e "${marker}${env}\t${api_url}"
            found=$((found + 1))
        else
            echo -e "  ${env}\t(未配置)"
        fi
    done

    echo ""
    if [[ $found -eq 0 ]]; then
        print_warning "没有已配置的环境"
        echo "运行 'api.sh configure' 配置环境"
    else
        echo "* = 当前环境"
    fi
}

cmd_env_switch() {
    local target_env="${1:-}"

    if [[ -z "$target_env" ]]; then
        die "请指定环境名: api.sh env switch <env>"
    fi

    if ! validate_env "$target_env"; then
        die "无效的环境名: $target_env。有效值: ${VALID_ENVS[*]}"
    fi

    local env_config
    env_config=$(get_env_config_file "$target_env")

    if [[ ! -f "$env_config" ]]; then
        die "环境 '$target_env' 未配置。运行 'api.sh configure --env $target_env' 配置。"
    fi

    echo "$target_env" > "$CURRENT_ENV_FILE"
    print_success "已切换到环境: $target_env"

    # 显示配置信息
    # shellcheck source=/dev/null
    source "$env_config"
    echo "API URL: ${api_url}"
}

# ============================================
# Sources 命令
# ============================================

cmd_sources() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)           cmd_sources_list "$@" ;;
        get)            cmd_sources_get "$@" ;;
        create)         cmd_sources_create "$@" ;;
        update)         cmd_sources_update "$@" ;;
        delete)         cmd_sources_delete "$@" ;;
        test)           cmd_sources_test "$@" ;;
        schedule)       cmd_sources_schedule "$@" ;;
        unschedule)     cmd_sources_unschedule "$@" ;;
        import)         cmd_sources_import "$@" ;;
        export)         cmd_sources_export "$@" ;;
        defaults)       cmd_sources_defaults "$@" ;;
        set-defaults)   cmd_sources_set_defaults "$@" ;;
        cleanup)        cmd_sources_cleanup "$@" ;;
        validate)       cmd_sources_validate "$@" ;;
        *)
            print_error "Unknown sources subcommand: $subcommand"
            print_sources_help
            exit 1
            ;;
    esac
}

cmd_sources_list() {
    local status_filter=""
    local tier_filter=""
    local scheduled_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)       status_filter="$2"; shift 2 ;;
            --tier)         tier_filter="$2"; shift 2 ;;
            --scheduled)    scheduled_filter="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    local endpoint="/api/v1/admin/sources"
    local params=()

    [[ -n "$status_filter" ]] && params+=("status=$status_filter")
    [[ -n "$tier_filter" ]] && params+=("tier=$tier_filter")
    [[ -n "$scheduled_filter" ]] && params+=("scheduled=$scheduled_filter")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Name", "Type", "Status", "Tier", "Scheduled"],
            ["--", "----", "----", "------", "----", "---------"],
            (.data[] | [.source_id, .name, .connector_type, .status, .tier, (if .schedule_interval != null then "Yes" else "No" end)])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_sources_get() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources get <source_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/sources/$source_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_sources_create() {
    local name=""
    local connector_type=""
    local url=""
    local tier=""
    local needs_full_fetch=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)     name="$2"; shift 2 ;;
            --type)     connector_type="$2"; shift 2 ;;
            --url)      url="$2"; shift 2 ;;
            --tier)     tier="$2"; shift 2 ;;
            --needs-full-fetch) needs_full_fetch="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    [[ -z "$name" ]] && die "--name is required"
    [[ -z "$connector_type" ]] && die "--type is required"
    [[ -z "$url" ]] && die "--url is required"

    local data

    # 根据 connector_type 使用不同的 config key
    if [[ "$connector_type" == "youtube" ]]; then
        # YouTube 使用 channel_url
        data=$(jq -n \
            --arg name "$name" \
            --arg type "$connector_type" \
            --arg url "$url" \
            --arg tier "$tier" \
            '{name: $name, connector_type: $type, config: {channel_url: $url}} + if $tier != "" then {tier: $tier} else {} end'
        )
    else
        # RSS 等类型使用 feed_url
        data=$(jq -n \
            --arg name "$name" \
            --arg type "$connector_type" \
            --arg url "$url" \
            --arg tier "$tier" \
            --argjson needs_full_fetch "${needs_full_fetch:-false}" \
            '{name: $name, connector_type: $type, config: {feed_url: $url}} + if $tier != "" then {tier: $tier} else {} end + if $needs_full_fetch then {needs_full_fetch: $needs_full_fetch} else {} end'
        )
    fi

    local response
    response=$(api_post "/api/v1/admin/sources" "$data")
    check_api_error "$response"

    print_success "Source created"
    echo "$response" | jq .
}

cmd_sources_update() {
    local source_id="${1:-}"
    shift

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources update <source_id> [options]"
    fi

    local data="{}"
    local url_value=""
    local use_channel_url="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)     data=$(echo "$data" | jq --arg v "$2" '. + {name: $v}'); shift 2 ;;
            --url)      url_value="$2"; shift 2 ;;
            --tier)     data=$(echo "$data" | jq --arg v "$2" '. + {tier: $v}'); shift 2 ;;
            --status)   data=$(echo "$data" | jq --arg v "$2" '. + {status: $v}'); shift 2 ;;
            --score)    data=$(echo "$data" | jq --argjson v "$2" '. + {score: $v}'); shift 2 ;;
            --needs-full-fetch) data=$(echo "$data" | jq --argjson v "$2" '. + {needs_full_fetch: $v}'); shift 2 ;;
            --schedule-interval) data=$(echo "$data" | jq --argjson v "$2" '. + {schedule_interval: $v}'); shift 2 ;;
            --config)   data=$(echo "$data" | jq --argjson v "$2" '. + {config: $v}'); shift 2 ;;
            *)          shift ;;
        esac
    done

    # 如果指定了 --url，需要根据 connector_type 使用不同的 key
    if [[ -n "$url_value" ]]; then
        # 获取源的 connector_type
        local source_info
        source_info=$(api_get "/api/v1/admin/sources/$source_id")
        local connector_type
        connector_type=$(echo "$source_info" | jq -r '.connector_type')

        if [[ "$connector_type" == "youtube" ]]; then
            # YouTube 使用 channel_url
            data=$(echo "$data" | jq --arg v "$url_value" '.config = (.config // {}) + {channel_url: $v}')
        else
            # RSS 等类型使用 feed_url
            data=$(echo "$data" | jq --arg v "$url_value" '.config = (.config // {}) + {feed_url: $v}')
        fi
    fi

    local response
    response=$(api_request "PUT" "/api/v1/admin/sources/$source_id" "$data")
    check_api_error "$response"

    print_success "Source updated"
    echo "$response" | jq .
}

cmd_sources_delete() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources delete <source_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/sources/$source_id")

    if [[ -z "$response" ]]; then
        print_success "Source deleted: $source_id"
    else
        check_api_error "$response"
    fi
}

cmd_sources_test() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources test <source_id>"
    fi

    print_info "Testing source: $source_id"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/test")
    check_api_error "$response"

    local test_result
    test_result=$(echo "$response" | jq -r '.test_result')

    if [[ "$test_result" == "success" ]]; then
        print_success "Source test passed"
        echo ""
        echo "$response" | jq '{
            source_id,
            test_result,
            response_time_ms,
            items_found,
            last_modified
        }'
    else
        print_error "Source test failed"
        echo ""
        echo "$response" | jq '{
            source_id,
            test_result,
            error_type,
            error_message,
            suggestion
        }'
    fi
}

cmd_sources_schedule() {
    local source_id="${1:-}"
    local interval=""

    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval)  interval="$2"; shift 2 ;;
            *)           shift ;;
        esac
    done

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources schedule <source_id> --interval SECONDS"
    fi

    if [[ -z "$interval" ]]; then
        die "Please specify --interval SECONDS (minimum 300)"
    fi

    local data="{\"interval\": ${interval}}"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/schedule" "$data")
    check_api_error "$response"

    print_success "Schedule set for $source_id"
    echo "$response" | jq .
}

cmd_sources_unschedule() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources unschedule <source_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/sources/${source_id}/schedule")
    check_api_error "$response"

    print_success "Schedule removed for $source_id"
    echo "$response" | jq .
}

cmd_sources_import() {
    local file=""
    local skip_invalid="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file)         file="$2"; shift 2 ;;
            --skip-invalid) skip_invalid="true"; shift ;;
            *)              shift ;;
        esac
    done

    if [[ -z "$file" ]]; then
        die "Usage: api.sh sources import --file FILE.opml [--skip-invalid]"
    fi

    if [[ ! -f "$file" ]]; then
        die "File not found: $file"
    fi

    print_info "Importing sources from: $file"

    # 使用 curl 上传文件
    local response
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $admin_key" \
        -F "file=@${file}" \
        -F "skip_invalid=${skip_invalid}" \
        "${api_url}/api/v1/admin/sources/import")

    check_api_error "$response"

    local job_id
    job_id=$(echo "$response" | jq -r '.job_id')

    print_success "Import job created: $job_id"
    echo ""
    echo "Check job status with:"
    echo "  ./scripts/api.sh jobs get $job_id"
}

cmd_sources_export() {
    local output_file="${1:-sources-export.yaml}"

    print_info "Exporting sources..."

    local response
    response=$(api_get "/api/v1/admin/sources/export")
    check_api_error "$response"

    echo "$response" > "$output_file"
    print_success "Sources exported to: $output_file"
}

cmd_sources_defaults() {
    local response
    response=$(api_get "/api/v1/admin/sources/defaults")
    check_api_error "$response"

    echo "Default fetch interval settings:"
    echo "$response" | jq .
}

cmd_sources_set_defaults() {
    local interval=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval)  interval="$2"; shift 2 ;;
            *)           shift ;;
        esac
    done

    if [[ -z "$interval" ]]; then
        die "Usage: api.sh sources set-defaults --interval SECONDS"
    fi

    local data="{\"default_fetch_interval\": ${interval}}"

    local response
    response=$(api_request "PATCH" "/api/v1/admin/sources/defaults" "$data")
    check_api_error "$response"

    print_success "Default fetch interval updated"
    echo "$response" | jq .
}

cmd_sources_cleanup() {
    print_info "Cleaning up REMOVED sources..."

    local response
    response=$(api_post "/api/v1/admin/sources/cleanup")
    check_api_error "$response"

    local deleted_sources deleted_items deleted_jobs
    deleted_sources=$(echo "$response" | jq -r '.deleted_sources')
    deleted_items=$(echo "$response" | jq -r '.deleted_items')
    deleted_jobs=$(echo "$response" | jq -r '.deleted_jobs')

    print_success "Cleaned up $deleted_sources sources, $deleted_items items, $deleted_jobs jobs"
    echo "$response" | jq .
}

cmd_sources_validate() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh sources validate <source_id>"
    fi

    print_info "Validating source: $source_id"

    local response
    response=$(api_post "/api/v1/admin/sources/${source_id}/validate")
    check_api_error "$response"

    local is_valid
    is_valid=$(echo "$response" | jq -r '.is_valid')

    if [[ "$is_valid" == "true" ]]; then
        print_success "Validation passed"
    else
        print_warning "Validation failed"
    fi

    echo ""
    echo "$response" | jq .
}

print_sources_help() {
    echo ""
    echo "Sources commands:"
    echo "  list [--status STATUS] [--tier TIER] [--scheduled BOOL]"
    echo "  get <source_id>"
    echo "  create --name NAME --type TYPE --url URL [--tier TIER]"
    echo "  update <source_id> [--name NAME] [--url URL] [--tier TIER] [--status STATUS]"
    echo "  delete <source_id>"
    echo ""
    echo "  test <source_id>                          测试源连接"
    echo "  validate <source_id>                      验证源配置"
    echo "  schedule <source_id> --interval SECONDS   设置采集调度"
    echo "  unschedule <source_id>                    取消采集调度"
    echo ""
    echo "  import --file FILE.opml [--skip-invalid]  批量导入"
    echo "  export [OUTPUT_FILE]                      导出源配置"
    echo ""
    echo "  defaults                                  查看默认配置"
    echo "  set-defaults --interval SECONDS           设置默认采集间隔"
    echo ""
    echo "  cleanup                                   清理已删除的源（物理删除）"
    echo ""
    echo "Connector types:"
    echo "  rss      - RSS/Atom feed (--url: feed URL)"
    echo "  youtube  - YouTube channel (--url: channel URL, supports @handle)"
    echo ""
    echo "Examples:"
    echo "  # RSS 源"
    echo "  api.sh sources create --name \"Krebs\" --type rss --url \"https://krebsonsecurity.com/feed/\" --tier T1"
    echo ""
    echo "  # YouTube 源"
    echo "  api.sh sources create --name \"Black Hat\" --type youtube --url \"https://www.youtube.com/@BlackHatOfficialYT\" --tier T1"
}

# ============================================
# Jobs 命令
# ============================================

cmd_jobs() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)       cmd_jobs_list "$@" ;;
        get)        cmd_jobs_get "$@" ;;
        run)        cmd_jobs_run "$@" ;;
        delete)     cmd_jobs_delete "$@" ;;
        retry)      cmd_jobs_retry "$@" ;;
        cleanup)    cmd_jobs_cleanup "$@" ;;
        *)
            print_error "Unknown jobs subcommand: $subcommand"
            print_jobs_help
            exit 1
            ;;
    esac
}

cmd_jobs_list() {
    local type_filter=""
    local status_filter=""
    local source_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --type)     type_filter="$2"; shift 2 ;;
            --status)   status_filter="$2"; shift 2 ;;
            --source)   source_filter="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/jobs"
    local params=()

    [[ -n "$type_filter" ]] && params+=("job_type=$type_filter")
    [[ -n "$status_filter" ]] && params+=("status=$status_filter")
    [[ -n "$source_filter" ]] && params+=("source_id=$source_filter")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Type", "Status", "Source", "Started", "Items"],
            ["--", "----", "------", "------", "-------", "-----"],
            (.data[] | [.job_id[:20], .job_type, .status, (.source_id[:12] // "-"), (.started_at[:16] // "-"), (.items_processed // 0)])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_jobs_get() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs get <job_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/jobs/$job_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_jobs_run() {
    local source_id="${1:-}"

    if [[ -z "$source_id" ]]; then
        die "Usage: api.sh jobs run <source_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/jobs" "{\"type\": \"ingest\", \"source_id\": \"$source_id\"}")
    check_api_error "$response"

    print_success "Job created"
    echo "$response" | jq .
}

cmd_jobs_delete() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs delete <job_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/jobs/$job_id")
    check_api_error "$response"

    print_success "Job deleted: $job_id"
    echo "$response" | jq .
}

cmd_jobs_retry() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs retry <job_id>"
    fi

    print_info "Retrying job: $job_id"

    local response
    response=$(api_post "/api/v1/admin/jobs/${job_id}/retry")
    check_api_error "$response"

    print_success "Job queued for retry"
    echo "$response" | jq .
}

cmd_jobs_cleanup() {
    local days="30"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --days)  days="$2"; shift 2 ;;
            *)       shift ;;
        esac
    done

    print_info "Cleaning up jobs older than $days days..."

    local response
    response=$(api_post "/api/v1/admin/jobs/cleanup?days=${days}")
    check_api_error "$response"

    local deleted_count
    deleted_count=$(echo "$response" | jq -r '.deleted_count')

    print_success "Deleted $deleted_count old jobs"
    echo "$response" | jq .
}

print_jobs_help() {
    echo ""
    echo "Jobs commands:"
    echo "  list [--type TYPE] [--status STATUS] [--source SOURCE_ID]"
    echo "  get <job_id>"
    echo "  run <source_id>"
    echo "  delete <job_id>              Delete a FAILED job"
    echo "  retry <job_id>               Retry a FAILED job"
    echo "  cleanup [--days 30]          Cleanup old completed jobs"
}

# ============================================
# Clients 命令
# ============================================

cmd_clients() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)       cmd_clients_list "$@" ;;
        get)        cmd_clients_get "$@" ;;
        create)     cmd_clients_create "$@" ;;
        rotate)     cmd_clients_rotate "$@" ;;
        suspend)    cmd_clients_suspend "$@" ;;
        activate)   cmd_clients_activate "$@" ;;
        delete)     cmd_clients_delete "$@" ;;
        *)
            print_error "Unknown clients subcommand: $subcommand"
            print_clients_help
            exit 1
            ;;
    esac
}

cmd_clients_list() {
    local status_filter=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --status)   status_filter="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/clients"

    if [[ -n "$status_filter" ]]; then
        endpoint="${endpoint}?status=${status_filter}"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            ["ID", "Name", "Status", "Permissions", "Created"],
            ["--", "----", "------", "-----------", "-------"],
            (.data[] | [.client_id, .name, .status, (.permissions | join(",")), (.created_at[:10] // "-")])
            | @tsv
        else
            .[]
        end
    ' | column -t -s $'\t'
}

cmd_clients_get() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients get <client_id>"
    fi

    local response
    response=$(api_get "/api/v1/admin/clients/$client_id")
    check_api_error "$response"

    echo "$response" | jq .
}

cmd_clients_create() {
    local name=""
    local permissions=""
    local description=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)         name="$2"; shift 2 ;;
            --permissions)  permissions="$2"; shift 2 ;;
            --description)  description="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    [[ -z "$name" ]] && die "--name is required"

    local perms_array="[]"
    if [[ -n "$permissions" ]]; then
        perms_array=$(echo "$permissions" | jq -R 'split(",")')
    fi

    local data
    data=$(jq -n \
        --arg name "$name" \
        --argjson perms "$perms_array" \
        --arg desc "$description" \
        '{name: $name, permissions: $perms} + if $desc != "" then {description: $desc} else {} end'
    )

    local response
    response=$(api_post "/api/v1/admin/clients" "$data")
    check_api_error "$response"

    print_success "Client created"
    echo ""
    echo "$response" | jq .
    echo ""
    print_warning "IMPORTANT: Save the API key now - it cannot be retrieved later!"
}

cmd_clients_rotate() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients rotate <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/rotate")
    check_api_error "$response"

    print_success "Key rotated"
    echo ""
    echo "$response" | jq .
    echo ""
    print_warning "IMPORTANT: Save the new API key now - old key is invalid!"
}

cmd_clients_suspend() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients suspend <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/suspend")
    check_api_error "$response"

    print_success "Client suspended: $client_id"
}

cmd_clients_activate() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients activate <client_id>"
    fi

    local response
    response=$(api_post "/api/v1/admin/clients/$client_id/activate")
    check_api_error "$response"

    print_success "Client activated: $client_id"
}

cmd_clients_delete() {
    local client_id="${1:-}"

    if [[ -z "$client_id" ]]; then
        die "Usage: api.sh clients delete <client_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/clients/$client_id")

    if [[ -z "$response" ]]; then
        print_success "Client deleted: $client_id"
    else
        check_api_error "$response"
    fi
}

print_clients_help() {
    echo ""
    echo "Clients commands:"
    echo "  list [--status STATUS]"
    echo "  get <client_id>"
    echo "  create --name NAME [--permissions PERMS] [--description DESC]"
    echo "  rotate <client_id>"
    echo "  suspend <client_id>"
    echo "  activate <client_id>"
    echo "  delete <client_id>"
}

# ============================================
# Logs 命令
# ============================================

cmd_logs() {
    local level=""
    local source_id=""
    local since=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --level)    level="$2"; shift 2 ;;
            --source)   source_id="$2"; shift 2 ;;
            --since)    since="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    local endpoint="/api/v1/admin/logs"
    local params=()

    [[ -n "$level" ]] && params+=("level=$level")
    [[ -n "$source_id" ]] && params+=("source_id=$source_id")
    [[ -n "$since" ]] && params+=("since=$since")

    if [[ ${#params[@]} -gt 0 ]]; then
        endpoint="${endpoint}?$(IFS='&'; echo "${params[*]}")"
    fi

    local response
    response=$(api_get "$endpoint")
    check_api_error "$response"

    echo "$response" | jq -r '
        if .data then
            .data[] | "[\(.timestamp[:19])] \(.level | ascii_upcase) \(.message)"
        else
            .[]
        end
    '
}

# ============================================
# Diagnose 命令
# ============================================

cmd_diagnose() {
    local response
    response=$(api_get "/api/v1/admin/diagnose")
    check_api_error "$response"

    echo "$response" | jq .
}

# ============================================
# API Keys 管理命令
# ============================================

# 获取 .env 文件路径
get_env_file_path() {
    local env="${CURRENT_ENV:-$(get_current_env)}"
    local project_root

    # 查找项目根目录
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    project_root="$(cd "$script_dir/.." && pwd)"

    echo "$project_root/deploy/.env"
}

# 从 .env 文件获取值
get_env_value() {
    local key="$1"
    local env_file
    env_file=$(get_env_file_path)

    if [[ -f "$env_file" ]]; then
        grep "^${key}=" "$env_file" 2>/dev/null | cut -d'=' -f2- || echo ""
    else
        echo ""
    fi
}

# 设置 .env 文件中的值
set_env_value() {
    local key="$1"
    local value="$2"
    local env_file
    env_file=$(get_env_file_path)

    if [[ ! -f "$env_file" ]]; then
        print_error ".env 文件不存在: $env_file"
        print_info "请先运行: ./scripts/cyber-pulse.sh deploy --env ${CURRENT_ENV:-prod}"
        return 1
    fi

    # 检查 key 是否存在
    if grep -q "^${key}=" "$env_file" 2>/dev/null; then
        # 更新现有值
        if [[ -n "$value" ]]; then
            sed -i.bak "s|^${key}=.*|${key}=${value}|" "$env_file"
            rm -f "${env_file}.bak"
        else
            # 清空值
            sed -i.bak "s|^${key}=.*|${key}=|" "$env_file"
            rm -f "${env_file}.bak"
        fi
    else
        # 添加新 key
        echo "${key}=${value}" >> "$env_file"
    fi
}

cmd_api_keys() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)
            cmd_api_keys_list "$@"
            ;;
        set)
            cmd_api_keys_set "$@"
            ;;
        get)
            cmd_api_keys_get "$@"
            ;;
        --help|-h)
            echo "用法: api.sh [--env ENV] api-keys <命令> [选项]"
            echo ""
            echo "管理外部服务 API Keys"
            echo ""
            echo "命令:"
            echo "  list                    列出所有 API Keys 配置状态"
            echo "  get <key>               获取指定 API Key 的值"
            echo "  set <key> <value>       设置 API Key"
            echo ""
            echo "支持的 API Keys:"
            echo "  YOUTUBE_API_KEY         YouTube Data API v3 Key"
            echo ""
            echo "示例:"
            echo "  api.sh api-keys list"
            echo "  api.sh api-keys set YOUTUBE_API_KEY your_api_key_here"
            echo "  api.sh api-keys get YOUTUBE_API_KEY"
            ;;
        *)
            print_error "Unknown api-keys subcommand: $subcommand"
            echo "使用 'api.sh api-keys --help' 查看帮助"
            return 1
            ;;
    esac
}

cmd_api_keys_list() {
    local env_file
    env_file=$(get_env_file_path)

    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    API Keys 配置状态                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [[ ! -f "$env_file" ]]; then
        print_warning ".env 文件不存在"
        print_info "请先运行: ./scripts/cyber-pulse.sh deploy"
        return 1
    fi

    echo -e "${BOLD}配置文件:${NC} $env_file"
    echo ""

    # YouTube API Key
    local yt_key
    yt_key=$(get_env_value "YOUTUBE_API_KEY")
    if [[ -n "$yt_key" ]]; then
        echo -e "  ${GREEN}✓${NC} YOUTUBE_API_KEY: ${YELLOW}********${NC} (${#yt_key} 字符)"
    else
        echo -e "  ${YELLOW}○${NC} YOUTUBE_API_KEY: ${CYAN}未配置${NC} (将使用 RSS Feed 降级)"
    fi

    echo ""
    echo -e "${BOLD}使用说明:${NC}"
    echo "  api.sh api-keys set YOUTUBE_API_KEY <your_key>  设置 YouTube API Key"
    echo "  api.sh api-keys get YOUTUBE_API_KEY             查看完整 Key 值"
}

cmd_api_keys_get() {
    local key="${1:-}"

    if [[ -z "$key" ]]; then
        print_error "请指定 API Key 名称"
        echo "用法: api.sh api-keys get <key>"
        echo "示例: api.sh api-keys get YOUTUBE_API_KEY"
        return 1
    fi

    local value
    value=$(get_env_value "$key")

    if [[ -n "$value" ]]; then
        echo "$value"
    else
        print_warning "API Key '$key' 未配置"
        return 1
    fi
}

cmd_api_keys_set() {
    local key="${1:-}"
    local value="${2:-}"

    if [[ -z "$key" ]]; then
        print_error "请指定 API Key 名称"
        echo "用法: api.sh api-keys set <key> <value>"
        echo "示例: api.sh api-keys set YOUTUBE_API_KEY your_key_here"
        return 1
    fi

    # 支持的 key 列表
    local supported_keys="YOUTUBE_API_KEY"
    if ! echo "$supported_keys" | grep -qw "$key"; then
        print_warning "Key '$key' 不是已知的外部服务 API Key"
        print_info "已知 API Keys: YOUTUBE_API_KEY"
        echo ""
        read -r -p "是否继续设置? (y/N): " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "操作已取消"
            return 0
        fi
    fi

    if [[ -z "$value" ]]; then
        print_error "请提供 API Key 值"
        echo "用法: api.sh api-keys set $key <value>"
        return 1
    fi

    set_env_value "$key" "$value"

    if [[ $? -eq 0 ]]; then
        print_success "已设置 $key"

        # 提示需要重启服务
        echo ""
        print_warning "注意: 需要重启服务才能生效"
        echo "  ./scripts/cyber-pulse.sh restart --env ${CURRENT_ENV:-prod}"
    fi
}


# ============================================
# 帮助信息
# ============================================

show_help() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 管理工具                           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "用法: api.sh [--env ENV] <命令> [选项]"
    echo ""
    echo -e "${BOLD}全局选项:${NC}"
    echo "  --env ENV              指定环境 (prod/dev/test)，默认使用当前环境"
    echo ""
    echo -e "${BOLD}命令:${NC}"
    echo "  configure [--env ENV]  配置 API URL 和 Admin Key"
    echo ""
    echo "  env <cmd>              环境管理"
    echo "    current              显示当前环境"
    echo "    list                 列出所有已配置的环境"
    echo "    switch ENV           切换到指定环境"
    echo ""
    echo "  sources <cmd>          情报源管理"
    echo "    list                 列出情报源"
    echo "    get <id>             获取情报源详情"
    echo "    create               创建情报源"
    echo "    update <id>          更新情报源"
    echo "    delete <id>          删除情报源"
    echo "    test <id>            测试连接"
    echo "    schedule <id>        设置调度"
    echo "    unschedule <id>      取消调度"
    echo "    import --file FILE   批量导入"
    echo "    export               导出配置"
    echo "    defaults             默认配置"
    echo ""
    echo "  jobs <cmd>             任务管理"
    echo "    list                 列出任务"
    echo "    get <id>             获取任务详情"
    echo "    run <source_id>      运行采集任务"
    echo "    delete <id>          删除失败任务"
    echo "    retry <id>           重试失败任务"
    echo "    cleanup [--days N]   清理旧任务"
    echo ""
    echo "  clients <cmd>          客户端管理"
    echo "    list                 列出客户端"
    echo "    get <id>             获取客户端详情"
    echo "    create               创建客户端"
    echo "    rotate <id>          轮换 API Key"
    echo "    suspend <id>         暂停客户端"
    echo "    activate <id>        激活客户端"
    echo "    delete <id>          删除客户端"
    echo ""
    echo "  logs [选项]            查看日志"
    echo "    --level LEVEL        日志级别过滤"
    echo "    --source SOURCE_ID   情报源过滤"
    echo "    --since TIME         时间过滤"
    echo ""
    echo "  diagnose               系统诊断"
    echo ""
    echo "  api-keys <cmd>         API Keys 管理"
    echo "    list                 列出 API Keys 配置状态"
    echo "    get <key>            获取 API Key 值"
    echo "    set <key> <value>    设置 API Key"
    echo ""
    echo -e "${BOLD}配置目录:${NC} $CONFIG_DIR"
    echo -e "${BOLD}环境配置:${NC} $ENV_DIR/"
    echo ""
    echo -e "${BOLD}示例:${NC}"
    echo "  api.sh configure --env dev --url http://localhost:8002 --key cp_live_xxx"
    echo "  api.sh env switch dev"
    echo "  api.sh --env prod sources list"
    echo "  api.sh jobs run src_xxxx"
}

# ============================================
# 主入口
# ============================================

main() {
    check_dependencies

    # 解析 --env 参数（全局选项）
    local filtered_args=()
    CURRENT_ENV=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --env)
                if [[ -n "${2:-}" ]]; then
                    if ! validate_env "$2"; then
                        die "无效的环境名: $2。有效值: ${VALID_ENVS[*]}"
                    fi
                    CURRENT_ENV="$2"
                    shift 2
                else
                    die "--env 需要环境名参数"
                fi
                ;;
            *)
                filtered_args+=("$1")
                shift
                ;;
        esac
    done

    # 如果没有通过 --env 指定，使用当前环境
    if [[ -z "$CURRENT_ENV" ]]; then
        CURRENT_ENV=$(get_current_env)
    fi

    # 使用过滤后的参数
    set -- "${filtered_args[@]}"

    local command="${1:-help}"
    shift || true

    case "$command" in
        configure)
            cmd_configure "$@"
            ;;
        env)
            cmd_env "$@"
            ;;
        sources)
            load_config
            cmd_sources "$@"
            ;;
        jobs)
            load_config
            cmd_jobs "$@"
            ;;
        clients)
            load_config
            cmd_clients "$@"
            ;;
        logs)
            load_config
            cmd_logs "$@"
            ;;
        diagnose)
            load_config
            cmd_diagnose
            ;;
        api-keys)
            cmd_api_keys "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"