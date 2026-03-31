# 本地测试环境部署指南

本文档指导如何部署测试环境，用于 PR 验证和开发测试。

## 开发模式说明

遵循 `superpowers:subagent-driven-development` 工作流，开发者在 Worktree 特性分支上开发：

| 场景 | 分支 | 操作 |
|------|------|------|
| **Worktree 开发** | 特性分支 | `deploy --local` 部署当前代码，**不使用 upgrade** |
| **主分支维护** | main/master | `deploy` 部署，`upgrade` 升级到最新版本 |

> ⚠️ **重要**：在特性分支上执行 `upgrade` 命令会提示退出，建议使用 `deploy --local` 部署当前代码。

## 前置条件

- Docker 和 Docker Compose 已安装
- 已 clone 主仓库或 worktree

## 快速开始

### 首次部署

```bash
# 1. 部署开发环境（本地构建）
./scripts/cyber-pulse.sh deploy --env dev --local
```

### 清除旧环境重新部署

如果需要完全清除测试数据（数据库、Redis、业务数据）重新部署：

```bash
# 一步式清理（推荐）
cd deploy && docker compose down -v && cd ..

# 然后重新部署
./scripts/cyber-pulse.sh deploy --env dev --local
```

> 💡 **说明**：`docker compose down -v` 会停止服务、移除容器、删除数据卷。这是清除测试环境的最完整方式。

部署成功后，终端会显示 **Admin API Key**，请立即保存！

```bash
# 2. 配置 API 管理（使用部署输出的 Key）
./scripts/api.sh configure --url http://localhost:8000 --key cp_live_xxxxx

# 3. 验证部署
./scripts/api.sh diagnose
```

## 获取 Admin API Key

Admin API Key 在首次部署时自动生成并显示在终端。如果需要重新获取：

```bash
# 重置 Admin Key（旧 Key 失效）
./scripts/cyber-pulse.sh admin reset --force
```

> 💡 **提示**：开发模式下，Admin Key 在部署完成后自动显示，无需手动从日志获取。

## 命令详解

### 部署命令

```bash
# 开发环境（本地构建，支持热重载）
./scripts/cyber-pulse.sh deploy --env dev --local

# 测试环境（本地构建）
./scripts/cyber-pulse.sh deploy --env test --local

# 使用远程镜像（运维模式）
./scripts/cyber-pulse.sh deploy --env prod
```

### 服务管理

```bash
# 查看状态
./scripts/cyber-pulse.sh status

# 查看日志
./scripts/cyber-pulse.sh logs [api|worker|scheduler|postgres|redis]

# 停止服务
./scripts/cyber-pulse.sh stop

# 重启服务
./scripts/cyber-pulse.sh restart
```

### 版本显示

```bash
# 查看当前版本
cat .version

# 在 main 分支（有 tag）: v1.5.0
# 在特性分支: v1.5.0-25-gb596d0b (git describe 格式)
```

### 端口映射（开发模式）

开发模式默认启用以下端口映射，便于本地调试和测试：

| 服务 | 端口 | 用途 |
|------|------|------|
| API | 8000 | REST API 访问 |
| PostgreSQL | 5432 | 数据库直连（测试/调试） |
| Redis | 6379 | 缓存直连（调试） |

> ⚠️ **生产环境**：使用 `docker-compose.prod.yml` 部署，端口不对外暴露。

### API 管理

```bash
# 配置 API 连接（交互式）
./scripts/api.sh configure

# 配置 API 连接（非交互式）
./scripts/api.sh configure --url http://localhost:8000 --key cp_live_xxx

# 系统诊断
./scripts/api.sh diagnose

# 情报源管理
./scripts/api.sh sources list
./scripts/api.sh sources create --name "名称" --type rss --url "URL" --tier T0
./scripts/api.sh sources test <source_id>

# 任务管理
./scripts/api.sh jobs list
./scripts/api.sh jobs run <source_id>

# 客户端管理
./scripts/api.sh clients list
```

## 清理环境

### 方法一：一步式清理（推荐）

清除所有数据并重新部署的最完整方式：

```bash
# 停止服务、移除容器、删除数据卷
cd deploy && docker compose down -v && cd ..
```

此命令执行以下操作：
- 停止所有运行中的容器
- 移除容器（api、worker、scheduler、postgres、redis）
- 删除数据卷（postgres_data、redis_data）
- 移除网络

执行后数据库和 Redis 数据完全清空，重新部署将从空白状态开始。

### 方法二：分步清理

如果只想清空数据但保留网络配置：

```bash
# 1. 停止服务
./scripts/cyber-pulse.sh stop

# 2. 删除数据卷（清空数据库和 Redis）
docker volume rm deploy_postgres_data deploy_redis_data

# 3. 清理悬空镜像（可选）
docker rmi cyber-pulse:dev 2>/dev/null || true
docker image prune -f
```

### 对比

| 方法 | 命令 | 适用场景 |
|------|------|----------|
| **一步式** | `docker compose down -v` | 完全重新部署、端到端测试 |
| **分步式** | `stop` + `volume rm` | 清空数据但保留容器配置 |

## 常见问题

### 1. Admin Key 未显示

**症状**: 部署完成但未看到 Admin Key

**原因**: 数据卷保留了旧数据，admin client 已存在

**解决**:
```bash
# 重置 Admin Key
./scripts/cyber-pulse.sh admin reset --force
```

### 2. 数据库迁移失败

**症状**: 容器日志显示迁移错误

**解决**:
```bash
# 完全清理后重新部署
./scripts/cyber-pulse.sh stop
docker volume rm deploy_postgres_data deploy_redis_data
./scripts/cyber-pulse.sh deploy --env dev --local
```

### 3. 端口冲突

**症状**: 部署时端口已被占用

**解决**:
```bash
# 查看端口占用
lsof -i :8000
lsof -i :5432
lsof -i :6379

# 停止冲突的容器
docker stop <container_name>
```

### 4. API 认证失败

**症状**: `./scripts/api.sh diagnose` 返回 "Invalid or expired API key"

**解决**:
```bash
# 1. 确认配置正确
cat ~/.config/cyber-pulse/config

# 2. 重置 Key 并更新配置
./scripts/cyber-pulse.sh admin reset --force
# 复制新 Key
./scripts/api.sh configure --url http://localhost:8000 --key <new_key>
```

## 验证清单

部署完成后，执行以下验证：

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 系统诊断
./scripts/api.sh diagnose

# 3. 创建测试源
./scripts/api.sh sources create --name "Test" --type rss --url "https://example.com/feed.xml"

# 4. 运行采集任务
./scripts/api.sh jobs run <source_id>
```

## 运行测试套件

测试套件会自动使用部署环境的数据库配置：

```bash
# 运行所有测试
uv run pytest tests/

# 运行特定测试
uv run pytest tests/test_services/ -v

# 查看测试摘要
uv run pytest tests/ -q --tb=no
```

> 💡 **说明**：`tests/conftest.py` 会自动读取 `deploy/.env` 中的数据库配置，无需手动设置环境变量。

## 配置文件

| 文件 | 说明 |
|------|------|
| `~/.config/cyber-pulse/config` | API 管理配置（api.sh） |
| `deploy/.env` | 部署配置（数据库密码等） |
| `.version` | 版本追踪文件 |