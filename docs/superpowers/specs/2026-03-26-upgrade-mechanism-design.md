# 设计文档：应用升级机制

**版本**: 1.0
**日期**: 2026-03-26
**状态**: 待审核

---

## 1. 概述

### 1.1 背景

部署优化阶段1完成后，用户分为两类：
- **开发者**：通过 `git clone` 获取完整代码库
- **运维人员**：通过安装脚本获取轻量部署包（无 `.git` 目录）

两类用户的升级机制不同，需要统一设计。

### 1.2 目标

1. **数据安全**：升级过程不丢失已采集数据
2. **自动化**：升级操作简单，无需人工干预
3. **可回滚**：升级失败自动恢复
4. **配置保留**：用户配置在升级后保留

### 1.3 约束

- 镜像仓库：阿里云容器镜像服务
- 版本检测：GitHub Releases API
- 数据库迁移：Alembic
- 配置文件：sources.yaml

---

## 2. 用户区分与模式选择

### 2.1 判断逻辑

```bash
is_developer_mode() {
    # 1. 检查 .git 目录存在
    [[ -d "$PROJECT_ROOT/.git" ]] || return 1

    # 2. 检查 remote URL 是否为 cyber-pulse 仓库
    local remote_url
    remote_url=$(git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null)
    [[ "$remote_url" == *"cyber-pulse"* ]]
}
```

### 2.2 模式对应

| 条件 | 模式 | 升级命令 |
|------|------|----------|
| `.git` 存在 + remote URL 匹配 | 本地构建模式 | `rebuild` |
| 其他情况 | 远程镜像模式 | `upgrade` |

---

## 3. 本地构建模式（开发者）

### 3.1 适用场景

开发者在开发环境验证当前编写的代码。

### 3.2 部署工作流

```bash
./scripts/cyber-pulse.sh deploy --env dev --local
```

```
预检查 → 生成配置 → 本地构建镜像 → 启动服务 → 数据库初始化 → Admin Key 生成 → 健康检查
```

### 3.3 升级工作流（rebuild）

```bash
./scripts/cyber-pulse.sh rebuild
```

**说明**：开发环境的"升级"实际是重新构建，使用本地当前代码。

```
┌─────────────────────────────────────────────────────────┐
│ 1. 创建快照（自动）                                       │
│    - pg_dump 导出数据库                                  │
│    - 备份 .env、sources.yaml                             │
│    - 保存到 ~/.snapshots/rebuild-YYYYMMDD-HHMMSS/       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. 重新构建镜像                                          │
│    - docker compose build                               │
│    - 使用本地当前代码                                    │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 重启服务                                              │
│    - docker compose down                                │
│    - docker compose up -d                               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. 数据库迁移                                            │
│    - alembic upgrade head                               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 健康检查                                              │
│    - 所有容器运行中？                                     │
│    - API /health 返回 200？                              │
│    - 失败则自动回滚                                      │
└─────────────────────────────────────────────────────────┘
```

### 3.4 回滚机制

| 步骤 | 操作 |
|------|------|
| 恢复数据库 | pg_restore 从快照 |
| 重启服务 | docker compose restart |

**注意**：本地构建模式代码不变，无需回退代码版本。

---

## 4. 远程镜像模式（运维人员）

### 4.1 适用场景

- 运维人员部署生产环境
- 开发者部署测试环境（无 `--local` 参数）

### 4.2 部署工作流

```bash
./scripts/cyber-pulse.sh deploy --env prod
```

```
预检查 → 生成配置 → 拉取镜像（阿里云） → 启动服务 → 数据库初始化 → Admin Key 生成 → 健康检查
```

### 4.3 版本检测

#### 4.3.1 版本信息来源

| 来源 | 用途 | 优先级 |
|------|------|--------|
| `/api/v1/version` | 应用运行时版本 | 高 |
| 镜像 tag | 应用未运行时版本 | 低 |
| GitHub Releases API | 最新可用版本 | 高 |

#### 4.3.2 API 端点设计

```yaml
GET /api/v1/version
Response:
  {
    "version": "1.3.0",
    "commit": "abc1234",
    "build_time": "2026-03-26T10:00:00Z"
  }
```

**实现**：构建时注入环境变量 `APP_VERSION`，API 返回该值。

#### 4.3.3 版本检测逻辑

```bash
get_current_version() {
    # 优先从 API 获取
    local api_version
    api_version=$(curl -s http://localhost:8000/api/v1/version | jq -r '.version' 2>/dev/null)
    if [[ -n "$api_version" && "$api_version" != "null" ]]; then
        echo "$api_version"
        return
    fi

    # 应用未运行，从镜像 tag 获取
    local image_tag
    image_tag=$(docker inspect --format='{{.Config.Image}}' cyberpulse-api-1 2>/dev/null | cut -d: -f2)
    if [[ -n "$image_tag" && "$image_tag" != "latest" ]]; then
        echo "$image_tag"
        return
    fi

    # 无法确定版本
    echo "unknown"
}

get_latest_version() {
    curl -s https://api.github.com/repos/cyberstrat-forge/cyber-pulse/releases/latest | jq -r '.tag_name'
}
```

### 4.4 升级工作流

```bash
./scripts/cyber-pulse.sh upgrade
./scripts/cyber-pulse.sh upgrade --version v1.4.0  # 升级到指定版本
```

```
┌─────────────────────────────────────────────────────────┐
│ 1. 版本检测                                              │
│    - 获取当前版本（API 或镜像 tag）                       │
│    - 获取最新版本（GitHub API）                          │
│    - 比较：当前 < 最新 → 继续                            │
│    - 当前 ≥ 最新 → 提示已是最新，退出                     │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. 创建快照（自动）                                       │
│    - pg_dump 导出数据库                                  │
│    - 备份 .env（便于回滚时对比）                          │
│    - 记录当前版本号（用于回滚）                           │
│    - 保存到 ~/.snapshots/upgrade-YYYYMMDD-HHMMSS/       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 拉取新镜像                                            │
│    - 修改 .env 中的 IMAGE_TAG（如指定版本）              │
│    - docker compose pull                                │
│    - 从阿里云拉取镜像                                    │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. 重启服务                                              │
│    - docker compose down                                │
│    - docker compose up -d                               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 数据库迁移                                            │
│    - alembic upgrade head                               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 6. 健康检查                                              │
│    - 所有容器运行中？                                     │
│    - API /health 返回 200？                              │
│    - /api/v1/version 返回新版本？                        │
└─────────────────────────────────────────────────────────┘
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
           成功                   失败
              ↓                     ↓
        记录日志              自动回滚
              ↓                     ↓
           完成        ┌──────────────────────────┐
                       │ - 恢复数据库快照          │
                       │ - 恢复 .env               │
                       │ - 修改 IMAGE_TAG 为旧版本 │
                       │ - docker compose pull    │
                       │ - docker compose up -d   │
                       └──────────────────────────┘
```

### 4.5 回滚机制

| 步骤 | 操作 |
|------|------|
| 恢复数据库 | pg_restore 从快照 |
| 恢复 .env | 复制快照中的 .env |
| 切换镜像版本 | 修改 `.env` 中的 `IMAGE_TAG` 为旧版本 |
| 拉取旧镜像 | docker compose pull（从阿里云拉取历史版本） |
| 重启服务 | docker compose up -d |

---

## 5. 启动时版本检查

### 5.1 触发时机

- `deploy` 命令
- `start` 命令

### 5.2 检查流程

```
启动服务
    ↓
服务就绪后
    ↓
调用 /api/v1/version → 当前版本
调用 GitHub API → 最新版本
    ↓
比较版本
    ↓
当前 < 最新 → 输出提示：
  "有新版本可用: v1.4.0 (当前: v1.3.0)"
  "运行 ./scripts/cyber-pulse.sh upgrade 进行升级"
    ↓
继续正常启动流程
```

### 5.3 特性

- 不阻断启动
- 仅提示，不自动升级
- 网络失败时静默跳过

---

## 6. 升级日志

### 6.1 日志位置

```
logs/upgrade-YYYYMMDD-HHMMSS.log
```

### 6.2 日志内容

```
[2026-03-26 10:00:00] ========== 升级开始 ==========
[2026-03-26 10:00:00] 当前版本: 1.3.0
[2026-03-26 10:00:00] 目标版本: 1.4.0
[2026-03-26 10:00:01] 创建快照: ~/.snapshots/upgrade-20260326-100001/
[2026-03-26 10:00:05] 拉取镜像: registry.cn-xxx.aliyuncs.com/xxx/cyberpulse-api:latest
[2026-03-26 10:00:30] 重启服务
[2026-03-26 10:00:35] 数据库迁移: alembic upgrade head
[2026-03-26 10:00:36] 健康检查: 通过
[2026-03-26 10:00:36] ========== 升级完成 ==========
```

### 6.3 失败日志

```
[2026-03-26 10:00:00] ========== 升级开始 ==========
[2026-03-26 10:00:00] 当前版本: 1.3.0
[2026-03-26 10:00:00] 目标版本: 1.4.0
[2026-03-26 10:00:01] 创建快照: ~/.snapshots/upgrade-20260326-100001/
[2026-03-26 10:00:05] 拉取镜像: registry.cn-xxx.aliyuncs.com/xxx/cyberpulse-api:latest
[2026-03-26 10:00:30] 重启服务
[2026-03-26 10:00:35] 数据库迁移: alembic upgrade head
[2026-03-26 10:00:40] 健康检查: 失败 - api 容器未运行
[2026-03-26 10:00:40] ========== 升级失败，开始回滚 ==========
[2026-03-26 10:00:41] 恢复数据库快照
[2026-03-26 10:00:45] 拉取旧版本镜像: v1.3.0
[2026-03-26 10:01:00] 重启服务
[2026-03-26 10:01:05] 健康检查: 通过
[2026-03-26 10:01:05] ========== 回滚完成 ==========
```

---

## 7. 命令清单

### 7.1 开发者命令

```bash
# 部署开发环境（本地构建）
./scripts/cyber-pulse.sh deploy --env dev --local

# 重新构建（使用本地当前代码）
./scripts/cyber-pulse.sh rebuild

# 部署测试环境（远程镜像）
./scripts/cyber-pulse.sh deploy --env test

# 升级测试环境
./scripts/cyber-pulse.sh upgrade
```

### 7.2 运维人员命令

```bash
# 部署生产环境
./scripts/cyber-pulse.sh deploy --env prod

# 检查更新
./scripts/cyber-pulse.sh check-update

# 升级到最新版本
./scripts/cyber-pulse.sh upgrade

# 升级到指定版本
./scripts/cyber-pulse.sh upgrade --version v1.4.0
```

---

## 8. 数据持久化保障

### 8.1 存储架构分析

| 数据类型 | 存储位置 | 容器挂载 | 升级时影响 |
|----------|----------|----------|------------|
| PostgreSQL 数据 | Docker named volume | `postgres_data` | ✅ 自动持久化 |
| Redis 数据 | Docker named volume | `redis_data` | ✅ 自动持久化 |
| Admin Key | 数据库（bcrypt 哈希） | - | ✅ 自动持久化 |
| Sources/Clients | 数据库 | - | ✅ 自动持久化 |
| .env | 宿主机 `deploy/.env` | docker-compose 读取 | ✅ 不受镜像升级影响 |

**关键发现**：

- **sources.yaml 不是运行时配置**：它是导入用的初始配置文件，实际 Source 数据存储在数据库中，通过 API 管理
- **.env 在宿主机**：docker-compose 从宿主机读取，镜像升级不会覆盖
- **真正需要保护的只有数据库**：通过 Docker named volume + pg_dump 快照双重保障

### 8.2 快照内容

快照仅需包含：

| 内容 | 保护方式 |
|------|----------|
| PostgreSQL 数据库 | pg_dump 全量导出 |
| .env 文件 | 备份到快照目录（便于回滚时对比） |

**不需要保护**：
- sources.yaml：数据在数据库，文件覆盖无影响
- Redis 数据：缓存性质，可重建

---

## 9. 文件变更清单

### 9.1 新增

| 文件 | 说明 |
|------|------|
| `scripts/upgrade.sh` | 升级脚本（远程镜像模式） |
| `src/cyberpulse/api/routers/version.py` | 版本 API 端点 |

### 9.2 修改

| 文件 | 变更 |
|------|------|
| `scripts/cyber-pulse.sh` | 新增 `rebuild` 命令，修改 `upgrade` 命令逻辑 |
| `deploy/upgrade/check-update.sh` | 支持 API 端点检测 |
| `src/cyberpulse/api/startup.py` | 注入版本环境变量 |
| `Dockerfile` | 构建时注入版本信息 |

---

## 10. 验证清单

### 10.1 功能验证

- [ ] 开发者 `rebuild` 使用本地代码重新构建
- [ ] 运维人员 `upgrade` 从阿里云拉取新镜像
- [ ] 版本检测通过 `/api/v1/version` 获取
- [ ] 升级前自动创建数据库快照
- [ ] 升级失败自动回滚
- [ ] 数据库数据完整保留

### 10.2 安全验证

- [ ] 升级不丢失数据
- [ ] 回滚恢复到升级前状态
- [ ] 升级日志记录完整

---

## 11. 关联文档

- [部署优化阶段1设计](./2026-03-26-deployment-optimization-phase1-design.md)
- [部署指南](../deployment-guide.md)
- [升级指南](../upgrade-guide.md)