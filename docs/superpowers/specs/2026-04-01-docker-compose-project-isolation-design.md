# Docker Compose 项目名隔离设计

## 概述

### 问题背景

项目存在两个相关问题：

1. **Docker Compose 项目名冲突**（Issue #94）：开发者在 worktree 目录部署测试环境时，会覆盖生产环境的容器和数据
2. **密码不同步**：`.env` 文件中的密码与 Docker volume 中实际初始化的密码不一致

### 根因分析

两个问题本质上是同一个根本原因：**部署环境缺乏唯一标识**。

| 问题 | 根因 |
|------|------|
| 项目名冲突 | 所有环境使用默认项目名 `deploy` |
| 密码不同步 | 不同环境共享同一套 Docker volume，初始化密码不一致 |

### 解决思路

通过设置唯一的 `COMPOSE_PROJECT_NAME` 实现环境隔离：
- 每个环境有独立的容器名、卷名
- 每个环境首次部署时独立初始化密码
- 密码问题自然解决（无需同步）

## 设计目标

1. **环境隔离**：不同环境的容器和卷完全隔离，可同时运行
2. **自动化**：项目名自动生成，无需用户手动配置
3. **安全性**：生产环境不暴露数据库端口
4. **向后兼容**：现有环境不受影响，新部署使用新项目名

## 技术方案

### 项目名命名规则

| 模式 | 环境 | 项目名格式 | 示例 |
|------|------|-----------|------|
| 运维者 | prod | `cyber-pulse-prod` | cyber-pulse-prod-postgres-1 |
| 运维者 | test | `cyber-pulse-test` | cyber-pulse-test-postgres-1 |
| 开发者 | dev | `cyber-pulse-dev-<hash>` | cyber-pulse-dev-a1b2c3d4-postgres-1 |

**开发者模式 hash 规则**：
- 取当前 git 分支名的 MD5 前 8 位
- 避免分支名中特殊字符导致问题
- 不同 worktree 的分支名不同，项目名自然隔离

### 端口分配规则

采用端口偏移量机制：`基础端口 + 环境偏移量`

| 服务 | 基础端口 | prod | test | dev |
|------|---------|------|------|-----|
| API | 8000 | 8000 | 8001 | 8002 |
| PostgreSQL | 5432 | **不暴露** | 5433 | 5434 |
| Redis | 6379 | **不暴露** | 6380 | 6381 |

**端口偏移规则**：
- prod: 偏移量 0
- test: 偏移量 +1
- dev: 偏移量 +2

**生产环境安全**：
- PostgreSQL 和 Redis 端口不对外暴露
- 仅 API 服务暴露 8000 端口

### 实现方式

#### generate-env.sh 修改

**新增检测函数**（脚本自检测，无需外部传参）：

```bash
# 检测运行模式
detect_mode() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local project_root="$(cd "$script_dir/../.." && pwd)"

    # 优先使用环境变量
    if [[ -n "${CYBER_PULSE_MODE:-}" ]]; then
        echo "$CYBER_PULSE_MODE"
        return
    fi
    # 检测是否为 git 仓库
    if [[ -d "$project_root/.git" ]] || [[ -f "$project_root/.git" ]]; then
        echo "developer"
    else
        echo "ops"
    fi
}

# 获取环境
get_current_env() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local project_root="$(cd "$script_dir/../.." && pwd)"
    local env_file="$project_root/.cyber-pulse-env"
    local mode=$(detect_mode)

    # 优先使用环境变量
    if [[ -n "${CYBER_PULSE_ENV:-}" ]]; then
        echo "$CYBER_PULSE_ENV"
        return
    fi

    # 读取环境覆盖文件
    if [[ -f "$env_file" ]]; then
        cat "$env_file"
        return
    fi

    # 根据模式返回默认环境
    case "$mode" in
        ops)      echo "prod" ;;  # 运维者默认 prod
        developer) echo "dev" ;;   # 开发者默认 dev
    esac
}

**Why**: 当前 `cyber-pulse.sh` 中的 `get_current_env()` 默认返回 `dev`，这对于运维者模式不合理。运维者通常部署生产环境，应默认 `prod`。此修复确保不同模式有正确的默认环境。

# 生成项目名
generate_project_name() {
    local mode=$(detect_mode)
    local env=$(get_current_env)

    case "$mode" in
        developer)
            # 开发者模式：使用分支名哈希
            local branch
            branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo "main")
            local hash=$(echo -n "$branch" | md5sum | cut -c1-8)
            echo "cyber-pulse-dev-${hash}"
            ;;
        ops)
            # 运维者模式：根据环境命名
            echo "cyber-pulse-${env}"
            ;;
    esac
}

# 生成端口配置
generate_ports() {
    local env="$1"

    case "$env" in
        prod)
            echo "API_PORT=8000"
            echo "# 生产环境不暴露数据库端口"
            ;;
        test)
            echo "API_PORT=8001"
            echo "POSTGRES_PORT=5433"
            echo "REDIS_PORT=6380"
            ;;
        dev|*)
            echo "API_PORT=8002"
            echo "POSTGRES_PORT=5434"
            echo "REDIS_PORT=6381"
            ;;
    esac
}
```

**修改生成配置函数**：

```bash
generate_env_file() {
    local force="${1:-false}"
    local mode=$(detect_mode)
    local env=$(get_current_env)
    local project_name=$(generate_project_name)

    # ... 生成密码逻辑保持不变 ...

    cat > "$ENV_FILE" << EOF
# ==============================================
# Cyber Pulse 配置文件
# 自动生成于: $(date '+%Y-%m-%d %H:%M:%S')
# ==============================================

# Docker Compose 项目名（环境隔离）
COMPOSE_PROJECT_NAME=${project_name}

# 端口配置
$(generate_ports "$env")

# 数据库配置
POSTGRES_USER=${db_user}
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_DB=${db_name}

# ... 其他配置保持不变 ...
EOF
}
```

#### docker-compose.yml 修改

端口配置改为变量：

```yaml
services:
  postgres:
    ports:
      - "${POSTGRES_PORT:-5432}:5432"

  redis:
    ports:
      - "${REDIS_PORT:-6379}:6379"

  api:
    ports:
      - "${API_PORT:-8000}:8000"
```

#### docker-compose.prod.yml 修改

显式覆盖端口配置，确保生产环境安全：

```yaml
services:
  postgres:
    ports: []  # 显式不暴露
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
    # ... 其他配置 ...

  redis:
    ports: []  # 显式不暴露
    deploy:
      # ... 其他配置 ...

  api:
    ports:
      - "${API_PORT:-8000}:8000"  # 仅 API 暴露
    deploy:
      # ... 其他配置 ...
```

**Why**: Docker Compose overlay 机制是合并配置而非替换。如果不显式设置 `ports: []`，生产环境会继承 `docker-compose.yml` 中的端口暴露配置，导致 PostgreSQL 和 Redis 端口对外暴露的安全隐患。

#### cyber-pulse.sh 修改

修复 `get_current_env()` 函数，根据运行模式返回正确的默认环境：

```bash
# 获取当前环境
get_current_env() {
    local env_file="$PROJECT_ROOT/.cyber-pulse-env"
    local mode=$(detect_mode)

    # 优先使用环境变量
    if [[ -n "${CYBER_PULSE_ENV:-}" ]]; then
        echo "$CYBER_PULSE_ENV"
        return
    fi

    # 读取环境覆盖文件
    if [[ -f "$env_file" ]]; then
        cat "$env_file"
        return
    fi

    # 根据模式返回默认环境
    case "$mode" in
        ops)      echo "prod" ;;  # 运维者默认 prod
        developer) echo "dev" ;;   # 开发者默认 dev
    esac
}
```

**Why**: 当前 `cyber-pulse.sh` 中 `get_current_env()` 默认返回 `dev`，这对运维者模式不合理。运维者通常部署生产环境，应默认 `prod`。

#### docker-compose.test.yml 和 docker-compose.dev.yml 修改

移除端口硬编码，继承 `docker-compose.yml` 的变量配置：

```yaml
# docker-compose.test.yml
services:
  postgres:
    # 移除 ports 配置，继承 base 的变量配置
    deploy:
      resources:
        # ... 保持现有配置 ...
```

```yaml
# docker-compose.dev.yml
services:
  postgres:
    # 移除 ports 配置，继承 base 的变量配置
  redis:
    # 移除 ports 配置
  api:
    # 移除 ports 配置
    volumes:
      # ... 保持现有的热重载配置 ...
```

### .env 文件结构

生成后的 `.env` 文件示例：

```bash
# ==============================================
# Cyber Pulse 配置文件
# 自动生成于: 2026-04-01 12:00:00
# ==============================================

# Docker Compose 项目名（环境隔离）
COMPOSE_PROJECT_NAME=cyber-pulse-prod

# 端口配置
API_PORT=8000
# 生产环境不暴露数据库端口

# 数据库配置
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=xxxxxxxx
POSTGRES_DB=cyberpulse

# 数据库连接 URL（Docker 内部使用）
DATABASE_URL=postgresql://cyberpulse:xxxxxxxx@postgres:5432/cyberpulse

# Redis 配置
REDIS_URL=redis://redis:6379/0

# Dramatiq 消息队列
DRAMATIQ_BROKER_URL=redis://redis:6379/1

# ... 其他配置 ...
```

## 文档更新

### developer-deployment-guide.md 更新

1. **端口表更新**：

```markdown
## 端口分配

端口基于环境自动分配，规则：`基础端口 + 环境偏移量`

| 服务 | 基础端口 | dev 环境 |
|------|---------|---------|
| API | 8000 | 8002 |
| PostgreSQL | 5432 | 5434 |
| Redis | 6379 | 6381 |

> **为什么 dev 端口偏移 +2？** 为了支持在同一台机器同时运行 prod、test、dev 三套环境。
```

2. **清理命令更新**：

```markdown
## 清理环境

### 一步式清理（推荐）

\`\`\`bash
cd deploy && docker compose down -v && cd ..
\`\`\`

> 此命令会自动使用正确的项目名，无需手动指定卷名。
```

3. **新增环境隔离说明**：

```markdown
## 环境隔离

每个 worktree 自动获得独立的项目名（基于分支哈希），不同 worktree 的容器和数据完全隔离。

### 查看当前项目名

\`\`\`bash
docker compose config | grep project_name
\`\`\`
```

### ops-deployment-guide.md 更新

1. **端口表更新**：

```markdown
## 端口分配

| 环境 | API | PostgreSQL | Redis |
|------|-----|------------|-------|
| prod | 8000 | 不暴露 | 不暴露 |
| test | 8001 | 5433 | 6380 |

**生产环境安全**：PostgreSQL 和 Redis 端口不对外暴露。
```

2. **新增多环境部署说明**：

```markdown
## 多环境部署

可在同一台服务器部署多套环境：

\`\`\`bash
# 生产环境
./scripts/cyber-pulse.sh deploy --env prod
# 项目名: cyber-pulse-prod, API: 8000

# 测试环境
./scripts/cyber-pulse.sh deploy --env test
# 项目名: cyber-pulse-test, API: 8001
\`\`\`

两套环境的容器、数据卷完全隔离。
```

3. **新增迁移指南**：

```markdown
## 从旧版本迁移

如果您已有运行中的环境（项目名 `deploy`），升级后建议迁移：

### 迁移步骤

1. **备份数据**：
   \`\`\`bash
   ./scripts/cyber-pulse.sh snapshot create --name pre-migration
   \`\`\`

2. **停止旧环境**：
   \`\`\`bash
   cd deploy && docker compose down && cd ..
   \`\`\`

3. **重新生成配置**：
   \`\`\`bash
   ./scripts/cyber-pulse.sh config generate --force
   \`\`\`

4. **重新部署**：
   \`\`\`bash
   ./scripts/cyber-pulse.sh deploy --env prod
   \`\`\`

5. **删除旧数据卷**（可选，如不需要旧数据）：
   \`\`\`bash
   docker volume rm deploy_postgres_data deploy_redis_data
   \`\`\`
```

## 边界情况处理

### 已存在环境

- **向后兼容**：现有环境（项目名 `deploy`）不受影响
- **新部署**：使用新的项目名规则
- **迁移**：提供迁移指南，但非强制

### 分支名哈希冲突

- **概率**：16^8 ≈ 43 亿种可能，冲突概率极低
- **影响**：即使冲突，只是两个开发环境共享容器，开发者会注意到
- **处理**：无需特殊处理

### 开发者切换分支

- **行为**：切换分支后项目名变化
- **处理**：需要重新部署（`deploy --local`）
- **理由**：保持简单，每个分支数据独立

### 端口已被占用

- **检测**：部署前检查端口可用性
- **处理**：提示用户修改 `.env` 中的端口配置

## 修改文件清单

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `deploy/init/generate-env.sh` | 新增项目名检测、端口分配逻辑 | 高 |
| `scripts/cyber-pulse.sh` | 修复 `get_current_env()` 根据模式返回默认环境 | 高 |
| `deploy/docker-compose.yml` | 端口改为变量 | 高 |
| `deploy/docker-compose.prod.yml` | 添加 `ports: []` 覆盖 | 高（安全） |
| `deploy/docker-compose.test.yml` | 移除端口硬编码 | 中 |
| `deploy/docker-compose.dev.yml` | 移除端口硬编码 | 中 |
| `docs/developer-deployment-guide.md` | 更新端口表、清理命令、环境隔离说明 | 中 |
| `docs/ops-deployment-guide.md` | 更新端口表、多环境说明、迁移指南 | 中 |

## 测试计划

1. **单元测试**：测试 `generate-env.sh` 的项目名生成逻辑
2. **集成测试**：
   - 验证 prod/test/dev 环境可同时运行
   - 验证生产环境 PostgreSQL/Redis 端口不暴露
   - 验证不同 worktree 的容器隔离
3. **升级测试**：验证从旧版本迁移流程

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 旧环境迁移数据丢失 | 低 | 高 | 提供迁移文档，建议备份 |
| 端口冲突 | 中 | 低 | 文档说明如何修改端口配置 |
| 开发者不习惯新端口 | 中 | 低 | 文档清晰说明端口规则 |

## 参考资料

- Issue #94: Docker Compose 项目名冲突
- Issue 相关问题：密码不同步
- Docker Compose 文档：https://docs.docker.com/compose/project-name/