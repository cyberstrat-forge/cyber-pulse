# 设计文档：部署与升级（双模式）

**版本**: 2.0
**日期**: 2026-03-29
**状态**: 待审核

---

## 1. 概述

### 1.1 背景

cyber-pulse 需要支持两类用户的部署场景：

- **开发者**：通过 `git clone` 获取代码，本地构建镜像进行开发测试
- **运维者**：通过安装脚本获取部署包，拉取远程镜像进行生产部署

两类用户的安装方式和升级路径不同，但大部分运维逻辑是复用的。本文档设计统一的管理脚本，自动识别模式并提供一致的操作体验。

### 1.2 目标

1. **统一入口**：同一套脚本支持两种模式，自动检测切换
2. **一键安装**：运维者通过一条命令完成安装和部署
3. **安全升级**：升级时自动保护数据，失败自动回滚
4. **版本可追溯**：清晰记录和管理运行版本

### 1.3 范围

| 内容 | 范围 |
|------|------|
| 开发者模式部署与升级 | ✅ |
| 运维者模式部署与升级 | ✅ |
| 环境检测机制 | ✅ |
| 快照与回滚机制 | ✅ |

---

## 2. 双模式概述

### 2.1 模式定义

| 维度 | 开发者模式 | 运维者模式 |
|------|-----------|-----------|
| **识别标志** | `.git` 存在（目录或文件） | `.git` 不存在 |
| **获取方式** | `git clone` 完整代码 | 安装脚本下载部署包 |
| **镜像来源** | 本地构建 (`--local`) | 远程拉取 |
| **升级方式** | `git checkout` + 重建镜像（仅 main 分支） | 拉取新版本镜像 |
| **版本检测** | `git describe --tags` 或 `分支名@commit` | `.version` 文件 |
| **回滚代码** | `git checkout` 旧版本 | 切换镜像 tag |

> **Worktree 开发模式说明**：遵循 `superpowers:subagent-driven-development` 工作流，开发者在 worktree 的特性分支上开发，通过 `deploy --local` 部署当前分支最新代码进行测试，**不使用 upgrade 命令**。

### 2.2 复用的部分

以下组件两种模式完全复用：

| 组件 | 说明 |
|------|------|
| Docker Compose 配置 | docker-compose.yml + 覆盖配置 |
| 快照/备份机制 | 数据库快照、备份恢复脚本 |
| 健康检查 | /health 端点、容器检查 |
| 数据库迁移 | alembic upgrade head |
| Admin Key 管理 | 生成、重置逻辑 |
| 管理脚本 | api.sh（sources、jobs、clients） |
| 配置生成 | generate-env.sh |
| 服务启停 | start/stop/restart/status |

### 2.3 有差异的部分

| 环节 | 开发者模式 | 运维者模式 |
|------|-----------|-----------|
| upgrade 命令 | 仅 main 分支可用：git fetch + checkout + build/pull | 更新 CYBER_PULSE_VERSION + pull |
| 版本获取 | main: `git describe --tags`；特性分支: `分支名@commit` | cat .version |
| check-deps git 检查 | 必须有 git | 无需 git（警告而非错误） |
| 回滚代码版本 | git checkout 旧 tag | 修改 .env 中的 CYBER_PULSE_VERSION |

### 2.4 开发者子模式

开发者在不同场景下有不同操作：

| 场景 | 分支 | 操作 |
|------|------|------|
| **Worktree 开发** | 特性分支 | `deploy --local` 部署当前代码，**不使用 upgrade** |
| **主分支维护** | main/master | `deploy` 部署，`upgrade` 升级到最新版本 |

---

## 3. 环境检测机制

### 3.1 检测函数

```bash
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
```

### 3.2 Worktree 说明

Git worktree 是一种将同一仓库的不同分支检出到不同目录的机制：

```bash
# 创建 worktree
git worktree add ../feature-branch feature-branch

# worktree 目录结构
../feature-branch/
├── .git          # 文件（指向主仓库），而非目录
├── src/
└── ...
```

**检测要点**：
- 普通 clone：`.git` 是**目录**
- worktree：`.git` 是**文件**
- 必须同时检测 `-d`（目录）和 `-f`（文件）

### 3.3 模式检测应用场景

| 场景 | 使用方式 |
|------|----------|
| upgrade 命令 | 根据模式选择升级流程 |
| check-deps.sh | 根据模式决定 git 检查级别 |
| 版本获取 | 根据模式选择版本来源 |
| 部署命令 | 开发者模式默认本地构建 |

---

## 4. 安装流程设计

### 4.1 开发者安装

```bash
# 一键安装（开发者模式）
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash

# 或手动 clone
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse
```

**安装后目录**：包含完整代码库（`.git` 目录存在）

### 4.2 运维者安装

```bash
# 运维模式安装
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops

# 或指定版本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops --version v1.5.0
```

**安装后目录**：仅包含部署文件（无 `.git`）

```
cyber-pulse/
├── scripts/
│   ├── cyber-pulse.sh          # 主管理脚本
│   └── api.sh                  # API 管理脚本
├── deploy/
│   ├── docker-compose.yml      # 基础配置
│   ├── docker-compose.prod.yml # 生产环境覆盖
│   └── init/
│       ├── check-deps.sh       # 依赖检查
│       ├── generate-env.sh     # 配置生成
│       ├── create-snapshot.sh  # 快照创建
│       ├── restore-snapshot.sh # 快照恢复
│       ├── create-backup.sh    # 备份创建
│       └── restore-backup.sh   # 备份恢复
├── sources.yaml                # 情报源配置模板
├── .version                    # 版本记录
└── README.md                   # 部署说明
```

**部署包构建**：由 `scripts/build-deploy-package.sh` 脚本打包，包含上述所有文件，输出 `cyber-pulse-deploy-{VERSION}.tar.gz`。

### 4.3 安装脚本流程

```
┌─────────────────────────────────────────────────────────────┐
│                    install.sh 执行流程                       │
├─────────────────────────────────────────────────────────────┤
│  1. 解析参数                                                │
│     └─ --type developer/ops（默认 developer）               │
├─────────────────────────────────────────────────────────────┤
│  2. 检查依赖                                                │
│     ├─ developer: 需要 git                                  │
│     └─ ops: 仅需要 Docker、curl、jq                         │
├─────────────────────────────────────────────────────────────┤
│  3. 获取文件                                                │
│     ├─ developer: git clone                                 │
│     └─ ops: 下载部署包 tar.gz                               │
├─────────────────────────────────────────────────────────────┤
│  4. 写入版本信息（ops 模式）                                 │
│     └─ 创建 .version 文件                                   │
├─────────────────────────────────────────────────────────────┤
│  5. 执行部署（ops 模式自动执行）                             │
│     └─ ./scripts/cyber-pulse.sh deploy --env prod           │
├─────────────────────────────────────────────────────────────┤
│  6. 输出结果                                                │
│     ├─ Admin API Key（首次生成，仅显示一次）                  │
│     └─ 访问地址和下一步操作                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 部署流程设计

### 5.1 部署命令

```bash
# Worktree 开发模式（特性分支，推荐）
cd .worktrees/feature-xxx
./scripts/cyber-pulse.sh deploy --env dev --local

# 主分支开发模式
./scripts/cyber-pulse.sh deploy --env dev

# 主分支开发模式（显式指定本地构建）
./scripts/cyber-pulse.sh deploy --env dev --local

# 运维者模式（自动检测，远程拉取）
./scripts/cyber-pulse.sh deploy --env prod
```

> **Worktree 开发模式**：遵循 `superpowers:subagent-driven-development` 工作流，开发者在 `.worktrees/<branch-name>/` 目录下工作，使用 `deploy --local` 构建并部署当前分支的最新代码。

### 5.2 部署流程

> **说明**：开发者模式"推荐本地构建"以确保代码一致性，但脚本也支持 `--pull` 选项直接使用远程镜像（适用于快速验证）。运维者模式始终使用远程镜像。

```
┌─────────────────────────────────────────────────────────────┐
│                    deploy 命令流程                           │
├─────────────────────────────────────────────────────────────┤
│  1. 检测模式                                                │
│     └─ mode=$(detect_mode)                                  │
├─────────────────────────────────────────────────────────────┤
│  2. 依赖检查                                                │
│     ├─ Docker 运行中                                        │
│     ├─ 端口 8000 未占用                                      │
│     ├─ 磁盘空间充足                                         │
│     └─ git 检查（developer 必须，ops 警告）                   │
├─────────────────────────────────────────────────────────────┤
│  3. 配置生成（如 .env 不存在）                               │
│     ├─ 生成 POSTGRES_PASSWORD                               │
│     ├─ 生成 SECRET_KEY                                      │
│     ├─ 写入 CYBER_PULSE_VERSION（ops 模式）                  │
│     └─ 写入 .env 文件（权限 600）                            │
├─────────────────────────────────────────────────────────────┤
│  4. 写入版本信息                                            │
│     ├─ developer: 从 git tag 获取                           │
│     └─ ops: 从下载版本或 GitHub API 获取                     │
│     └─ 写入 .version 文件                                   │
├─────────────────────────────────────────────────────────────┤
│  5. 镜像处理                                                │
│     ├─ developer + --local: docker compose build            │
│     ├─ developer + --pull: docker compose pull              │
│     ├─ developer 默认: docker compose build（推荐）          │
│     └─ ops: docker compose pull                             │
├─────────────────────────────────────────────────────────────┤
│  6. 启动服务                                                │
│     ├─ docker compose up -d                                 │
│     └─ 等待健康检查通过                                     │
├─────────────────────────────────────────────────────────────┤
│  7. 数据库迁移                                              │
│     └─ alembic upgrade head                                 │
├─────────────────────────────────────────────────────────────┤
│  8. 初始化 Admin Key（如不存在）                             │
│     └─ 输出到终端一次                                       │
├─────────────────────────────────────────────────────────────┤
│  9. 启动时版本检查                                          │
│     ├─ 查询 GitHub Releases 最新版本                        │
│     ├─ 当前版本 = 最新 → 无提示                             │
│     └─ 当前版本 < 最新 → 提示可升级                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 升级流程设计

### 6.1 升级命令

```bash
./scripts/cyber-pulse.sh upgrade
```

**行为**：根据模式自动选择升级方式，升级到最新版本

### 6.2 升级流程总览

```
┌─────────────────────────────────────────────────────────────┐
│                    upgrade 命令流程                          │
├─────────────────────────────────────────────────────────────┤
│  1. 检测模式                                                │
│     └─ mode=$(detect_mode)                                  │
├─────────────────────────────────────────────────────────────┤
│  2. 开发者模式分支检测                                      │
│     ├─ main/master → 继续升级                               │
│     └─ 特性分支 → 提示退出，建议使用 deploy --local          │
├─────────────────────────────────────────────────────────────┤
│  3. 根据模式分支执行                                        │
│     ├─ developer → upgrade_developer_mode                   │
│     └─ ops → upgrade_ops_mode                               │
├─────────────────────────────────────────────────────────────┤
│  4. 共同步骤                                                │
│     ├─ 预检查（服务状态、磁盘空间、网络）                     │
│     ├─ 获取目标版本（GitHub Releases API）                   │
│     ├─ 创建快照                                             │
│     ├─ 执行升级                                             │
│     ├─ 健康检查                                             │
│     └─ 成功删除快照 / 失败自动回滚                           │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 开发者模式升级流程

```
┌─────────────────────────────────────────────────────────────┐
│              upgrade_developer_mode 流程                     │
├─────────────────────────────────────────────────────────────┤
│  1. 预检查                                                  │
│     ├─ 服务运行中                                           │
│     ├─ git 仓库可用                                         │
│     ├─ 分支检测:                                            │
│     │   ├─ main/master → 继续升级流程                       │
│     │   └─ 特性分支 → 提示并退出:                           │
│     │       "当前在特性分支 '<branch>'，upgrade 不适用       │
│     │        如需部署当前代码，请使用:                       │
│     │        ./scripts/cyber-pulse.sh deploy --local"       │
│     └─ 无未提交的更改（警告而非阻塞）                         │
├─────────────────────────────────────────────────────────────┤
│  2. 获取版本信息                                            │
│     ├─ 当前版本: git describe --tags                        │
│     └─ 目标版本: GitHub Releases API                        │
│     └─ 版本比较:                                            │
│        ├─ 当前 == 目标: 提示"已是最新版本"，退出            │
│        └─ 当前 < 目标: 继续升级                             │
│        └─ 当前 > 目标: 提示"当前版本高于目标"，警告继续     │
├─────────────────────────────────────────────────────────────┤
│  3. 创建快照                                                │
│     ├─ 数据库导出                                           │
│     ├─ .env 备份                                            │
│     ├─ 当前 git commit 记录                                 │
│     ├─ alembic revision 记录                                │
│     └─ 失败 → 中断升级，提示用户手动备份后重试               │
├─────────────────────────────────────────────────────────────┤
│  4. 执行升级                                                │
│     ├─ git fetch origin --tags                              │
│     ├─ git checkout <target_version>                        │
│     ├─ 镜像处理:                                            │
│     │   ├─ --local: docker compose build                    │
│     │   ├─ --pull: docker compose pull                      │
│     │   └─ 默认: docker compose build                       │
│     ├─ docker compose down                                  │
│     ├─ docker compose up -d                                 │
│     └─ alembic upgrade head                                 │
├─────────────────────────────────────────────────────────────┤
│  5. 更新 .version 文件                                      │
├─────────────────────────────────────────────────────────────┤
│  6. 健康检查                                                │
│     ├─ 等待服务就绪（超时 60s，重试 3 次，间隔 10s）           │
│     ├─ 检查 /health 端点返回 200                             │
│     └─ 失败 → 进入回滚流程                                   │
├─────────────────────────────────────────────────────────────┤
│  7. 结果处理                                                │
│     ├─ 成功 → 删除快照                                      │
│     └─ 失败 → git checkout <old_commit> + 恢复快照           │
└─────────────────────────────────────────────────────────────┘
```

### 6.4 运维者模式升级流程

```
┌─────────────────────────────────────────────────────────────┐
│                upgrade_ops_mode 流程                         │
├─────────────────────────────────────────────────────────────┤
│  1. 预检查                                                  │
│     ├─ 服务运行中                                           │
│     ├─ 磁盘空间充足                                         │
│     └─ 网络可用                                             │
├─────────────────────────────────────────────────────────────┤
│  2. 获取版本信息                                            │
│     ├─ 当前版本: cat .version                               │
│     └─ 目标版本: GitHub Releases API                        │
│     └─ 版本比较:                                            │
│        ├─ 当前 == 目标: 提示"已是最新版本"，退出            │
│        └─ 当前 < 目标: 继续升级                             │
│        └─ 当前 > 目标: 提示"当前版本高于目标"，警告继续     │
├─────────────────────────────────────────────────────────────┤
│  3. 创建快照                                                │
│     ├─ 数据库导出                                           │
│     ├─ .env 备份                                            │
│     ├─ .version 备份                                        │
│     ├─ alembic revision 记录                                │
│     └─ 失败 → 中断升级，提示用户手动备份后重试               │
├─────────────────────────────────────────────────────────────┤
│  4. 执行升级                                                │
│     ├─ 更新 .env 中的 CYBER_PULSE_VERSION                   │
│     ├─ docker compose pull                                  │
│     ├─ docker compose down                                  │
│     ├─ docker compose up -d                                 │
│     └─ alembic upgrade head                                 │
├─────────────────────────────────────────────────────────────┤
│  5. 更新 .version 文件                                      │
├─────────────────────────────────────────────────────────────┤
│  6. 健康检查                                                │
│     ├─ 等待服务就绪（超时 60s，重试 3 次，间隔 10s）           │
│     ├─ 检查 /health 端点返回 200                             │
│     └─ 失败 → 进入回滚流程                                   │
├─────────────────────────────────────────────────────────────┤
│  7. 结果处理                                                │
│     ├─ 成功 → 删除快照                                      │
│     └─ 失败 → 恢复旧版本镜像 + 恢复快照                      │
└─────────────────────────────────────────────────────────────┘
```

### 6.5 回滚流程差异

| 步骤 | 开发者模式 | 运维者模式 |
|------|-----------|-----------|
| 恢复数据库 | pg_restore | pg_restore |
| 恢复配置 | `cp .env.backup .env && chmod 600 .env` | `cp .env.backup .env && chmod 600 .env` |
| 恢复代码版本 | `git checkout <old_commit>` | `sed -i "s/VERSION=.*/VERSION=$old/" .env` |
| 数据库迁移回滚 | `alembic downgrade <old_revision>` | `alembic downgrade <old_revision>` |
| 拉取镜像 | 可能需要 build/pull | docker compose pull |
| 重启服务 | docker compose up -d | docker compose up -d |

> **说明**：数据库迁移回滚需要从快照的 `metadata.json` 中读取旧的 alembic revision。如果降级失败，使用 pg_restore 完整恢复数据库。

---

## 7. 版本管理

### 7.1 版本来源优先级

| 模式 | 分支 | 优先级 1 | 优先级 2 | 优先级 3 |
|------|------|----------|----------|----------|
| **开发者** | main/master | `git describe --tags` | `.version` 文件 | `/health` API |
| **开发者** | 特性分支 | `分支名@commit` | - | - |
| **运维者** | - | `.version` 文件 | `/health` API | - |

### 7.2 统一版本获取函数

```bash
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
```

### 7.3 .version 文件管理

**位置**: 项目根目录 `.version`

**内容**: 纯文本版本号
```
1.5.0
```

**写入时机**:
1. 开发者模式：部署或升级成功后
2. 运维者模式：安装时、升级成功后

---

## 8. 依赖检查调整

### 8.1 check-deps.sh 修改

```bash
check_git_repo() {
    print_header "Git 仓库检查"

    # 支持 worktree (.git 可以是文件或目录)
    if [[ -d "$PROJECT_ROOT/.git" ]] || [[ -f "$PROJECT_ROOT/.git" ]]; then
        print_ok "Git 仓库存在（开发者模式）"

        # 检查是否有未提交的更改（仅提示，不报错）
        if ! git -C "$PROJECT_ROOT" diff --quiet 2>/dev/null; then
            print_warning "存在未提交的更改"
        fi

        # 显示当前分支
        local branch
        branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo "unknown")
        print_info "当前分支: $branch"
    else
        # 运维者模式：无 git 是正常的，仅提示
        print_info "非 Git 仓库（运维者模式）"
    fi
}
```

### 8.2 cyber-pulse.sh upgrade 修改

```bash
cmd_upgrade() {
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

    case "$mode" in
        developer)
            upgrade_developer_mode "$@"
            ;;
        ops)
            upgrade_ops_mode "$@"
            ;;
    esac
}
```

---

## 9. 快照与回滚机制

### 9.1 快照目录结构

```
.snapshots/
├── snapshot_20260329_120000/
│   ├── database.dump         # pg_dump 自定义格式
│   ├── .env.backup           # 配置文件备份
│   ├── .version.backup       # 版本记录
│   ├── git_commit.txt        # git commit（开发者模式）
│   └── metadata.json         # 快照元数据
└── snapshot_20260329_150000/
    └── ...
```

### 9.2 快照元数据

```json
{
    "snapshot_name": "snapshot_20260329_120000",
    "created_at": "2026-03-29T12:00:00Z",
    "mode": "developer",
    "version": "1.5.0",
    "git_commit": "abc1234",
    "alembic_revision": "abc123def",
    "upgrade_target": "1.6.0",
    "database_size": "128M",
    "components": {
        "database": "included",
        "env_config": "included",
        "version_info": "included",
        "git_commit": "included",
        "alembic_revision": "included"
    }
}
```

> **alembic_revision 说明**：记录升级前的数据库迁移版本，用于回滚时执行 `alembic downgrade`。

### 9.3 快照生命周期

| 阶段 | 操作 |
|------|------|
| 升级前 | 自动创建快照 |
| 升级成功 | 自动删除快照 |
| 升级失败 | 自动回滚快照后删除 |

> **说明**：快照仅作为升级过程中的临时保护机制，升级完成后（无论成功或失败回滚）立即删除，不长期保留。如需长期备份，请使用 `backup` 命令。

---

## 10. 边界条件处理

### 10.1 版本信息异常

| 场景 | 处理方式 |
|------|----------|
| `.version` 文件不存在 | 返回 `unknown`，提示"无法确定当前版本，建议先执行 deploy" |
| `.version` 文件损坏/空 | 返回 `unknown`，警告"版本文件异常" |
| `git describe --tags` 失败（无 tag） | 返回 commit hash，警告"未找到版本标签" |
| 特性分支（非 main/master） | 返回 `分支名@commit`，如 `feature/auth@abc1234` |

### 10.2 升级执行异常

| 场景 | 处理方式 |
|------|----------|
| 特性分支执行 upgrade | 提示退出："当前在特性分支，upgrade 不适用。请使用 deploy --local 部署当前代码" |
| `git checkout` 失败（tag 不存在） | 中断升级，提示"目标版本不存在" |
| `docker compose pull` 失败（网络问题） | 重试 3 次（间隔 5s），失败后中断并提示检查网络 |
| `docker compose build` 失败 | 中断升级，提示"镜像构建失败，检查代码或使用 --pull" |
| `alembic upgrade head` 失败 | 进入回滚流程：先 `alembic downgrade`，再 `pg_restore` |
| 健康检查超时（60s） | 进入回滚流程 |

### 10.3 快照异常

| 场景 | 处理方式 |
|------|----------|
| 快照创建失败（磁盘空间不足） | 中断升级，提示"磁盘空间不足，请清理后重试" |
| `pg_dump` 失败 | 中断升级，提示"数据库导出失败" |
| 快照恢复失败 | 提示"快照恢复失败，请检查快照文件完整性" |

---

## 11. 配置管理

### 11.1 .env 配置项

| 配置项 | 敏感性 | 升级处理 |
|--------|--------|----------|
| `POSTGRES_PASSWORD` | 🔴 高 | 保留 |
| `SECRET_KEY` | 🔴 高 | 保留 |
| `POSTGRES_USER` | 🟡 中 | 保留 |
| `POSTGRES_DB` | 🟡 中 | 保留 |
| `DATABASE_URL` | 🟡 中 | 保留（依赖密码） |
| `REDIS_URL` | 🟢 低 | 保留 |
| `DRAMATIQ_BROKER_URL` | 🟢 低 | 保留 |
| `LOG_LEVEL` | 🟢 低 | 保留 |
| `CYBER_PULSE_VERSION` | 🟢 低 | 升级时更新 |

### 11.2 generate-env.sh 修改

新增 `CYBER_PULSE_VERSION` 配置项：

```bash
cat > "$ENV_FILE" << EOF
# ... 其他配置 ...

# 镜像版本（运维者模式使用）
CYBER_PULSE_VERSION=${version:-latest}
EOF
```

---

## 12. 部署包构建

### 12.1 构建脚本

`scripts/build-deploy-package.sh` 用于构建运维者部署包：

```bash
# 使用方式
./scripts/build-deploy-package.sh --version v1.5.0

# 输出
cyber-pulse-deploy-v1.5.0.tar.gz
```

### 12.2 构建流程

```
┌─────────────────────────────────────────────────────────────┐
│            build-deploy-package.sh 执行流程                  │
├─────────────────────────────────────────────────────────────┤
│  1. 解析参数                                                │
│     └─ --version: 指定版本号                                │
├─────────────────────────────────────────────────────────────┤
│  2. 创建临时目录                                            │
│     └─ mkdir -p /tmp/cyber-pulse-deploy                     │
├─────────────────────────────────────────────────────────────┤
│  3. 复制必要文件                                            │
│     ├─ scripts/cyber-pulse.sh                               │
│     ├─ scripts/api.sh                                       │
│     ├─ deploy/                                              │
│     ├─ sources.yaml                                         │
│     └─ README.md                                            │
├─────────────────────────────────────────────────────────────┤
│  4. 创建 .version 文件                                      │
│     └─ echo "v1.5.0" > .version                             │
├─────────────────────────────────────────────────────────────┤
│  5. 打包                                                    │
│     └─ tar -czvf cyber-pulse-deploy-v1.5.0.tar.gz           │
├─────────────────────────────────────────────────────────────┤
│  6. 清理临时目录                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 13. 镜像仓库配置

### 13.1 仓库信息

| 项目 | 值 |
|------|-----|
| **仓库地址** | `crpi-tuxci06y0zyoionf.cn-guangzhou.personal.cr.aliyuncs.com` |
| **命名空间** | `cyberstrat-forge` |
| **镜像名称** | `cyber-pulse` |
| **仓库类型** | 公开 |
| **认证需求** | 无需 `docker login` |

### 13.2 镜像版本控制

```yaml
# docker-compose.yml
services:
  api:
    image: crpi-tuxci06y0zyoionf.cn-guangzhou.personal.cr.aliyuncs.com/cyberstrat-forge/cyber-pulse:${CYBER_PULSE_VERSION:-latest}
```

---

## 14. 文件变更清单

### 14.1 新增文件

| 文件 | 说明 |
|------|------|
| `.version` | 版本记录文件 |
| `scripts/build-deploy-package.sh` | 部署包构建脚本 |

### 14.2 修改文件

| 文件 | 变更 |
|------|------|
| `scripts/cyber-pulse.sh` | 新增模式检测函数、版本获取函数、upgrade 分支检测、升级流程分支逻辑、启动时版本检查 |
| `deploy/init/check-deps.sh` | git 检查改为非阻塞警告 |
| `deploy/init/generate-env.sh` | 新增 `CYBER_PULSE_VERSION` 配置项 |
| `.github/workflows/docker-publish.yml` | 新增部署包构建和发布 |
| `scripts/install.sh` | 运维者模式自动执行部署 |
| `src/cyberpulse/__init__.py` | 版本号从 `.version` 文件或环境变量读取 |
| `Dockerfile` | 构建时注入版本信息 |

---

## 15. 命令清单

### 15.1 安装命令

```bash
# 开发者模式（默认）
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash

# 运维者模式
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops

# 指定版本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops --version v1.5.0
```

### 15.2 部署命令

```bash
# Worktree 开发模式（特性分支）
cd .worktrees/feature-xxx
./scripts/cyber-pulse.sh deploy --env dev --local

# 主分支开发模式
./scripts/cyber-pulse.sh deploy --env dev

# 运维者模式
./scripts/cyber-pulse.sh deploy --env prod
```

### 15.3 升级命令

```bash
# 升级到最新版本（仅 main/master 分支可用）
./scripts/cyber-pulse.sh upgrade
```

> **说明**：`upgrade` 命令仅适用于 main/master 分支。在特性分支执行时会提示退出，建议使用 `deploy --local` 部署当前代码。

### 15.4 其他命令

```bash
# 服务管理
./scripts/cyber-pulse.sh status
./scripts/cyber-pulse.sh start
./scripts/cyber-pulse.sh stop
./scripts/cyber-pulse.sh restart
./scripts/cyber-pulse.sh logs [service]

# 备份恢复
./scripts/cyber-pulse.sh backup
./scripts/cyber-pulse.sh restore --list
./scripts/cyber-pulse.sh restore <backup_name>

# API 管理
./scripts/api.sh configure
./scripts/api.sh diagnose
./scripts/api.sh sources list
```

---

## 16. 验证清单

### 16.1 环境检测验证

- [ ] 开发者模式（git clone）正确识别
- [ ] 开发者模式（worktree）正确识别
- [ ] 运维者模式（无 .git）正确识别
- [ ] `CYBER_PULSE_MODE` 环境变量覆盖生效

### 16.2 开发者模式验证

- [ ] deploy 命令默认本地构建
- [ ] upgrade 命令在 main 分支正常执行
- [ ] upgrade 命令在特性分支提示退出并建议使用 deploy
- [ ] 版本检测在 main 分支使用 git describe --tags
- [ ] 版本检测在特性分支显示 `分支名@commit`
- [ ] 回滚正确切换 git commit

### 16.3 运维者模式验证

- [ ] deploy 命令远程拉取镜像
- [ ] upgrade 命令通过镜像 tag 切换版本
- [ ] 版本检测使用 .version 文件
- [ ] 回滚正确切换镜像版本

### 16.4 共用功能验证

- [ ] 快照正确创建和恢复
- [ ] 配置文件正确保留
- [ ] Admin Key 正确生成
- [ ] 健康检查正常工作

---

## 17. 附录

### 17.1 版本比较函数

```bash
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

### 17.2 关联文档

- [部署优化设计](./2026-03-21-deployment-optimization-design.md)
- [部署优化阶段1设计](./2026-03-26-deployment-optimization-phase1-design.md)
- [升级机制设计](./2026-03-26-upgrade-mechanism-design.md)
- [本地部署指南](../../local-deployment-guide.md)
- [设计方案评估报告](./2026-03-29-production-deployment-review.md)