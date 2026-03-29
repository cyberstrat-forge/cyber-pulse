# 设计方案评估报告：生产环境部署与升级

**版本**: 1.0
**日期**: 2026-03-29
**评估对象**: `2026-03-29-dual-mode-deployment-upgrade-design.md`

---

## 1. 总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **合理性** | ⭐⭐⭐⭐ | 设计思路清晰，决策点合理 |
| **完整性** | ⭐⭐⭐ | 主要流程完整，但与现有实现存在差距 |
| **可实现性** | ⭐⭐⭐ | 需要较多代码修改才能落地 |

---

## 2. 与现有实现的差异分析

### 2.1 🔴 关键差异（必须解决）

| 问题 | 设计方案 | 现有实现 | 影响 |
|------|----------|----------|------|
| **upgrade 依赖 git** | 基于镜像版本升级，无需 git | `cyber-pulse.sh upgrade` 检查 `.git` 目录，没有则退出 | 运维者无法使用 upgrade 命令 |
| **check-deps 检查 git** | 运维者环境无 git | `check-deps.sh` 第 77-79 行报错"不是 Git 仓库" | 运维者部署时会报错 |
| **部署包不存在** | GitHub Release 提供部署包 | GitHub Actions 只构建 Docker 镜像 | `install.sh --type ops` 无法下载 |

### 2.2 🟡 中等差异（建议解决）

| 问题 | 设计方案 | 现有实现 | 影响 |
|------|----------|----------|------|
| **install.sh 行为** | 下载 + 自动部署 | 仅下载文件，提示手动 deploy | 需要修改 install.sh |
| **.version 文件** | 部署时创建 | 不存在 | 版本检测依赖 git |
| **`__version__` 不同步** | 从 `.version` 或环境变量读取 | 硬编码 `"1.3.0"`，实际已 v1.5.0 | API 返回错误版本 |
| **CYBER_PULSE_VERSION** | 写入 `.env` | `generate-env.sh` 未生成此变量 | 无法通过 `.env` 控制镜像版本 |

### 2.3 🟢 已正确实现

| 功能 | 现有实现 | 说明 |
|------|----------|------|
| Admin Key 生成 | `startup.py` 首次运行生成，仅显示一次 | ✅ 符合设计 |
| 快照创建/恢复 | `create-snapshot.sh` / `restore-snapshot.sh` | ✅ 完整实现 |
| 备份创建/恢复 | `create-backup.sh` / `restore-backup.sh` | ✅ 完整实现 |
| Docker Compose 配置 | 三级配置覆盖（dev/test/prod） | ✅ 设计方案建议简化为两级 |
| 镜像仓库 | 阿里云公开仓库 | ✅ 无需认证 |
| 健康检查 | `/health` 端点 | ✅ 已实现 |

---

## 3. 详细问题分析

### 3.1 upgrade 命令依赖 git（最关键）

**当前实现**（`scripts/cyber-pulse.sh` 第 659-763 行）：

```bash
# 检查 git 仓库
if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
    die "当前目录不是 git 仓库，无法使用 upgrade 命令"
fi

# ...

# 获取代码
print_step "获取最新代码..."
if ! git fetch origin; then
    print_error "git fetch 失败"
    upgrade_failed="true"
fi

# 切换版本
print_step "切换到版本 $target_version..."
if ! git checkout "$target_version" 2>/dev/null; then
    # ...
fi
```

**问题**：运维者环境无 `.git` 目录，upgrade 命令直接退出。

**解决方案**：需要重新设计 upgrade 命令逻辑：

```bash
# 判断环境类型
if [[ -d "$PROJECT_ROOT/.git" ]]; then
    # 开发者模式：使用 git 切换版本
    upgrade_via_git
else
    # 运维者模式：使用镜像版本升级
    upgrade_via_image
fi
```

### 3.2 check-deps.sh 检查 git

**当前实现**（`deploy/init/check-deps.sh` 第 77-79 行）：

```bash
else
    print_error "不是 Git 仓库"
fi
```

**问题**：运维者环境会报错，但实际不影响部署。

**解决方案**：将 git 检查改为警告而非错误：

```bash
else
    print_info "非 Git 仓库（运维部署模式）"
fi
```

### 3.3 部署包构建缺失

**当前实现**（`.github/workflows/docker-publish.yml`）：

```yaml
# 仅构建并推送 Docker 镜像
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    push: true
    tags: |
      ${{ env.REGISTRY }}/${{ env.NAMESPACE }}/${{ env.IMAGE_NAME }}:${{ steps.version.outputs.version }}
      ${{ env.REGISTRY }}/${{ env.NAMESPACE }}/${{ env.IMAGE_NAME }}:latest
```

**问题**：没有构建 `cyber-pulse-deploy-{VERSION}.tar.gz` 部署包。

**解决方案**：在 GitHub Actions 中添加部署包构建步骤：

```yaml
- name: Build deploy package
  run: |
    ./scripts/build-deploy-package.sh --version ${{ steps.version.outputs.version }}

- name: Upload deploy package to Release
  uses: softprops/action-gh-release@v1
  with:
    files: cyber-pulse-deploy-*.tar.gz
```

### 3.4 install.sh 行为差异

**设计方案**：下载 + 自动部署

**当前实现**：仅下载，提示用户手动执行 `deploy`

```bash
# 当前 install.sh 第 246-256 行
echo "  2. 部署服务:"
echo "     ./scripts/cyber-pulse.sh deploy --env prod"
```

**解决方案**：修改 install.sh，在下载完成后自动执行部署：

```bash
# 下载完成后
if [[ "${USER_TYPE}" == "ops" ]]; then
    cd "${INSTALL_DIR}"
    ./scripts/cyber-pulse.sh deploy --env prod
fi
```

### 3.5 版本管理缺失

**当前状态**：

| 项目 | 现状 | 问题 |
|------|------|------|
| `__version__` | `"1.3.0"` | 未同步，实际已是 v1.5.0 |
| `.version` 文件 | 不存在 | 设计方案要求有 |
| `CYBER_PULSE_VERSION` | 未在 `.env` 中 | 无法通过配置控制版本 |

**解决方案**：

1. **`.version` 文件**：部署时创建
   ```bash
   # generate-env.sh 或 deploy 流程中
   echo "${version}" > "$PROJECT_ROOT/.version"
   ```

2. **`__version__` 同步**：从环境变量或 `.version` 文件读取
   ```python
   # src/cyberpulse/__init__.py
   import os
   from pathlib import Path

   def _get_version():
       # 优先从环境变量
       if os.environ.get("APP_VERSION"):
           return os.environ["APP_VERSION"]
       # 从 .version 文件
       version_file = Path(__file__).parent.parent.parent / ".version"
       if version_file.exists():
           return version_file.read_text().strip()
       # 默认值
       return "1.5.0"

   __version__ = _get_version()
   ```

3. **Dockerfile 注入版本**：
   ```dockerfile
   ARG APP_VERSION=latest
   ENV APP_VERSION=$APP_VERSION
   ```

---

## 4. 需要修改的文件清单

### 4.1 必须修改

| 文件 | 修改内容 | 工作量 |
|------|----------|--------|
| `scripts/cyber-pulse.sh` | upgrade 命令支持无 git 环境 | 中 |
| `deploy/init/check-deps.sh` | git 检查改为非阻塞警告 | 小 |
| `.github/workflows/docker-publish.yml` | 添加部署包构建和发布 | 中 |
| `scripts/install.sh` | 添加自动部署逻辑 | 小 |

### 4.2 建议修改

| 文件 | 修改内容 | 工作量 |
|------|----------|--------|
| `src/cyberpulse/__init__.py` | `__version__` 动态读取 | 小 |
| `deploy/init/generate-env.sh` | 添加 `CYBER_PULSE_VERSION` | 小 |
| `Dockerfile` | 构建时注入版本信息 | 小 |

---

## 5. 设计方案补充建议

### 5.1 补充：环境检测逻辑

设计方案应明确环境检测逻辑：

```bash
detect_environment() {
    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        echo "developer"
    else
        echo "ops"
    fi
}
```

### 5.2 补充：upgrade 命令分支逻辑

设计方案应补充 upgrade 命令的分支处理：

```bash
cmd_upgrade() {
    local env_type
    env_type=$(detect_environment)

    if [[ "$env_type" == "developer" ]]; then
        upgrade_developer_mode
    else
        upgrade_ops_mode
    fi
}
```

### 5.3 补充：开发者模式 upgrade 流程

设计方案主要描述运维者模式，应补充开发者模式：

```bash
upgrade_developer_mode() {
    # 1. 创建快照
    # 2. git fetch origin
    # 3. git checkout $target_version
    # 4. docker compose build (--local 模式) 或 pull
    # 5. docker compose up -d
    # 6. alembic upgrade head
    # 7. 健康检查
    # 8. 失败回滚
}
```

### 5.4 补充：部署包内容清单

设计方案应明确部署包包含的文件：

```
cyber-pulse-deploy-{VERSION}.tar.gz
├── scripts/
│   ├── cyber-pulse.sh
│   └── api.sh
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.prod.yml
│   └── init/
│       ├── check-deps.sh
│       └── generate-env.sh
├── sources.yaml
├── .version
├── install-ops.sh
└── README.md
```

---

## 6. 验证建议

### 6.1 开发者环境验证

```bash
# 本地测试环境
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse
./scripts/cyber-pulse.sh deploy --env dev --local

# 验证 upgrade（开发者模式）
./scripts/cyber-pulse.sh upgrade --dry-run
```

### 6.2 运维者环境模拟验证

```bash
# 模拟运维者环境（无 git）
mkdir -p /tmp/ops-test
cd /tmp/ops-test

# 下载部署包（需要先实现 CI 构建）
curl -fsSL https://github.com/cyberstrat-forge/cyber-pulse/releases/download/v1.5.0/cyber-pulse-deploy-v1.5.0.tar.gz | tar xz

cd cyber-pulse
./scripts/cyber-pulse.sh deploy --env prod

# 验证 upgrade（运维者模式）
./scripts/cyber-pulse.sh upgrade --dry-run
```

---

## 7. 结论

设计方案整体思路清晰合理，但与现有实现存在较大差距，主要体现在：

1. **upgrade 命令完全依赖 git**，需要重新设计支持无 git 环境
2. **部署包构建流程缺失**，需要修改 CI/CD
3. **版本管理机制不完整**，需要补充 `.version` 文件和环境变量

**建议**：先修改关键文件实现运维者模式支持，再验证设计方案的可落地性。