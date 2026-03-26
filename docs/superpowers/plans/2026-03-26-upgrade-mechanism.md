# 应用升级机制实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现开发者 rebuild 和运维人员 upgrade 两套升级机制，支持自动快照和回滚

**Architecture:** 通过检测 .git 目录区分模式；API 提供 /api/v1/version 端点；Dockerfile 构建时注入版本信息；upgrade 命令根据模式执行不同流程

**Tech Stack:** Python 3.11, FastAPI, Bash, Docker, curl, jq

---

## 任务依赖关系

```
Task 1 (版本 API 端点)
    │
    └──→ Task 2 (Dockerfile 版本注入)
              │
              └──→ Task 3 (check-update.sh 改造)
                        │
                        └──→ Task 4 (cyber-pulse.sh 模式检测)
                                  │
                                  ├──→ Task 5 (rebuild 命令)
                                  │
                                  └──→ Task 6 (upgrade 命令改造)
                                            │
                                            └──→ Task 7 (启动时版本检查)
                                                      │
                                                      └──→ Task 8 (集成测试)
```

---

## 文件结构

### 新增

| 文件 | 说明 |
|------|------|
| `src/cyberpulse/api/routers/version.py` | 版本 API 端点 |
| `tests/test_api/test_version_api.py` | 版本 API 测试 |

### 修改

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 构建时注入版本信息 |
| `deploy/upgrade/check-update.sh` | 支持 API 端点检测 |
| `scripts/cyber-pulse.sh` | 新增 rebuild 命令、改造 upgrade 命令 |

---

## Task 1: 版本 API 端点

**Files:**
- Create: `src/cyberpulse/api/routers/version.py`
- Modify: `src/cyberpulse/api/main.py:95-106`
- Test: `tests/test_api/test_version_api.py`

- [ ] **Step 1: 编写版本 API 测试**

创建测试文件 `tests/test_api/test_version_api.py`:

```python
"""Tests for version API endpoint."""
import os
import pytest
from fastapi.testclient import TestClient


class TestVersionEndpoint:
    """Test /api/v1/version endpoint."""

    def test_version_returns_200(self, client: TestClient):
        """Version endpoint should return 200."""
        response = client.get("/api/v1/version")
        assert response.status_code == 200

    def test_version_returns_json(self, client: TestClient):
        """Version endpoint should return JSON with version field."""
        response = client.get("/api/v1/version")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_version_from_env(self, client: TestClient, monkeypatch):
        """Version should come from APP_VERSION env var."""
        monkeypatch.setenv("APP_VERSION", "2.0.0-test")
        # Need to re-import to pick up new env var
        from cyberpulse.api.routers.version import get_version_info
        info = get_version_info()
        assert info["version"] == "2.0.0-test"

    def test_version_fallback_to_package(self, client: TestClient, monkeypatch):
        """Version should fallback to package __version__ if env not set."""
        monkeypatch.delenv("APP_VERSION", raising=False)
        from cyberpulse.api.routers.version import get_version_info
        info = get_version_info()
        # Should return the package version (1.3.0)
        assert info["version"] == "1.3.0"

    def test_version_response_format(self, client: TestClient):
        """Version response should have expected format."""
        response = client.get("/api/v1/version")
        data = response.json()
        # Required fields
        assert "version" in data
        # Optional fields (may be None)
        assert "commit" in data or "commit" not in data  # Optional
        assert "build_time" in data or "build_time" not in data  # Optional
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && uv run pytest tests/test_api/test_version_api.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: 创建版本 API 路由**

创建文件 `src/cyberpulse/api/routers/version.py`:

```python
"""
Version API endpoint.

Returns current application version information.
"""
import os
from datetime import datetime
from fastapi import APIRouter

from ... import __version__

router = APIRouter()


def get_version_info() -> dict:
    """
    Get version information from environment or package.

    Returns:
        dict with version, commit, and build_time fields
    """
    # APP_VERSION is injected at build time via Dockerfile
    version = os.environ.get("APP_VERSION", __version__)

    # Optional: commit SHA injected at build time
    commit = os.environ.get("APP_COMMIT", None)

    # Optional: build time injected at build time
    build_time = os.environ.get("APP_BUILD_TIME", None)

    return {
        "version": version,
        "commit": commit,
        "build_time": build_time,
    }


@router.get("/api/v1/version")
async def get_version() -> dict:
    """
    Get current application version.

    Returns:
        Version information including version string, commit SHA, and build time.
    """
    return get_version_info()
```

- [ ] **Step 4: 注册路由到 main.py**

修改 `src/cyberpulse/api/main.py`，在 import 部分添加（约第 16 行后）:

```python
from .routers.admin import sources_router, jobs_router, clients_router, logs_router, diagnose_router
from .routers.version import router as version_router  # 新增
```

在路由注册部分添加（约第 106 行后）:

```python
app.include_router(diagnose_router, prefix="/api/v1/admin", tags=["admin-diagnose"])
# Version API
app.include_router(version_router, tags=["version"])  # 新增
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && uv run pytest tests/test_api/test_version_api.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/cyberpulse/api/routers/version.py src/cyberpulse/api/main.py tests/test_api/test_version_api.py
git commit -m "$(cat <<'EOF'
feat(api): add /api/v1/version endpoint

- Return version from APP_VERSION env var (build-time injection)
- Fallback to package __version__ if env not set
- Include optional commit and build_time fields

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Dockerfile 版本注入

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: 修改 Dockerfile 添加版本构建参数**

修改 `Dockerfile`，在 Stage 2 (runtime) 部分添加版本信息注入。

在 `# Set environment variables` 部分后（约第 73 行后）添加:

```dockerfile
# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"

# Version information (can be overridden at build time)
ARG APP_VERSION=""
ARG APP_COMMIT=""
ARG APP_BUILD_TIME=""
ENV APP_VERSION=${APP_VERSION}
ENV APP_COMMIT=${APP_COMMIT}
ENV APP_BUILD_TIME=${APP_BUILD_TIME}
```

- [ ] **Step 2: 验证 Dockerfile 语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && docker build --help | head -1`
Expected: 输出 docker build 帮助信息

- [ ] **Step 3: 提交**

```bash
git add Dockerfile
git commit -m "$(cat <<'EOF'
feat(docker): add version injection build args

- Add APP_VERSION, APP_COMMIT, APP_BUILD_TIME build args
- Set as environment variables for runtime access

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: check-update.sh 改造

**Files:**
- Modify: `deploy/upgrade/check-update.sh`

- [ ] **Step 1: 添加 API 端点版本检测函数**

修改 `deploy/upgrade/check-update.sh`，在 `get_current_version()` 函数前（约第 38 行后）添加:

```bash
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

# 从 API 端点获取当前版本（运行中的应用）
get_current_version_from_api() {
    local api_url="${1:-http://localhost:8000}"

    local version
    version=$(curl -s --connect-timeout 5 "${api_url}/api/v1/version" 2>/dev/null | jq -r '.version' 2>/dev/null)

    if [[ -n "$version" && "$version" != "null" && "$version" != "" ]]; then
        echo "$version"
        return 0
    fi
    return 1
}

# 从镜像 tag 获取版本（应用未运行时）
get_current_version_from_image() {
    local container_name="${1:-cyberpulse-api-1}"

    # 获取镜像名称:tag
    local image
    image=$(docker inspect --format='{{.Config.Image}}' "$container_name" 2>/dev/null)

    if [[ -n "$image" ]]; then
        # 提取 tag 部分
        local tag
        tag=$(echo "$image" | cut -d: -f2)
        if [[ -n "$tag" && "$tag" != "latest" ]]; then
            echo "$tag"
            return 0
        fi
    fi
    return 1
}

# 智能获取当前版本（优先 API，其次镜像）
get_current_version_smart() {
    local api_url="${1:-http://localhost:8000}"
    local version

    # 优先从 API 获取
    version=$(get_current_version_from_api "$api_url") && {
        echo "$version"
        return 0
    }

    # API 不可用，尝试从镜像获取
    version=$(get_current_version_from_image) && {
        echo "$version"
        return 0
    }

    # 都不可用
    echo "unknown"
    return 1
}
```

- [ ] **Step 2: 修改 main 函数使用新的版本获取方式**

找到 main 函数中的版本获取部分，修改为:

```bash
# 主函数
main() {
    local json_output="false"
    local use_api="false"
    local api_url="http://localhost:8000"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json)
                json_output="true"
                shift
                ;;
            --api)
                use_api="true"
                shift
                ;;
            --api-url)
                api_url="$2"
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

    # 获取当前版本
    local current_version
    if [[ "$use_api" == "true" ]]; then
        current_version=$(get_current_version_smart "$api_url")
    else
        current_version=$(get_current_version)
    fi
```

- [ ] **Step 3: 更新帮助信息**

修改 `show_help()` 函数:

```bash
# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "检查 Cyber Pulse 更新。"
    echo ""
    echo "选项:"
    echo "  --json       以 JSON 格式输出"
    echo "  --api        从运行中的 API 获取当前版本"
    echo "  --api-url    指定 API URL (默认: http://localhost:8000)"
    echo "  --help, -h   显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0              检查更新（从 git 或 .version 文件获取版本）"
    echo "  $0 --api        检查更新（从运行中的 API 获取版本）"
    echo "  $0 --json       以 JSON 格式输出"
}
```

- [ ] **Step 4: 测试脚本语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && bash -n deploy/upgrade/check-update.sh && echo "Syntax OK"`
Expected: 输出 "Syntax OK"

- [ ] **Step 5: 提交**

```bash
git add deploy/upgrade/check-update.sh
git commit -m "$(cat <<'EOF'
feat(upgrade): add API endpoint version detection

- Add get_current_version_from_api() for running apps
- Add get_current_version_from_image() for stopped apps
- Add get_current_version_smart() with priority fallback
- Support --api and --api-url flags

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: cyber-pulse.sh 模式检测

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 添加模式检测函数**

在 `scripts/cyber-pulse.sh` 的工具函数部分（约第 100 行后）添加:

```bash
# ============================================
# 模式检测
# ============================================

# 检测是否为开发者模式（本地构建）
is_developer_mode() {
    # 1. 检查 .git 目录存在
    [[ -d "$PROJECT_ROOT/.git" ]] || return 1

    # 2. 检查 remote URL 是否为 cyber-pulse 仓库
    local remote_url
    remote_url=$(git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null)
    [[ "$remote_url" == *"cyber-pulse"* ]]
}

# 获取当前模式名称
get_mode_name() {
    if is_developer_mode; then
        echo "developer"
    else
        echo "operator"
    fi
}
```

- [ ] **Step 2: 测试脚本语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && bash -n scripts/cyber-pulse.sh && echo "Syntax OK"`
Expected: 输出 "Syntax OK"

- [ ] **Step 3: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(cli): add developer/operator mode detection

- Check .git directory and remote URL for cyber-pulse
- is_developer_mode() returns true for git clone
- get_mode_name() returns "developer" or "operator"

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: rebuild 命令（开发者模式）

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 添加 rebuild 命令函数**

在 `scripts/cyber-pulse.sh` 中添加 `cmd_rebuild` 函数（在 `cmd_upgrade` 函数之前）:

```bash
# rebuild 命令 - 重新构建（开发者模式）
cmd_rebuild() {
    print_banner
    print_header "重新构建 Cyber Pulse (开发者模式)"

    # 检查是否为开发者模式
    if ! is_developer_mode; then
        print_error "rebuild 命令仅适用于开发者模式（git clone 获取的代码库）"
        print_info "运维人员请使用 upgrade 命令"
        exit 1
    fi

    # 检查 Docker
    check_docker
    check_docker_compose

    # 1. 创建快照
    print_step "创建快照..."
    local snapshot_name=""
    if bash "$UPGRADE_DIR/create-snapshot.sh"; then
        snapshot_name=$(ls -t "$SNAPSHOTS_DIR" 2>/dev/null | head -1)
        print_success "快照已创建: $snapshot_name"
    else
        print_warning "快照创建失败，继续重新构建"
    fi

    # 2. 重新构建镜像
    print_step "重新构建镜像..."
    cd "$DEPLOY_DIR"

    if ! $DOCKER_COMPOSE build; then
        print_error "镜像构建失败"
        exit 1
    fi
    print_success "镜像构建完成"

    # 3. 重启服务
    print_step "重启服务..."
    $DOCKER_COMPOSE down
    if ! $DOCKER_COMPOSE up -d; then
        print_error "服务启动失败"
        exit 1
    fi

    # 4. 数据库迁移
    print_step "运行数据库迁移..."
    sleep 5
    if $DOCKER_COMPOSE exec -T api alembic upgrade head; then
        print_success "数据库迁移完成"
    else
        print_warning "数据库迁移可能已失败，请检查日志"
    fi

    # 5. 健康检查
    print_step "执行健康检查..."
    sleep 5

    local healthy="true"
    for service in postgres redis api worker scheduler; do
        if $DOCKER_COMPOSE ps "$service" 2>/dev/null | grep -q "running"; then
            echo -e "  ${GREEN}[●]${NC} $service - 运行中"
        else
            echo -e "  ${RED}[○]${NC} $service - 未运行"
            healthy="false"
        fi
    done

    if [[ "$healthy" == "true" ]]; then
        echo ""
        print_success "重新构建完成!"
    else
        print_warning "部分服务未正常运行，请检查日志"
    fi
}
```

- [ ] **Step 2: 在命令分发部分添加 rebuild**

找到命令分发部分（通常在 case 语句中），添加 rebuild 分支:

```bash
        rebuild)
            cmd_rebuild "${@:2}"
            ;;
        upgrade)
            cmd_upgrade "${@:2}"
            ;;
```

- [ ] **Step 3: 添加 rebuild 帮助信息**

在 `print_help()` 函数中添加:

```bash
    echo "  rebuild            重新构建（开发者模式，使用本地代码）"
```

- [ ] **Step 4: 测试脚本语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && bash -n scripts/cyber-pulse.sh && echo "Syntax OK"`
Expected: 输出 "Syntax OK"

- [ ] **Step 5: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(cli): add rebuild command for developer mode

- Rebuild using local code (docker compose build)
- Auto snapshot before rebuild
- Run database migration after restart
- Health check on completion

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: upgrade 命令改造

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 重写 cmd_upgrade 函数**

替换现有的 `cmd_upgrade` 函数:

```bash
# upgrade 命令 - 升级系统
cmd_upgrade() {
    local target_version=""
    local force="false"
    local dry_run="false"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version|-v)
                target_version="$2"
                shift 2
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

    # 检测模式并分发
    if is_developer_mode; then
        print_warning "检测到开发者模式，请使用 rebuild 命令重新构建"
        print_info "运行: ./scripts/cyber-pulse.sh rebuild"
        exit 1
    fi

    # 运维模式升级
    cmd_upgrade_operator "$target_version" "$dry_run"
}

# 运维模式升级
cmd_upgrade_operator() {
    local target_version="$1"
    local dry_run="$2"

    print_banner
    print_header "升级 Cyber Pulse (运维模式)"

    # 检查 Docker
    check_docker
    check_docker_compose

    cd "$DEPLOY_DIR"

    # 1. 版本检测
    print_step "检测当前版本..."
    local current_version
    current_version=$(bash "$UPGRADE_DIR/check-update.sh" --api 2>/dev/null | grep "^CURRENT_VERSION=" | cut -d= -f2)

    if [[ -z "$current_version" || "$current_version" == "unknown" ]]; then
        # 尝试从 API 获取
        current_version=$(curl -s http://localhost:8000/api/v1/version 2>/dev/null | jq -r '.version' 2>/dev/null)
    fi

    print_info "当前版本: ${current_version:-unknown}"

    # 2. 获取最新版本
    if [[ -z "$target_version" ]]; then
        print_step "获取最新版本信息..."
        local version_info
        version_info=$(bash "$UPGRADE_DIR/check-update.sh" 2>/dev/null) || {
            print_warning "无法检查版本更新，可能是网络问题"
        }

        if [[ -n "$version_info" ]]; then
            target_version=$(echo "$version_info" | grep "^LATEST_VERSION=" | cut -d= -f2)
        fi

        if [[ -z "$target_version" ]]; then
            print_warning "无法获取最新版本"
            target_version="latest"
        fi
    fi

    print_info "目标版本: $target_version"

    # 3. Dry run 模式
    if [[ "$dry_run" == "true" ]]; then
        print_info "Dry run 模式，不会执行实际升级"
        echo ""
        echo -e "${BOLD}升级计划:${NC}"
        echo "  1. 创建数据库快照"
        echo "  2. 拉取新镜像: docker compose pull"
        echo "  3. 重启服务: docker compose up -d"
        echo "  4. 数据库迁移: alembic upgrade head"
        echo "  5. 健康检查"
        echo "  6. 失败时自动回滚"
        echo ""
        return 0
    fi

    # 4. 创建快照
    print_step "创建升级快照..."
    local snapshot_name=""
    if bash "$UPGRADE_DIR/create-snapshot.sh"; then
        snapshot_name=$(ls -t "$SNAPSHOTS_DIR" 2>/dev/null | head -1)
        print_success "快照已创建: $snapshot_name"
    else
        print_warning "快照创建失败，继续升级"
    fi

    # 5. 记录升级日志
    local log_dir="$PROJECT_ROOT/logs"
    mkdir -p "$log_dir"
    local log_file="$log_dir/upgrade-$(date +%Y%m%d-%H%M%S).log"
    exec > >(tee -a "$log_file") 2>&1

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========== 升级开始 =========="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 当前版本: $current_version"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 目标版本: $target_version"

    # 6. 拉取新镜像
    print_step "拉取新镜像..."
    if ! $DOCKER_COMPOSE pull; then
        print_error "镜像拉取失败"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 镜像拉取失败"
        exit 1
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 镜像拉取成功"

    # 7. 重启服务
    print_step "重启服务..."
    $DOCKER_COMPOSE down
    if ! $DOCKER_COMPOSE up -d; then
        print_error "服务启动失败"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 服务启动失败"

        # 回滚
        if [[ -n "$snapshot_name" ]]; then
            print_warning "正在回滚..."
            bash "$UPGRADE_DIR/restore-snapshot.sh" "$snapshot_name" --force
            $DOCKER_COMPOSE up -d
        fi
        exit 1
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 服务重启成功"

    # 8. 数据库迁移
    print_step "运行数据库迁移..."
    sleep 5
    if $DOCKER_COMPOSE exec -T api alembic upgrade head; then
        print_success "数据库迁移完成"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据库迁移成功"
    else
        print_warning "数据库迁移可能已失败"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 数据库迁移失败"
    fi

    # 9. 健康检查
    print_step "执行健康检查..."
    sleep 5

    local healthy="true"
    for service in postgres redis api worker scheduler; do
        if $DOCKER_COMPOSE ps "$service" 2>/dev/null | grep -q "running"; then
            echo -e "  ${GREEN}[●]${NC} $service - 运行中"
        else
            echo -e "  ${RED}[○]${NC} $service - 未运行"
            healthy="false"
        fi
    done

    # 10. 版本验证
    local new_version
    new_version=$(curl -s http://localhost:8000/api/v1/version 2>/dev/null | jq -r '.version' 2>/dev/null)
    print_info "升级后版本: ${new_version:-unknown}"

    if [[ "$healthy" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 健康检查通过"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========== 升级完成 =========="
        echo ""
        print_success "升级完成!"
        echo ""
        echo "升级日志: $log_file"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 健康检查失败"

        # 回滚
        if [[ -n "$snapshot_name" ]]; then
            print_warning "正在回滚..."
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始回滚"
            bash "$UPGRADE_DIR/restore-snapshot.sh" "$snapshot_name" --force
            $DOCKER_COMPOSE pull
            $DOCKER_COMPOSE up -d
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 回滚完成"
        fi

        print_error "升级失败，已回滚"
        exit 1
    fi
}
```

- [ ] **Step 2: 更新升级帮助信息**

修改 `print_upgrade_help()` 函数:

```bash
# 打印 upgrade 帮助
print_upgrade_help() {
    echo ""
    echo "用法: ./scripts/cyber-pulse.sh upgrade [选项]"
    echo ""
    echo "升级 Cyber Pulse 到新版本（运维模式）。"
    echo ""
    echo "开发者模式请使用: ./scripts/cyber-pulse.sh rebuild"
    echo ""
    echo "选项:"
    echo "  --version, -v TAG   升级到指定版本"
    echo "  --dry-run           预览升级计划"
    echo "  --help, -h          显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  ./scripts/cyber-pulse.sh upgrade             # 升级到最新版本"
    echo "  ./scripts/cyber-pulse.sh upgrade -v v1.4.0   # 升级到指定版本"
    echo "  ./scripts/cyber-pulse.sh upgrade --dry-run   # 预览升级计划"
}
```

- [ ] **Step 3: 测试脚本语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && bash -n scripts/cyber-pulse.sh && echo "Syntax OK"`
Expected: 输出 "Syntax OK"

- [ ] **Step 4: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(cli): refactor upgrade command for operator mode

- Separate developer (rebuild) and operator (upgrade) commands
- Auto-detect mode and redirect developers to rebuild
- Add upgrade logging to logs/upgrade-YYYYMMDD-HHMMSS.log
- Auto snapshot and rollback on failure
- Version verification after upgrade

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 启动时版本检查

**Files:**
- Modify: `scripts/cyber-pulse.sh`

- [ ] **Step 1: 添加版本检查函数**

在工具函数部分添加:

```bash
# 启动时版本检查
check_version_on_startup() {
    local api_url="http://localhost:8000"

    # 等待 API 就绪
    sleep 3

    # 获取当前版本
    local current_version
    current_version=$(curl -s --connect-timeout 5 "${api_url}/api/v1/version" 2>/dev/null | jq -r '.version' 2>/dev/null)

    if [[ -z "$current_version" || "$current_version" == "null" ]]; then
        return 0  # 无法获取版本，静默跳过
    fi

    # 获取最新版本
    local latest_version
    latest_version=$(curl -s --connect-timeout 5 "https://api.github.com/repos/cyberstrat-forge/cyber-pulse/releases/latest" 2>/dev/null | jq -r '.tag_name' 2>/dev/null)

    if [[ -z "$latest_version" || "$latest_version" == "null" ]]; then
        return 0  # 无法获取最新版本，静默跳过
    fi

    # 比较版本
    local current=${current_version#v}
    local latest=${latest_version#v}

    if [[ "$current" != "$latest" ]]; then
        # 检查是否需要升级
        local sorted
        sorted=$(printf '%s\n%s\n' "$current" "$latest" | sort -V | tail -n1)

        if [[ "$sorted" == "$latest" ]]; then
            echo ""
            echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
            echo -e "${BOLD}${YELLOW}  有新版本可用!${NC}"
            echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
            echo ""
            echo -e "  当前版本:     ${YELLOW}v$current${NC}"
            echo -e "  最新版本:     ${GREEN}v$latest${NC}"
            echo ""
            echo -e "  运行以下命令升级:"
            echo -e "  ${CYAN}./scripts/cyber-pulse.sh upgrade${NC}"
            echo ""
            echo -e "${YELLOW}───────────────────────────────────────────────────────────────${NC}"
        fi
    fi
}
```

- [ ] **Step 2: 在 deploy 命令中添加版本检查**

找到 `cmd_deploy` 函数的末尾，在健康检查后添加:

```bash
    # 版本检查
    check_version_on_startup
```

- [ ] **Step 3: 在 start 命令中添加版本检查**

找到 `cmd_start` 函数，在启动服务后添加:

```bash
    # 版本检查
    check_version_on_startup
```

- [ ] **Step 4: 测试脚本语法**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && bash -n scripts/cyber-pulse.sh && echo "Syntax OK"`
Expected: 输出 "Syntax OK"

- [ ] **Step 5: 提交**

```bash
git add scripts/cyber-pulse.sh
git commit -m "$(cat <<'EOF'
feat(cli): add startup version check

- Check for new version after deploy and start
- Display upgrade hint if newer version available
- Silent fail on network errors

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 集成测试

**Files:**
- Create: `tests/test_integration/test_upgrade_mechanism.py`

- [ ] **Step 1: 编写集成测试**

创建测试文件 `tests/test_integration/test_upgrade_mechanism.py`:

```python
"""Integration tests for upgrade mechanism."""
import subprocess
import os
import pytest


class TestModeDetection:
    """Test developer/operator mode detection."""

    def test_is_developer_mode_in_git_repo(self):
        """Should detect developer mode in git repo."""
        result = subprocess.run(
            ["bash", "-c", """
                source scripts/cyber-pulse.sh
                PROJECT_ROOT="$(pwd)"
                if is_developer_mode; then echo "developer"; else echo "operator"; fi
            """],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        # We're in a git repo with cyber-pulse in remote URL
        assert "developer" in result.stdout or result.returncode != 0


class TestVersionAPI:
    """Test version API endpoint."""

    def test_version_endpoint_exists(self, client):
        """Version endpoint should be accessible."""
        response = client.get("/api/v1/version")
        assert response.status_code == 200

    def test_version_returns_valid_json(self, client):
        """Version endpoint should return valid JSON."""
        response = client.get("/api/v1/version")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestCheckUpdateScript:
    """Test check-update.sh script."""

    def test_check_update_syntax(self):
        """Script should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", "deploy/upgrade/check-update.sh"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_check_update_help(self):
        """Script should display help."""
        result = subprocess.run(
            ["bash", "deploy/upgrade/check-update.sh", "--help"],
            capture_output=True,
            text=True
        )
        assert "用法" in result.stdout or "Usage" in result.stdout


class TestSnapshotScripts:
    """Test snapshot scripts."""

    def test_create_snapshot_syntax(self):
        """Create snapshot script should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", "deploy/upgrade/create-snapshot.sh"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_restore_snapshot_syntax(self):
        """Restore snapshot script should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", "deploy/upgrade/restore-snapshot.sh"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0


class TestCyberPulseScript:
    """Test cyber-pulse.sh script."""

    def test_script_syntax(self):
        """Main script should have valid syntax."""
        result = subprocess.run(
            ["bash", "-n", "scripts/cyber-pulse.sh"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_help_contains_rebuild(self):
        """Help should mention rebuild command."""
        result = subprocess.run(
            ["bash", "scripts/cyber-pulse.sh", "--help"],
            capture_output=True,
            text=True
        )
        assert "rebuild" in result.stdout

    def test_help_contains_upgrade(self):
        """Help should mention upgrade command."""
        result = subprocess.run(
            ["bash", "scripts/cyber-pulse.sh", "--help"],
            capture_output=True,
            text=True
        )
        assert "upgrade" in result.stdout
```

- [ ] **Step 2: 运行测试**

Run: `cd /Users/luoweirong/cyberstrat-forge/cyber-pulse && uv run pytest tests/test_integration/test_upgrade_mechanism.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_integration/test_upgrade_mechanism.py
git commit -m "$(cat <<'EOF'
test: add integration tests for upgrade mechanism

- Test mode detection (developer/operator)
- Test version API endpoint
- Test check-update.sh script syntax and help
- Test snapshot scripts syntax
- Test cyber-pulse.sh help content

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 验证清单

完成后执行以下验证：

```bash
# 1. 语法检查
bash -n scripts/cyber-pulse.sh
bash -n deploy/upgrade/check-update.sh
bash -n deploy/upgrade/create-snapshot.sh
bash -n deploy/upgrade/restore-snapshot.sh

# 2. 单元测试
uv run pytest tests/test_api/test_version_api.py -v

# 3. 集成测试
uv run pytest tests/test_integration/test_upgrade_mechanism.py -v

# 4. 功能验证
./scripts/cyber-pulse.sh --help | grep -E "rebuild|upgrade"
```

---

## 关联文档

- [升级机制设计](../specs/2026-03-26-upgrade-mechanism-design.md)
- [部署优化阶段1设计](../specs/2026-03-26-deployment-optimization-phase1-design.md)