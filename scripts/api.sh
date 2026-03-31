#!/usr/bin/env bash
#
# api.sh - Cyber Pulse API 管理脚本
#
# 功能:
#   配置 API 连接、管理情报源、任务、客户端、日志、诊断
#
# 使用:
#   ./scripts/api.sh configure           # 配置 API URL 和 Admin Key
#   ./scripts/api.sh sources list        # 列出情报源
#   ./scripts/api.sh jobs run <src_id>   # 运行采集任务
#   ./scripts/api.sh diagnose            # 系统诊断
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
CONFIG_FILE="$CONFIG_DIR/config"

# 默认 API URL
DEFAULT_API_URL="http://localhost:8000"

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

# 加载配置
load_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        die "Configuration not found. Run './scripts/api.sh configure' first."
    fi

    # shellcheck source=/dev/null
    source "$CONFIG_FILE"

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
    local non_interactive="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
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
                echo "  --url URL      API URL (非交互式)"
                echo "  --key KEY      Admin API Key (非交互式)"
                echo ""
                echo "示例:"
                echo "  api.sh configure                              # 交互式配置"
                echo "  api.sh configure --url http://localhost:8000 --key cp_live_xxx"
                return 0
                ;;
            *)
                shift
                ;;
        esac
    done

    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 配置                               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # 创建配置目录
    mkdir -p "$CONFIG_DIR"

    # 交互式模式
    if [[ "$non_interactive" != "true" ]]; then
        # 提示输入 API URL
        echo -e "${BLUE}API URL${NC} (按 Enter 使用默认值: $DEFAULT_API_URL)"
        read -r -p "> " input_api_url
        local final_api_url="${input_api_url:-$DEFAULT_API_URL}"

        # 提示输入 Admin Key
        echo ""
        echo -e "${BLUE}Admin API Key${NC} (格式: cp_live_xxxx)"
        read -r -p "> " input_admin_key

        if [[ -z "$input_admin_key" ]]; then
            die "Admin API Key 不能为空"
        fi
    else
        # 非交互式模式：使用参数
        local final_api_url="${input_api_url:-$DEFAULT_API_URL}"

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

    # 写入配置文件
    cat > "$CONFIG_FILE" << EOF
# Cyber Pulse API Configuration
# Generated by: api.sh configure
# Date: $(date '+%Y-%m-%d %H:%M:%S')

api_url=${final_api_url}
admin_key=${input_admin_key}
EOF

    chmod 600 "$CONFIG_FILE"

    echo ""
    print_success "配置已保存到: $CONFIG_FILE"
    print_info "文件权限: 600"
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
    data=$(jq -n \
        --arg name "$name" \
        --arg type "$connector_type" \
        --arg url "$url" \
        --arg tier "$tier" \
        --argjson needs_full_fetch "${needs_full_fetch:-false}" \
        '{name: $name, connector_type: $type, config: {feed_url: $url}} + if $tier != "" then {tier: $tier} else {} end + if $needs_full_fetch then {needs_full_fetch: $needs_full_fetch} else {} end'
    )

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

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)     data=$(echo "$data" | jq --arg v "$2" '. + {name: $v}'); shift 2 ;;
            --url)      data=$(echo "$data" | jq --arg v "$2" '.config = (.config // {}) + {feed_url: $v}'); shift 2 ;;
            --tier)     data=$(echo "$data" | jq --arg v "$2" '. + {tier: $v}'); shift 2 ;;
            --status)   data=$(echo "$data" | jq --arg v "$2" '. + {status: $v}'); shift 2 ;;
            --score)    data=$(echo "$data" | jq --argjson v "$2" '. + {score: $v}'); shift 2 ;;
            --needs-full-fetch) data=$(echo "$data" | jq --argjson v "$2" '. + {needs_full_fetch: $v}'); shift 2 ;;
            --schedule-interval) data=$(echo "$data" | jq --argjson v "$2" '. + {schedule_interval: $v}'); shift 2 ;;
            --config)   data=$(echo "$data" | jq --argjson v "$2" '. + {config: $v}'); shift 2 ;;
            *)          shift ;;
        esac
    done

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
# 帮助信息
# ============================================

show_help() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           Cyber Pulse API 管理工具                           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "用法: api.sh <命令> [选项]"
    echo ""
    echo -e "${BOLD}命令:${NC}"
    echo "  configure              配置 API URL 和 Admin Key"
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
    echo -e "${BOLD}配置文件:${NC} $CONFIG_FILE"
    echo -e "${BOLD}示例:${NC}"
    echo "  api.sh configure"
    echo "  api.sh sources list"
    echo "  api.sh jobs run src_xxxx"
    echo "  api.sh diagnose"
}

# ============================================
# 主入口
# ============================================

main() {
    check_dependencies

    local command="${1:-help}"
    shift || true

    case "$command" in
        configure)
            cmd_configure "$@"
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