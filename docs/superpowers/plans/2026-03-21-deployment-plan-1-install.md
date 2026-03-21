# 部署优化计划1：install.sh 一键安装脚本

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供一键安装脚本，用户可通过 curl 命令安装 cyber-pulse 到本地。

**Architecture:** 纯 Bash 脚本，负责检查依赖、克隆代码、切换版本、提示用户下一步操作。不涉及部署和服务启动。

**Tech Stack:** Bash, git

**依赖:** 无

---

## 文件结构

```
cyber-pulse/
├── install.sh              # 新建：一键安装脚本
└── README.md               # 修改：更新安装说明
```

---

## Task 1: 创建 install.sh 基础框架

**Files:**
- Create: `install.sh`

- [ ] **Step 1: 创建脚本文件并添加基础结构**

```bash
#!/bin/bash
#
# cyber-pulse 一键安装脚本
#
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --dir /path/to/install

set -e

# ============================================================================
# 配置
# ============================================================================

REPO_URL="https://github.com/cyberstrat-forge/cyber-pulse.git"
DEFAULT_DIR="cyber-pulse"
DEFAULT_BRANCH="main"

# 安装选项
INSTALL_DIR=""
INSTALL_VERSION=""
INSTALL_BRANCH=""

# ============================================================================
# 颜色输出
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# ============================================================================
# 参数解析
# ============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --version)
                INSTALL_VERSION="$2"
                shift 2
                ;;
            --branch)
                INSTALL_BRANCH="$2"
                shift 2
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 设置默认值
    INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"
    INSTALL_BRANCH="${INSTALL_BRANCH:-$DEFAULT_BRANCH}"
}

show_help() {
    cat << EOF
cyber-pulse 一键安装脚本

用法:
  curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- [选项]

选项:
  --dir DIR      安装目录 (默认: ./cyber-pulse)
  --version TAG  安装指定版本 (默认: 最新稳定版)
  --branch NAME  安装指定分支 (默认: main)
  --help, -h     显示此帮助信息

示例:
  # 默认安装
  curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash

  # 指定目录
  curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash -s -- --dir /opt/cyber-pulse

  # 安装指定版本
  curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash -s -- --version v1.2.0
EOF
}

# ============================================================================
# 依赖检查
# ============================================================================

check_dependencies() {
    log_info "检查依赖..."

    if ! command -v git &> /dev/null; then
        log_error "未找到 git，请先安装 git"
        echo ""
        echo "安装 git:"
        echo "  macOS:  brew install git"
        echo "  Ubuntu: sudo apt-get install git"
        echo "  CentOS: sudo yum install git"
        exit 1
    fi

    log_info "git 已安装: $(git --version)"
}

# ============================================================================
# 目录检查
# ============================================================================

check_directory() {
    log_info "检查安装目录: $INSTALL_DIR"

    if [ -d "$INSTALL_DIR" ]; then
        if [ "$(ls -A $INSTALL_DIR 2>/dev/null)" ]; then
            log_error "目录已存在且非空: $INSTALL_DIR"
            echo ""
            echo "解决方案:"
            echo "  1. 选择其他目录: install.sh --dir /path/to/other"
            echo "  2. 手动清理目录: rm -rf $INSTALL_DIR"
            exit 1
        else
            log_info "目录已存在且为空，将使用此目录"
        fi
    else
        log_info "目录不存在，将创建"
    fi
}

# ============================================================================
# 克隆仓库
# ============================================================================

clone_repository() {
    log_info "克隆仓库..."

    if ! git clone --branch "$INSTALL_BRANCH" "$REPO_URL" "$INSTALL_DIR" 2>&1; then
        log_error "克隆失败，请检查网络连接"
        echo ""
        echo "手动安装:"
        echo "  git clone $REPO_URL"
        exit 1
    fi

    log_info "克隆完成"
}

# ============================================================================
# 切换版本
# ============================================================================

switch_version() {
    if [ -n "$INSTALL_VERSION" ]; then
        log_info "切换到版本: $INSTALL_VERSION"
        cd "$INSTALL_DIR"

        if ! git checkout "$INSTALL_VERSION" 2>&1; then
            log_warn "版本 $INSTALL_VERSION 不存在，使用默认分支"
            echo ""
            echo "可用版本列表:"
            git tag -l | tail -10
            exit 1
        fi

        cd - > /dev/null
    fi
}

# ============================================================================
# 显示完成信息
# ============================================================================

show_completion() {
    local abs_dir
    abs_dir=$(cd "$INSTALL_DIR" && pwd)

    local version
    cd "$INSTALL_DIR"
    version=$(git describe --tags 2>/dev/null || echo "$INSTALL_BRANCH")
    cd - > /dev/null

    echo ""
    echo "╭─────────────────────────────────────────────────────────────╮"
    echo "│ ✅ cyber-pulse 安装成功                                      │"
    echo "├─────────────────────────────────────────────────────────────┤"
    echo "│ 安装目录: $abs_dir"
    echo "│ 版本:     $version"
    echo "│                                                             │"
    echo "│ 下一步：                                                   │"
    echo "│   cd $abs_dir"
    echo "│   ./scripts/cyber-pulse.sh deploy                          │"
    echo "│                                                             │"
    echo "│ 文档：https://github.com/cyberstrat-forge/cyber-pulse      │"
    echo "╰─────────────────────────────────────────────────────────────╯"
}

# ============================================================================
# 主流程
# ============================================================================

main() {
    parse_args "$@"
    check_dependencies
    check_directory
    clone_repository
    switch_version
    show_completion
}

main "$@"
```

- [ ] **Step 2: 设置脚本执行权限**

Run: `chmod +x install.sh`

- [ ] **Step 3: 测试帮助命令**

Run: `./install.sh --help`

Expected: 显示帮助信息

- [ ] **Step 4: 提交**

```bash
git add install.sh
git commit -m "$(cat <<'EOF'
feat(deploy): add install.sh one-click installation script

Add install.sh that provides:
- Dependency check (git)
- Directory validation
- Repository cloning
- Version switching (--version, --branch)
- User-friendly completion message

Usage:
  curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
  curl -fsSL ... | bash -s -- --dir /path/to/install --version v1.2.0

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 更新 README.md 安装说明

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新快速开始部分，添加一键安装说明**

在 README.md 的 "快速开始" 部分之前添加：

```markdown
### 一键安装

```bash
# 安装到默认目录 (./cyber-pulse)
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash

# 指定安装目录
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --dir /path/to/install

# 安装完成后部署
cd cyber-pulse
./scripts/cyber-pulse.sh deploy
```

安装选项：
- `--dir DIR` - 指定安装目录
- `--version TAG` - 安装指定版本
- `--branch NAME` - 安装指定分支
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: add one-click installation instructions to README

Update quick start section with install.sh usage and options.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准

- [ ] `./install.sh --help` 显示帮助信息
- [ ] `./install.sh --dir /tmp/test-install` 成功克隆到指定目录
- [ ] 目录已存在且非空时报错退出
- [ ] git 未安装时报错并提示安装方法
- [ ] 安装完成后显示下一步操作提示