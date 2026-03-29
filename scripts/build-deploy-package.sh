#!/usr/bin/env bash
#
# build-deploy-package.sh - 构建运维部署包
#
# 功能:
#   从完整代码库中提取运维人员所需的部署文件，生成轻量级部署包
#
# 使用:
#   ./scripts/build-deploy-package.sh [--version VERSION]
#
# 输出:
#   cyber-pulse-deploy-{VERSION}.tar.gz
#

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 默认版本号
VERSION="${1:-}"

# 输出文件名
if [[ -n "$VERSION" ]]; then
    OUTPUT_FILE="cyber-pulse-deploy-${VERSION}.tar.gz"
else
    OUTPUT_FILE="cyber-pulse-deploy-$(date +%Y%m%d%H%M%S).tar.gz"
fi

# 部署包包含的文件（不包含 src/ tests/ docs/）
DEPLOY_FILES=(
    "scripts/cyber-pulse.sh"
    "scripts/api.sh"
    "deploy/"
    "sources.yaml"
    "install-ops.sh"
)

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# 检查必需文件
check_required_files() {
    print_info "检查必需文件..."

    local missing=()
    for file in "${DEPLOY_FILES[@]}"; do
        if [[ ! -e "$PROJECT_ROOT/$file" ]] && [[ "$file" != "install-ops.sh" ]]; then
            missing+=("$file")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        print_error "缺少必需文件: ${missing[*]}"
        exit 1
    fi

    print_success "所有必需文件存在"
}

# 创建临时目录
create_temp_dir() {
    TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT
    print_info "临时目录: $TEMP_DIR"
}

# 复制文件到临时目录
copy_files() {
    print_info "复制部署文件..."

    mkdir -p "$TEMP_DIR/cyber-pulse"

    for file in "${DEPLOY_FILES[@]}"; do
        if [[ -e "$PROJECT_ROOT/$file" ]]; then
            # 创建父目录
            parent_dir=$(dirname "$file")
            if [[ "$parent_dir" != "." ]]; then
                mkdir -p "$TEMP_DIR/cyber-pulse/$parent_dir"
            fi
            cp -r "$PROJECT_ROOT/$file" "$TEMP_DIR/cyber-pulse/$file"
        fi
    done

    # 创建 sources.yaml 示例文件（如果不存在）
    if [[ ! -f "$TEMP_DIR/cyber-pulse/sources.yaml" ]]; then
        cat > "$TEMP_DIR/cyber-pulse/sources.yaml" << 'EOF'
# Cyber Pulse 情报源配置
# 格式参考: docs/source-config-examples.md

sources: []
EOF
    fi

    # 创建 .version 文件
    if [[ -n "$VERSION" ]]; then
        echo "$VERSION" > "$TEMP_DIR/cyber-pulse/.version"
        print_info "创建 .version 文件: $VERSION"
    fi

    print_success "文件复制完成"
}

# 创建 install-ops.sh（运维安装脚本）
create_install_ops() {
    print_info "创建运维安装脚本..."

    cat > "$TEMP_DIR/cyber-pulse/install-ops.sh" << 'INSTALL_SCRIPT'
#!/usr/bin/env bash
#
# Cyber Pulse 运维安装脚本
# 用于从部署包安装（非 git clone 方式）
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="${1:-cyber-pulse}"

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 运维安装"
    echo "========================================"
    echo ""

    # 检查当前目录是否为部署包目录
    if [[ ! -f "scripts/cyber-pulse.sh" ]]; then
        error "请在部署包根目录运行此脚本"
        exit 1
    fi

    info "安装目录: $INSTALL_DIR"

    # 如果指定了不同的安装目录，复制文件
    if [[ "$INSTALL_DIR" != "." ]] && [[ "$INSTALL_DIR" != "cyber-pulse" ]]; then
        info "复制文件到 $INSTALL_DIR..."
        mkdir -p "$INSTALL_DIR"
        cp -r scripts deploy sources.yaml "$INSTALL_DIR/" 2>/dev/null || true
        cd "$INSTALL_DIR"
    fi

    # 检查依赖
    info "检查依赖..."
    local missing=()

    command -v docker &>/dev/null || missing+=("docker")
    command -v docker-compose &>/dev/null || command -v docker &>/dev/null && docker compose version &>/dev/null || missing+=("docker-compose")
    command -v curl &>/dev/null || missing+=("curl")
    command -v jq &>/dev/null || missing+=("jq")

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "缺少依赖: ${missing[*]}"
        echo ""
        echo "安装依赖:"
        echo "  Docker:       https://docs.docker.com/get-docker/"
        echo "  Docker Compose: https://docs.docker.com/compose/install/"
        echo "  curl:         通常已预装"
        echo "  jq:           apt install jq / brew install jq"
        exit 1
    fi

    success "依赖检查通过"

    # 设置脚本权限
    chmod +x scripts/cyber-pulse.sh scripts/api.sh

    echo ""
    success "安装完成!"
    echo ""
    echo "下一步操作:"
    echo ""
    echo "  1. 部署服务:"
    echo "     ./scripts/cyber-pulse.sh deploy --env prod"
    echo ""
    echo "  2. 配置管理脚本:"
    echo "     ./scripts/api.sh configure"
    echo ""
    echo "  3. 管理命令:"
    echo "     ./scripts/api.sh diagnose"
    echo "     ./scripts/api.sh sources list"
    echo ""
}

main "$@"
INSTALL_SCRIPT

    chmod +x "$TEMP_DIR/cyber-pulse/install-ops.sh"
    print_success "运维安装脚本创建完成"
}

# 创建 README
create_readme() {
    print_info "创建部署包 README..."

    cat > "$TEMP_DIR/cyber-pulse/README.md" << 'EOF'
# Cyber Pulse 部署包

本部署包仅包含运维部署所需的文件，不包含源代码和测试文件。

## 目录结构

```
cyber-pulse/
├── scripts/
│   ├── cyber-pulse.sh      # 部署脚本
│   └── api.sh              # API 管理脚本
├── deploy/
│   ├── docker-compose.yml
│   └── init/
├── sources.yaml            # 情报源配置
├── install-ops.sh          # 运维安装脚本
└── README.md
```

## 快速开始

### 1. 安装

```bash
./install-ops.sh
```

### 2. 部署

```bash
./scripts/cyber-pulse.sh deploy --env prod
```

### 3. 配置 API 管理

```bash
./scripts/api.sh configure
```

### 4. 日常管理

```bash
./scripts/api.sh diagnose        # 系统诊断
./scripts/api.sh sources list    # 情报源列表
./scripts/api.sh jobs run src_xxx  # 运行采集
```

## 注意事项

- Admin API Key 在首次部署时自动生成并输出到终端
- 请妥善保存 Admin Key，忘记后需使用 `admin reset` 重置
- 详细文档: https://github.com/cyberstrat-forge/cyber-pulse
EOF

    print_success "README 创建完成"
}

# 打包
create_archive() {
    print_info "创建部署包..."

    cd "$TEMP_DIR"
    tar -czf "$PROJECT_ROOT/$OUTPUT_FILE" cyber-pulse

    local size
    size=$(du -h "$PROJECT_ROOT/$OUTPUT_FILE" | cut -f1)

    print_success "部署包创建完成: $OUTPUT_FILE ($size)"
}

# 显示完成信息
show_completion() {
    echo ""
    echo "========================================"
    print_success "部署包构建完成!"
    echo "========================================"
    echo ""
    echo "输出文件: $OUTPUT_FILE"
    echo ""
    echo "运维人员安装方式:"
    echo ""
    echo "  1. 下载部署包"
    echo "  2. 解压: tar -xzf $OUTPUT_FILE"
    echo "  3. 进入目录: cd cyber-pulse"
    echo "  4. 安装: ./install-ops.sh"
    echo ""
}

# 主函数
main() {
    echo ""
    echo "========================================"
    echo "   Cyber Pulse 部署包构建"
    echo "========================================"
    echo ""

    check_required_files
    create_temp_dir
    copy_files
    create_install_ops
    create_readme
    create_archive
    show_completion
}

main