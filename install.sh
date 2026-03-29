#!/bin/bash
#
# Cyber Pulse 一键安装脚本
# 仓库: https://github.com/cyberstrat-forge/cyber-pulse
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --version v1.2.0
#

set -e

# 默认配置
REPO_URL="https://github.com/cyberstrat-forge/cyber-pulse.git"
DEFAULT_DIR="cyber-pulse"
DEFAULT_BRANCH="main"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 输出函数
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# 显示帮助信息
show_help() {
    cat << EOF
Cyber Pulse 一键安装脚本

用法:
  $0 [选项]

选项:
  -d, --dir DIR       安装目录 (默认: ${DEFAULT_DIR})
  -v, --version TAG   安装指定版本标签 (如: v1.2.0)
  -b, --branch BRANCH 安装指定分支 (默认: ${DEFAULT_BRANCH})
  --type TYPE         用户类型: developer 或 ops (默认: developer)
                      - developer: 完整代码库 (git clone)
                      - ops: 仅部署文件 (轻量级)
  -h, --help          显示此帮助信息

示例:
  # 开发者安装（默认）- 获取完整代码库
  $0

  # 运维人员安装 - 仅获取部署文件
  $0 --type ops

  # 安装到指定目录
  $0 --dir /opt/cyber-pulse

  # 安装指定版本
  $0 --version v1.2.0

更多信息请访问: https://github.com/cyberstrat-forge/cyber-pulse
EOF
}

# 解析命令行参数
parse_args() {
    INSTALL_DIR="$DEFAULT_DIR"
    VERSION=""
    BRANCH="$DEFAULT_BRANCH"
    USER_TYPE="developer"  # developer 或 ops

    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            -v|--version)
                VERSION="$2"
                shift 2
                ;;
            -b|--branch)
                BRANCH="$2"
                shift 2
                ;;
            --type)
                USER_TYPE="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                error "未知选项: $1"
                echo ""
                show_help
                exit 1
                ;;
        esac
    done
}

# 检查依赖
check_dependencies() {
    info "检查依赖..."

    if ! command -v git &> /dev/null; then
        error "未找到 git，请先安装 git"
        echo ""
        echo "安装 git:"
        echo "  Debian/Ubuntu: sudo apt-get install git"
        echo "  CentOS/RHEL:   sudo yum install git"
        echo "  macOS:         brew install git"
        exit 1
    fi

    success "依赖检查通过"
}

# 检查目录
check_directory() {
    info "检查安装目录: ${INSTALL_DIR}"

    if [[ -d "${INSTALL_DIR}" ]]; then
        if [[ -n "$(ls -A "${INSTALL_DIR}" 2>/dev/null)" ]]; then
            error "目录 ${INSTALL_DIR} 已存在且不为空"
            echo ""
            echo "请选择其他目录，或手动删除现有目录:"
            echo "  rm -rf ${INSTALL_DIR}"
            exit 1
        fi
    fi

    success "目录检查通过"
}

# 克隆仓库
clone_repository() {
    info "克隆仓库..."

    if ! git clone "${REPO_URL}" "${INSTALL_DIR}"; then
        error "克隆仓库失败"
        exit 1
    fi

    success "仓库克隆成功"
}

# 切换版本
switch_version() {
    if [[ -n "${VERSION}" ]]; then
        info "切换到版本: ${VERSION}"

        cd "${INSTALL_DIR}"

        if ! git checkout "${VERSION}" 2>/dev/null; then
            warn "版本 ${VERSION} 不存在，保持在默认分支"
        else
            success "已切换到版本 ${VERSION}"
        fi

        cd - > /dev/null
    elif [[ "${BRANCH}" != "${DEFAULT_BRANCH}" ]]; then
        info "切换到分支: ${BRANCH}"

        cd "${INSTALL_DIR}"

        if ! git checkout "${BRANCH}" 2>/dev/null; then
            warn "分支 ${BRANCH} 不存在，保持在 ${DEFAULT_BRANCH}"
        else
            success "已切换到分支 ${BRANCH}"
        fi

        cd - > /dev/null
    fi
}

# 运维人员安装（下载轻量部署包）
install_ops_package() {
    info "运维模式: 下载部署包..."

    local download_url
    if [[ -n "${VERSION}" ]]; then
        download_url="https://github.com/cyberstrat-forge/cyber-pulse/releases/download/${VERSION}/cyber-pulse-deploy-${VERSION}.tar.gz"
    else
        download_url="https://github.com/cyberstrat-forge/cyber-pulse/releases/latest/download/cyber-pulse-deploy-latest.tar.gz"
    fi

    info "下载地址: ${download_url}"

    # 下载部署包
    local temp_file="/tmp/cyber-pulse-deploy.tar.gz"
    if ! curl -fsSL "${download_url}" -o "${temp_file}"; then
        error "下载部署包失败"
        echo ""
        echo "可能的原因:"
        echo "  1. 版本不存在"
        echo "  2. 网络问题"
        echo ""
        echo "请尝试使用开发者模式: $0 --type developer"
        exit 1
    fi

    # 解压
    info "解压部署包..."
    mkdir -p "${INSTALL_DIR}"
    if ! tar -xzf "${temp_file}" -C "$(dirname "${INSTALL_DIR}")"; then
        error "解压失败"
        rm -f "${temp_file}"
        exit 1
    fi

    # 清理临时文件
    rm -f "${temp_file}"

    # 自动部署（运维者模式）
    info "自动执行部署..."
    cd "${INSTALL_DIR}"
    if ./scripts/cyber-pulse.sh deploy --env prod; then
        success "部署完成"
    else
        warn "自动部署失败，请手动执行: ./scripts/cyber-pulse.sh deploy --env prod"
    fi
    cd - > /dev/null

    success "部署包安装完成"
}

# 显示完成信息
show_completion() {
    local install_path
    install_path="$(cd "${INSTALL_DIR}" 2>/dev/null && pwd)" || install_path="${INSTALL_DIR}"

    echo ""
    echo "========================================"
    success "Cyber Pulse 安装完成!"
    echo "========================================"
    echo ""
    echo "安装位置: ${install_path}"
    echo "用户类型: ${USER_TYPE}"
    echo ""
    echo "下一步操作:"
    echo ""

    if [[ "${USER_TYPE}" == "ops" ]]; then
        echo "  1. 进入项目目录:"
        echo "     cd ${INSTALL_DIR}"
        echo ""
        echo "  2. 部署服务:"
        echo "     ./scripts/cyber-pulse.sh deploy --env prod"
        echo ""
        echo "  3. 配置 API 管理:"
        echo "     ./scripts/api.sh configure"
        echo ""
    else
        echo "  1. 进入项目目录:"
        echo "     cd ${INSTALL_DIR}"
        echo ""
        echo "  2. 开发环境部署（本地构建）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env dev --local"
        echo ""
        echo "  3. 测试环境部署（本地构建）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env test --local"
        echo ""
        echo "  4. 生产环境部署（远程镜像）:"
        echo "     ./scripts/cyber-pulse.sh deploy --env prod"
        echo ""
    fi

    echo "API 管理:"
    echo "  ./scripts/api.sh configure       # 配置 API"
    echo "  ./scripts/api.sh diagnose         # 系统诊断"
    echo "  ./scripts/api.sh sources list     # 情报源列表"
    echo ""
    echo "详细文档: https://github.com/cyberstrat-forge/cyber-pulse#readme"
    echo ""
}

# 主函数
main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 安装脚本"
    echo "========================================"
    echo ""

    parse_args "$@"
    check_dependencies

    if [[ "${USER_TYPE}" == "ops" ]]; then
        # 运维人员安装
        check_directory
        install_ops_package
    else
        # 开发者安装
        check_directory
        clone_repository
        switch_version
    fi

    show_completion
}

main "$@"