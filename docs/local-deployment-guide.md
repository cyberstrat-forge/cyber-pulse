# 本地测试环境部署指南（Worktree）

本文档指导如何在 Git Worktree 环境中部署测试环境，用于 PR 验证和开发测试。

## 前置条件

- Docker 和 Docker Compose 已安装
- 已 clone 主仓库
- 有访问权限的 PR 分支

## 快速开始

```bash
# 1. 进入 worktree 目录
cd /Users/luoweirong/cyberstrat-forge/cyber-pulse/.worktrees/<branch-name>

# 2. 停止并清理旧环境
./scripts/cyber-pulse.sh stop --env test
docker volume rm deploy_postgres_data deploy_redis_data 2>/dev/null || true

# 3. 本地构建并部署测试环境
./scripts/cyber-pulse.sh deploy --env test --local

# 4. 等待服务启动后，获取 Admin Key
sleep 10
docker logs deploy-api-1 2>&1 | grep -A2 "Admin API Key" | head -6

# 5. 配置 api.sh
./scripts/api.sh configure
# 输入 API URL: http://localhost:8000
# 输入 Admin Key: cp_live_xxx（从步骤4获取）

# 6. 验证部署
./scripts/api.sh diagnose
```

## 命令详解

### 部署命令

```bash
# 本地构建部署（开发测试用，使用本地代码构建镜像）
./scripts/cyber-pulse.sh deploy --env test --local

# 远程镜像部署（运维人员用，从镜像仓库拉取）
./scripts/cyber-pulse.sh deploy --env test
```

### 管理命令

```bash
# 查看服务状态
./scripts/cyber-pulse.sh status

# 查看日志
./scripts/cyber-pulse.sh logs [api|worker|scheduler|postgres|redis]

# 停止服务
./scripts/cyber-pulse.sh stop --env test

# 重启服务
./scripts/cyber-pulse.sh restart --env test
```

### API 管理命令

```bash
# 配置 API 连接
./scripts/api.sh configure

# 系统诊断
./scripts/api.sh diagnose

# 情报源管理
./scripts/api.sh sources list
./scripts/api.sh sources create --name "名称" --type rss --url "RSS_URL" --tier T0
./scripts/api.sh sources get <source_id>
./scripts/api.sh sources update <source_id>  # 使用 curl 直接调用

# 任务管理
./scripts/api.sh jobs list
./scripts/api.sh jobs get <job_id>

# 触发采集任务（使用 curl）
curl -X POST -H "Authorization: Bearer <admin_key>" -H "Content-Type: application/json" \
  -d '{"type": "ingest", "source_id": "<source_id>"}' \
  http://localhost:8000/api/v1/admin/jobs

# 客户端管理
./scripts/api.sh clients list
```

## 常见问题

### 1. 数据库迁移失败

**症状**: 容器日志显示迁移错误

**解决**:
```bash
# 完全清理数据库 volume 后重新部署
./scripts/cyber-pulse.sh stop --env test
docker volume rm deploy_postgres_data deploy_redis_data
./scripts/cyber-pulse.sh deploy --env test --local
```

### 2. Git Worktree 检查失败

**症状**: `check-deps.sh` 报告 "不是 Git 仓库"

**解决**: 确保 `deploy/init/check-deps.sh` 包含 worktree 支持：
```bash
if [[ -d "$PROJECT_ROOT/.git" ]] || [[ -f "$PROJECT_ROOT/.git" ]]; then
```

### 3. Admin Key 未显示

**症状**: 日志中没有 Admin Key

**解决**:
```bash
# 检查数据库中是否有 admin client
docker exec deploy-postgres-1 psql -U cyberpulse -d cyberpulse \
  -c "SELECT client_id, name FROM api_clients WHERE permissions @> '[\"admin\"]';"

# 如果没有，重启 API 容器触发创建
docker restart deploy-api-1
sleep 5
docker logs deploy-api-1 2>&1 | grep -A2 "Admin API Key"
```

### 4. 端口冲突

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

## 验证清单

部署完成后，执行以下验证：

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 系统诊断
./scripts/api.sh diagnose

# 3. 创建测试源
curl -X POST -H "Authorization: Bearer <admin_key>" -H "Content-Type: application/json" \
  -d '{"name": "Test Source", "connector_type": "rss", "config": {"feed_url": "https://example.com/feed.xml"}}' \
  http://localhost:8000/api/v1/admin/sources

# 4. 触发采集并检查结果
# ... 使用 jobs API
```

## 清理环境

```bash
# 停止服务并清理数据
./scripts/cyber-pulse.sh stop --env test
docker volume rm deploy_postgres_data deploy_redis_data

# 完全清理（包括镜像）
docker rmi cyber-pulse:test 2>/dev/null || true
docker image prune -f
```

## 目录结构

```
.worktrees/<branch-name>/
├── scripts/
│   ├── cyber-pulse.sh      # 部署管理脚本
│   └── api.sh              # API 管理脚本
├── deploy/
│   ├── docker-compose.yml
│   ├── docker-compose.test.yml
│   ├── docker-compose.local.yml
│   └── .env                # 生成的配置文件
├── alembic/versions/       # 数据库迁移
└── src/cyberpulse/         # 源代码
```

## 配置文件

- **API 配置**: `~/.config/cyber-pulse/config` (由 api.sh configure 生成)
- **部署配置**: `deploy/.env` (由 cyber-pulse.sh deploy 生成)