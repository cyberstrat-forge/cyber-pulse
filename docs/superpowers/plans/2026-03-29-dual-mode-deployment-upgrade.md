# 双模式部署与升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现开发者/运维者双模式部署与升级，支持 Worktree 开发模式，运维者一键安装部署。

**Architecture:**
- 模式检测：通过 `.git` 存在与否识别开发者/运维者模式，支持 worktree（`.git` 为文件）
- 版本管理：开发者从 git tag 获取版本，运维者从 `.version` 文件获取
- 升级流程：开发者仅 main 分支可用 upgrade，特性分支使用 `deploy --local`

**Tech Stack:** Bash, Docker Compose, GitHub Actions, Python

---

## 文件结构

| 文件 | 状态 | 职责 |
|------|------|------|
| `scripts/cyber-pulse.sh` | 修改 | 模式检测、版本获取、upgrade 分支检测 |
| `deploy/init/check-deps.sh` | 修改 | git 检查改为非阻塞警告 |
| `deploy/init/generate-env.sh` | 修改 | 新增 CYBER_PULSE_VERSION 配置项 |
| `install.sh` | 修改 | 运维者模式自动执行部署 |
| `src/cyberpulse/__init__.py` | 修改 | 版本号动态读取 |
| `Dockerfile` | 修改 | 构建时注入版本信息 |
| `.github/workflows/docker-publish.yml` | 修改 | 新增部署包构建和发布 |
| `scripts/build-deploy-package.sh` | 修改 | 创建 .version 文件 |

---

## Task 1: 修改 check-deps.sh - git 检查改为非阻塞警告

**Files:**
- Modify: `deploy/init/check-deps.sh:60-79`

**背景:** 设计方案要求运维者模式下 git 检查应为信息提示而非错误。

- [ ] **Step 1: 修改 check_git_repo 函数**

将 `print_error "不是 Git 仓库"` 改为 `print_info "非 Git 仓库（运维者模式）"`。

```bash
# deploy/init/check-deps.sh 第 77-79 行
# 修改前:
    else
        print_error "不是 Git 仓库"
    fi

# 修改后:
    else
        print_info "非 Git 仓库（运维者模式）"
    fi
```

- [ ] **Step 2: 验证修改**

```bash
# 检查语法
bash -n deploy/init/check-deps.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add deploy/init/check-deps.sh
git commit -m "fix(check-deps): change git check to non-blocking info for ops mode"
```

---

## Task 2: 修改 generate-env.sh - 新增 CYBER_PULSE_VERSION 配置项

**Files:**
- Modify: `deploy/init/generate-env.sh:127-163`

**背景:** 运维者模式需要通过 `.env` 中的 `CYBER_PULSE_VERSION` 控制镜像版本。

- [ ] **Step 1: 添加 CYBER_PULSE_VERSION 配置项**

在 `generate_env_file` 函数中，找到 `cat > "$ENV_FILE" << EOF` 部分，在 `ENVIRONMENT=production` 后添加：

```bash
# deploy/init/generate-env.sh
# 在第 162 行 ENVIRONMENT=production 后添加:

# 镜像版本（运维者模式使用）
CYBER_PULSE_VERSION=latest
```

完整修改后的 EOF 块末尾应为：

```bash
# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/cyber_pulse.log

# 环境
ENVIRONMENT=production

# 镜像版本（运维者模式使用）
CYBER_PULSE_VERSION=latest
EOF
```

- [ ] **Step 2: 验证修改**

```bash
# 检查语法
bash -n deploy/init/generate-env.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add deploy/init/generate-env.sh
git commit -m "feat(generate-env): add CYBER_PULSE_VERSION config for ops mode"
```

---

## Task 3: 修改 cyber-pulse.sh - 新增模式检测和版本获取函数

**Files:**
- Modify: `scripts/cyber-pulse.sh`

**背景:** 需要新增 `is_git_repo`、`detect_mode`、`get_current_version`、`get_latest_version` 函数，以及版本比较函数。

- [ ] **Step 1: 在工具函数区域添加新函数**

在 `scripts/cyber-pulse.sh` 第 100 行（`die` 函数后）添加：

```bash
# ============================================
# 模式检测函数
# ============================================

# 检测是否为 git 仓库（支持 worktree）
is_git_repo() {
    # worktree 情况: .git 是文件而非目录
    # 普通 clone: .git 是目录
    [[ -d "$PROJECT_ROOT/.git" ]] || [[ -f "$PROJECT_ROOT/.git" ]]
}

# 检测运行模式
detect_mode() {
    # 1. 优先使用显式指定
    if [[ -n "${CYBER_PULSE_MODE:-}" ]]; then
        echo "$CYBER_PULSE_MODE"
        return
    fi

    # 2. 自动检测
    if is_git_repo; then
        echo "developer"
    else
        echo "ops"
    fi
}

# 获取当前版本
get_current_version() {
    local mode
    mode=$(detect_mode)

    case "$mode" in
        developer)
            # 检查是否在特性分支（非 main/master）
            local branch
            branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo "")
            if [[ -n "$branch" && "$branch" != "main" && "$branch" != "master" ]]; then
                # 特性分支: 显示分支名 + 短 commit
                local commit
                commit=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
                echo "$branch@$commit"
                return
            fi

            # main/master: 优先从 git tag 获取
            local git_version
            git_version=$(git -C "$PROJECT_ROOT" describe --tags --always 2>/dev/null || echo "")
            if [[ -n "$git_version" ]]; then
                echo "$git_version"
                return
            fi
            # Fallback: 继续尝试其他来源
            ;;
    esac

    # 开发者/运维者共同 fallback 路径
    # 从 .version 文件
    if [[ -f "$PROJECT_ROOT/.version" ]]; then
        local version_content
        version_content=$(cat "$PROJECT_ROOT/.version" 2>/dev/null)
        if [[ -n "$version_content" && "$version_content" != "" ]]; then
            echo "$version_content"
            return
        fi
    fi

    # 从运行中的 API 获取
    local api_version
    api_version=$(curl -s localhost:8000/health 2>/dev/null | jq -r '.version' 2>/dev/null)
    if [[ -n "$api_version" && "$api_version" != "null" ]]; then
        echo "$api_version"
        return
    fi

    echo "unknown"
}

# 获取最新版本
get_latest_version() {
    local response tag
    response=$(curl -sf https://api.github.com/repos/cyberstrat-forge/cyber-pulse/releases/latest 2>/dev/null)
    if [[ -z "$response" ]]; then
        echo "error:网络请求失败"
        return 1
    fi
    tag=$(echo "$response" | jq -r '.tag_name' 2>/dev/null)
    if [[ -z "$tag" || "$tag" == "null" ]]; then
        echo "error:解析失败"
        return 1
    fi
    echo "$tag"
}

# 比较版本号
# 返回: 0 = 相等, 1 = current > latest, 2 = current < latest
version_compare() {
    local current="$1"
    local latest="$2"

    # 移除 v 前缀
    current=${current#v}
    latest=${latest#v}

    if [[ "$current" == "$latest" ]]; then
        return 0
    fi

    # 使用 sort -V 比较
    local sorted
    sorted=$(printf '%s\n%s\n' "$current" "$latest" | sort -V | tail -n1)

    if [[ "$sorted" == "$current" ]]; then
        return 1  # current > latest
    else
        return 2  # current < latest
    fi
}

# 判断 current < latest
version_lt() {
    version_compare "$1" "$2"
    [[ $? -eq 2 ]]
}
```

- [ ] **Step 2: 验证语法**

```bash
bash -n scripts/cyber-pulse.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add scripts/cyber-pulse.sh
git commit -m "feat(cyber-pulse): add mode detection and version functions"
```

---

## Task 4: 修改 cyber-pulse.sh - upgrade 命令分支检测

**Files:**
- Modify: `scripts/cyber-pulse.sh:616-663`

**背景:** upgrade 命令需要检测是否在特性分支，特性分支应提示退出并建议使用 `deploy --local`。

- [ ] **Step 1: 修改 cmd_upgrade 函数开头**

将 `scripts/cyber-pulse.sh` 第 616-663 行修改为：

```bash
cmd_upgrade() {
    local target_version=""
    local force="false"
    local skip_snapshot="false"
    local dry_run="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version|-v)
                target_version="$2"
                shift 2
                ;;
            --force|-f)
                force="true"
                shift
                ;;
            --skip-snapshot)
                skip_snapshot="true"
                shift
                ;;
            --dry-run)
                dry_run="true"
                shift
                ;;
            --help|-h)
                print_upgrade_help
                exit 0
                ;;
            *)
                print_error "未知参数: $1"
                print_upgrade_help
                exit 1
                ;;
        esac
    done

    print_banner
    print_header "升级 Cyber Pulse"

    # 1. 模式和分支检测
    local mode branch
    mode=$(detect_mode)
    print_info "检测到模式: $mode"

    # 开发者模式: 检查是否在特性分支
    if [[ "$mode" == "developer" ]]; then
        branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo "")
        if [[ -n "$branch" && "$branch" != "main" && "$branch" != "master" ]]; then
            print_error "当前在特性分支 '$branch'，upgrade 不适用"
            print_info "如需部署当前代码，请使用: ./scripts/cyber-pulse.sh deploy --local"
            exit 1
        fi
    fi

    # 运维者模式: 检查 .version 文件
    if [[ "$mode" == "ops" ]]; then
        if [[ ! -f "$PROJECT_ROOT/.version" ]]; then
            print_warning ".version 文件不存在，无法确定当前版本"
        fi
    fi

    # 2. 预检查
    print_step "执行预检查..."
```

- [ ] **Step 2: 修改原有 git 仓库检查**

将第 659-662 行的 git 检查删除（已在上面处理）：

```bash
# 删除以下代码:
    # 检查 git 仓库
    if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
        die "当前目录不是 git 仓库，无法使用 upgrade 命令"
    fi
```

- [ ] **Step 3: 验证语法**

```bash
bash -n scripts/cyber-pulse.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 4: Commit**

```bash
git add scripts/cyber-pulse.sh
git commit -m "feat(upgrade): add branch detection for developer mode"
```

---

## Task 5: 修改 cyber-pulse.sh - deploy 命令写入 .version 文件

**Files:**
- Modify: `scripts/cyber-pulse.sh`

**背景:** 部署成功后需要写入 `.version` 文件，用于版本追踪。

- [ ] **Step 1: 找到 cmd_deploy 函数的成功结尾位置**

在 `cmd_deploy` 函数中，找到部署成功的输出位置，添加写入 `.version` 文件的逻辑。

搜索 `print_success "部署完成"` 或类似的成功提示，在其前面添加：

```bash
# 写入 .version 文件
write_version_file() {
    local mode version
    mode=$(detect_mode)

    if [[ "$mode" == "developer" ]]; then
        # 从 git 获取版本
        version=$(git -C "$PROJECT_ROOT" describe --tags --always 2>/dev/null || echo "unknown")
    else
        # 运维者模式: 从 .env 或参数获取
        version="${CYBER_PULSE_VERSION:-latest}"
    fi

    echo "$version" > "$PROJECT_ROOT/.version"
    print_info "版本信息已写入: .version ($version)"
}
```

然后在 `cmd_deploy` 函数成功结束前调用：

```bash
    # 写入版本信息
    write_version_file

    print_success "部署完成"
```

- [ ] **Step 2: 验证语法**

```bash
bash -n scripts/cyber-pulse.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add scripts/cyber-pulse.sh
git commit -m "feat(deploy): write .version file after successful deployment"
```

---

## Task 6: 修改 __init__.py - 版本号动态读取

**Files:**
- Modify: `src/cyberpulse/__init__.py`

**背景:** 当前版本号硬编码为 `"1.3.0"`，需要从环境变量或 `.version` 文件动态读取。

- [ ] **Step 1: 修改 __init__.py**

```python
# src/cyberpulse/__init__.py
import os
from pathlib import Path


def _get_version() -> str:
    """获取版本号，优先级：环境变量 > .version 文件 > 默认值"""
    # 1. 从环境变量获取（Docker 构建时注入）
    if os.environ.get("APP_VERSION"):
        return os.environ["APP_VERSION"]

    # 2. 从 .version 文件获取
    version_file = Path(__file__).parent.parent.parent / ".version"
    if version_file.exists():
        version = version_file.read_text().strip()
        if version:
            return version

    # 3. 默认值（开发时使用）
    return "1.5.0"


__version__ = _get_version()
__author__ = "老罗"

from .config import settings
from .database import Base, SessionLocal, engine, get_db

__all__ = [
    "__version__",
    "__author__",
    "settings",
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
]
```

- [ ] **Step 2: 验证语法**

```bash
python3 -c "from src.cyberpulse import __version__; print(__version__)"
```

Expected: 输出版本号（如 `1.5.0` 或 `.version` 文件内容）

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/__init__.py
git commit -m "feat: dynamic version from .version file or env var"
```

---

## Task 7: 修改 Dockerfile - 构建时注入版本信息

**Files:**
- Modify: `Dockerfile`

**背景:** Docker 构建时需要注入版本信息到环境变量，供应用读取。

- [ ] **Step 1: 添加 ARG 和 ENV**

在 `Dockerfile` 第 70 行（`ENV PYTHONUNBUFFERED=1` 附近）添加：

```dockerfile
# Dockerfile
# 在第 70 行附近，ENV PYTHONUNBUFFERED=1 之后添加:

# 构建参数：版本号
ARG APP_VERSION=latest
ENV APP_VERSION=$APP_VERSION
```

- [ ] **Step 2: 验证 Dockerfile 语法**

```bash
docker build --help | head -1  # 确认 docker 可用
```

Expected: 显示 docker build 帮助信息

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): inject APP_VERSION at build time"
```

---

## Task 8: 修改 GitHub Actions - 新增部署包构建和发布

**Files:**
- Modify: `.github/workflows/docker-publish.yml`

**背景:** 需要在 CI/CD 中构建部署包并发布到 GitHub Release。

- [ ] **Step 1: 添加部署包构建步骤**

在 `.github/workflows/docker-publish.yml` 的 `build` job 末尾（`Image pushed successfully` 步骤后）添加：

```yaml
      - name: Build deploy package
        run: |
          chmod +x scripts/build-deploy-package.sh
          ./scripts/build-deploy-package.sh --version ${{ steps.version.outputs.version }}

      - name: Upload deploy package to Release
        uses: softprops/action-gh-release@v1
        if: startsWith(github.ref, 'refs/tags/')
        with:
          files: cyber-pulse-deploy-*.tar.gz
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))" && echo "YAML 语法正确"
```

Expected: 输出 "YAML 语法正确"

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker-publish.yml
git commit -m "feat(ci): add deploy package build and release"
```

---

## Task 9: 修改 build-deploy-package.sh - 创建 .version 文件

**Files:**
- Modify: `scripts/build-deploy-package.sh:108-111`

**背景:** 部署包需要包含 `.version` 文件。

- [ ] **Step 1: 在 copy_files 函数中添加 .version 创建**

在 `scripts/build-deploy-package.sh` 的 `copy_files` 函数中，在 `print_success "文件复制完成"` 之前添加：

```bash
# deploy/init/generate-env.sh 第 108-111 行
# 在 print_success "文件复制完成" 之前添加:

    # 创建 .version 文件
    if [[ -n "$VERSION" ]]; then
        echo "$VERSION" > "$TEMP_DIR/cyber-pulse/.version"
        print_info "创建 .version 文件: $VERSION"
    fi

    print_success "文件复制完成"
```

- [ ] **Step 2: 验证语法**

```bash
bash -n scripts/build-deploy-package.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add scripts/build-deploy-package.sh
git commit -m "feat(build-deploy): create .version file in deploy package"
```

---

## Task 10: 修改 install.sh - 运维者模式自动执行部署

**Files:**
- Modify: `install.sh:225-228`

**背景:** 设计方案要求运维者模式下载后自动执行部署。

- [ ] **Step 1: 在 install_ops_package 函数末尾添加自动部署**

在 `install.sh` 的 `install_ops_package` 函数中，在 `success "部署包安装完成"` 之前添加自动部署逻辑：

```bash
# install.sh 第 225-228 行
# 修改 install_ops_package 函数末尾，在 success 输出之前添加:

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

- [ ] **Step 2: 验证语法**

```bash
bash -n install.sh && echo "语法正确"
```

Expected: 输出 "语法正确"

- [ ] **Step 3: Commit**

```bash
git add install.sh
git commit -m "feat(install): auto deploy for ops mode"
```

---

## Task 11: 更新项目 README.md - 双模式部署说明

**Files:**
- Modify: `README.md`

**背景:** 需要更新 README.md 以反映双模式部署（开发者/运维者）的设计。

- [ ] **Step 1: 更新"部署方式"章节**

将 `README.md` 第 41-68 行的部署方式章节修改为：

```markdown
### 部署方式

项目支持两种用户类型的部署：

| 用户类型 | 获取方式 | 镜像来源 | 适用场景 |
|----------|----------|----------|----------|
| **开发者** | git clone 完整代码 | 本地构建 | 开发测试、PR 验证 |
| **运维者** | 下载部署包 | 远程拉取 | 生产环境、测试环境 |

#### 开发者模式

适用于开发测试和 PR 验证场景，详见 [本地部署指南](./docs/local-deployment-guide.md)。

```bash
# 克隆仓库
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse

# 本地构建并部署测试环境
./scripts/cyber-pulse.sh deploy --env dev --local

# 或在 Worktree 特性分支开发
cd .worktrees/feature-xxx
./scripts/cyber-pulse.sh deploy --env dev --local
```

#### 运维者模式

适用于生产环境和测试环境，一键安装部署。

```bash
# 安装并自动部署
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops

# 或指定版本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops --version v1.5.0
```

> 💡 **加速提示**：镜像托管在阿里云容器镜像仓库，中国用户无需配置镜像加速即可快速拉取。
```

- [ ] **Step 2: 添加版本管理说明**

在 README.md 中添加版本管理章节：

```markdown
## 版本管理

### 查看当前版本

```bash
# 开发者模式
git describe --tags

# 运维者模式
cat .version
```

### 升级版本

```bash
# 仅适用于 main/master 分支
./scripts/cyber-pulse.sh upgrade

# 特性分支开发时，使用 deploy 部署当前代码
./scripts/cyber-pulse.sh deploy --local
```
```

- [ ] **Step 3: 验证文档格式**

```bash
head -100 README.md
```

Expected: 显示更新后的 README.md 内容

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for dual-mode deployment"
```

---

## Task 12: 更新本地部署指南 - 完善 Worktree 开发模式

**Files:**
- Modify: `docs/local-deployment-guide.md`

**背景:** 需要补充 Worktree 开发模式的说明，与设计方案保持一致。

- [ ] **Step 1: 添加 Worktree 开发模式章节**

在 `docs/local-deployment-guide.md` 开头添加：

```markdown
# 本地测试环境部署指南（Worktree）

本文档指导如何在 Git Worktree 环境中部署测试环境，用于 PR 验证和开发测试。

## 开发模式说明

遵循 `superpowers:subagent-driven-development` 工作流，开发者在 Worktree 特性分支上开发：

| 场景 | 分支 | 操作 |
|------|------|------|
| **Worktree 开发** | 特性分支 | `deploy --local` 部署当前代码，**不使用 upgrade** |
| **主分支维护** | main/master | `deploy` 部署，`upgrade` 升级到最新版本 |

> ⚠️ **重要**：在特性分支上执行 `upgrade` 命令会提示退出，建议使用 `deploy --local` 部署当前代码。
```

- [ ] **Step 2: 添加版本显示说明**

在"命令详解"章节后添加：

```markdown
### 版本显示

```bash
# 在 main 分支
./scripts/cyber-pulse.sh status
# 显示版本: v1.5.0

# 在特性分支
./scripts/cyber-pulse.sh status
# 显示版本: feature/auth@abc1234
```
```

- [ ] **Step 3: 验证文档**

```bash
head -60 docs/local-deployment-guide.md
```

Expected: 显示更新后的文档内容

- [ ] **Step 4: Commit**

```bash
git add docs/local-deployment-guide.md
git commit -m "docs: enhance local deployment guide for worktree mode"
```

---

## Task 13: 创建初始 .version 文件

**Files:**
- Create: `.version`

**背景:** 项目根目录需要有 `.version` 文件用于版本追踪。

- [ ] **Step 1: 创建 .version 文件**

```bash
echo "1.5.0" > .version
```

- [ ] **Step 2: 验证文件内容**

```bash
cat .version
```

Expected: 输出 "1.5.0"

- [ ] **Step 3: Commit**

```bash
git add .version
git commit -m "chore: add .version file"
```

---

## Task 14: 更新 .gitignore

**Files:**
- Modify: `.gitignore`

**背景:** 确保 `.version` 文件被跟踪（不忽略）。

- [ ] **Step 1: 检查 .gitignore 是否忽略 .version**

```bash
grep -q "^\.version$" .gitignore && echo "已忽略" || echo "未忽略"
```

Expected: 输出 "未忽略"（如果输出 "已忽略"，需要从 .gitignore 中移除）

- [ ] **Step 2: 如需修改**

如果 `.version` 被 `.gitignore` 忽略，移除该行。

- [ ] **Step 3: Commit（如有修改）**

```bash
git add .gitignore
git commit -m "chore: track .version file"
```

---

## Task 15: 集成测试

**Files:**
- Test: 手动验证

**背景:** 完成所有修改后需要验证功能正常。

- [ ] **Step 1: 验证模式检测**

```bash
# 在 git 仓库中
cd /Users/luoweirong/cyberstrat-forge/cyber-pulse
bash -c 'source scripts/cyber-pulse.sh; is_git_repo && echo "是 git 仓库"'
```

Expected: 输出 "是 git 仓库"

- [ ] **Step 2: 验证版本获取**

```bash
bash -c 'source scripts/cyber-pulse.sh; get_current_version'
```

Expected: 输出版本号（如 `v1.5.0` 或 `main@xxx`）

- [ ] **Step 3: 验证 upgrade 分支检测**

```bash
# 在 main 分支
bash -c 'source scripts/cyber-pulse.sh; branch=$(git branch --show-current); echo "当前分支: $branch"'
```

Expected: 输出 "当前分支: main" 或当前分支名

- [ ] **Step 4: 验证 Python 版本读取**

```bash
python3 -c "from src.cyberpulse import __version__; print(f'版本: {__version__}')"
```

Expected: 输出 "版本: 1.5.0"

- [ ] **Step 5: Commit 测试结果**

```bash
git add -A
git commit -m "test: verify dual-mode deployment implementation"
```

---

## 验证清单

完成所有任务后，验证以下功能：

### 环境检测验证
- [ ] 开发者模式（git clone）正确识别
- [ ] 开发者模式（worktree）正确识别
- [ ] 运维者模式（无 .git）正确识别
- [ ] `CYBER_PULSE_MODE` 环境变量覆盖生效

### 开发者模式验证
- [ ] deploy 命令默认本地构建
- [ ] upgrade 命令在 main 分支正常执行
- [ ] upgrade 命令在特性分支提示退出并建议使用 deploy
- [ ] 版本检测在 main 分支使用 git describe --tags
- [ ] 版本检测在特性分支显示 `分支名@commit`

### 运维者模式验证
- [ ] deploy 命令远程拉取镜像
- [ ] upgrade 命令通过镜像 tag 切换版本
- [ ] 版本检测使用 .version 文件

### 共用功能验证
- [ ] `.version` 文件正确创建和读取
- [ ] `CYBER_PULSE_VERSION` 配置项生效
- [ ] Docker 构建注入版本信息

---

## 完成后操作

完成所有任务后：

1. **更新 CHANGELOG.md**：添加本次变更记录
2. **创建 PR**：提交到主仓库进行代码审查
3. **标签发布**：合并后打 tag 触发 CI/CD 构建部署包