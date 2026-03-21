#!/usr/bin/env bash
#
# check-update.sh - 检查更新
#
# 功能:
#   - 从 GitHub Releases API 获取最新版本
#   - 比较当前版本和最新版本
#   - 显示更新提醒和 release notes URL
#
# 用法:
#   check-update.sh [--json]
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 配置
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GITHUB_REPO="cyberstrat-forge/cyber-pulse"
GITHUB_API_URL="https://api.github.com/repos/$GITHUB_REPO/releases/latest"

# 打印函数
print_step() { echo -e "${BLUE}[→]${NC} $1" >&2; }
print_success() { echo -e "${GREEN}[✓]${NC} $1" >&2; }
print_error() { echo -e "${RED}[✗]${NC} $1" >&2; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1" >&2; }
print_info() { echo -e "${BLUE}[i]${NC} $1" >&2; }

# 获取当前版本
get_current_version() {
    local version_file="$PROJECT_ROOT/.version"

    if [[ -f "$version_file" ]]; then
        cat "$version_file"
    else
        # 尝试从 git 获取
        cd "$PROJECT_ROOT"
        local version
        version=$(git describe --tags --always 2>/dev/null || echo "unknown")
        echo "$version"
    fi
}

# 获取最新版本信息
get_latest_version() {
    local json_output="${1:-false}"

    print_step "正在检查更新..."

    # 使用 curl 获取 GitHub API
    local response
    local http_code

    if command -v curl &>/dev/null; then
        response=$(curl -s -w "\n%{http_code}" "$GITHUB_API_URL" 2>/dev/null)
        http_code=$(echo "$response" | tail -n1)
        response=$(echo "$response" | sed '$d')
    elif command -v wget &>/dev/null; then
        response=$(wget -qO- "$GITHUB_API_URL" 2>/dev/null)
        http_code=$?
        if [[ $http_code -eq 0 ]]; then
            http_code=200
        fi
    else
        print_error "需要 curl 或 wget 来检查更新"
        return 1
    fi

    # 检查 HTTP 状态码
    if [[ "$http_code" != "200" ]]; then
        print_error "无法获取版本信息 (HTTP $http_code)"
        return 1
    fi

    # 解析 JSON
    local latest_version
    local release_name
    local release_url
    local published_at
    local release_notes

    if command -v jq &>/dev/null; then
        latest_version=$(echo "$response" | jq -r '.tag_name // empty')
        release_name=$(echo "$response" | jq -r '.name // empty')
        release_url=$(echo "$response" | jq -r '.html_url // empty')
        published_at=$(echo "$response" | jq -r '.published_at // empty')
        release_notes=$(echo "$response" | jq -r '.body // empty' | head -c 500)
    else
        # 简单解析（不依赖 jq）
        latest_version=$(echo "$response" | grep -o '"tag_name"[^,]*' | cut -d'"' -f4)
        release_name=$(echo "$response" | grep -o '"name"[^,]*' | head -1 | cut -d'"' -f4)
        release_url=$(echo "$response" | grep -o '"html_url"[^,]*' | cut -d'"' -f4)
        published_at=$(echo "$response" | grep -o '"published_at"[^,]*' | cut -d'"' -f4)
    fi

    # 验证获取到的信息
    if [[ -z "$latest_version" ]]; then
        print_error "无法解析版本信息"
        return 1
    fi

    # 输出结果
    if [[ "$json_output" == "true" ]]; then
        echo "{\"current_version\":\"$(get_current_version)\",\"latest_version\":\"$latest_version\",\"release_url\":\"$release_url\",\"published_at\":\"$published_at\"}"
    else
        echo "LATEST_VERSION=$latest_version"
        echo "RELEASE_NAME=$release_name"
        echo "RELEASE_URL=$release_url"
        echo "PUBLISHED_AT=$published_at"
        if [[ -n "$release_notes" ]]; then
            echo "RELEASE_NOTES=$release_notes"
        fi
    fi
}

# 比较版本号
# 返回: 0 = 相等, 1 = current > latest, 2 = current < latest
compare_versions() {
    local current="$1"
    local latest="$2"

    # 移除 v 前缀
    current=${current#v}
    latest=${latest#v}

    # 如果当前版本未知，认为需要更新
    if [[ "$current" == "unknown" ]]; then
        return 2
    fi

    # 比较版本
    if [[ "$current" == "$latest" ]]; then
        return 0
    fi

    # 使用 sort -V 比较
    local sorted
    sorted=$(printf '%s\n%s\n' "$current" "$latest" | sort -V | tail -n1)

    if [[ "$sorted" == "$current" ]]; then
        return 1  # current > latest (开发版本)
    else
        return 2  # current < latest (需要更新)
    fi
}

# 显示更新信息
show_update_info() {
    local current_version="$1"
    local latest_version="$2"
    local release_url="$3"
    local published_at="$4"

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${GREEN}  有新版本可用!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  当前版本:     ${YELLOW}$current_version${NC}"
    echo -e "  最新版本:     ${GREEN}$latest_version${NC}"

    if [[ -n "$published_at" && "$published_at" != "null" ]]; then
        local pub_date
        pub_date=$(echo "$published_at" | cut -dT -f1)
        echo -e "  发布日期:     $pub_date"
    fi

    echo ""
    echo -e "  ${BOLD}Release Notes:${NC}"
    echo -e "  ${CYAN}$release_url${NC}"
    echo ""
    echo -e "${YELLOW}───────────────────────────────────────────────────────────────${NC}"
    echo -e "  ${BOLD}升级命令:${NC}"
    echo -e "  cyber-pulse.sh upgrade"
    echo -e "${YELLOW}───────────────────────────────────────────────────────────────${NC}"
}

# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "检查 Cyber Pulse 更新。"
    echo ""
    echo "选项:"
    echo "  --json       以 JSON 格式输出"
    echo "  --help, -h   显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0              检查更新"
    echo "  $0 --json       以 JSON 格式输出"
}

# 主函数
main() {
    local json_output="false"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json)
                json_output="true"
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

    # 获取当前版本
    local current_version
    current_version=$(get_current_version)

    # 获取最新版本信息
    local version_info
    version_info=$(get_latest_version "$json_output")

    if [[ $? -ne 0 ]]; then
        exit 1
    fi

    # JSON 输出模式
    if [[ "$json_output" == "true" ]]; then
        echo "$version_info"
        exit 0
    fi

    # 解析版本信息
    local latest_version release_url published_at
    latest_version=$(echo "$version_info" | grep "^LATEST_VERSION=" | cut -d= -f2)
    release_url=$(echo "$version_info" | grep "^RELEASE_URL=" | cut -d= -f2)
    published_at=$(echo "$version_info" | grep "^PUBLISHED_AT=" | cut -d= -f2)

    # 比较版本 (使用 subshell 避免 set -e 触发)
    cmp_result=0
    compare_versions "$current_version" "$latest_version" || cmp_result=$?

    echo ""

    case $cmp_result in
        0)
            print_success "当前已是最新版本: $current_version"
            ;;
        1)
            print_info "当前版本 ($current_version) 高于最新发布版本 ($latest_version)"
            print_info "可能是开发版本或预发布版本"
            ;;
        2)
            show_update_info "$current_version" "$latest_version" "$release_url" "$published_at"
            ;;
    esac
}

main "$@"