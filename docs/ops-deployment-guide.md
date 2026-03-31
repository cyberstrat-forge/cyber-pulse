# 运维者部署指南

本文档指导运维人员部署 Cyber Pulse 生产环境或测试环境。

## 运维者模式说明

运维者模式适用于生产环境和测试环境，无需源代码，仅使用远程镜像部署。

| 特性 | 说明 |
|------|------|
| **获取方式** | 下载部署包或使用安装脚本 |
| **镜像来源** | 阿里云容器镜像仓库（国内加速） |
| **本地构建** | 不需要 |
| **版本管理** | 使用 tag 版本号（如 v1.5.0） |
| **升级方式** | `cyber-pulse.sh upgrade` |

## 前置条件

- Docker 和 Docker Compose 已安装
- 网络可访问阿里云容器镜像仓库

## 快速开始

### 方式一：一键安装（推荐）

```bash
# 安装最新版本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops

# 安装指定版本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops --version v1.5.0

# 安装到指定目录
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash -s -- --type ops --dir /opt/cyber-pulse
```

安装完成后，进入目录并部署：

```bash
cd cyber-pulse
./scripts/cyber-pulse.sh deploy --env prod
```

### 方式二：下载部署包

从 GitHub Releases 下载部署包：

```bash
# 下载部署包
wget https://github.com/cyberstrat-forge/cyber-pulse/releases/download/v1.5.0/cyber-pulse-deploy-v1.5.0.tar.gz

# 解压
tar -xzf cyber-pulse-deploy-v1.5.0.tar.gz

# 进入目录
cd cyber-pulse

# 安装
./install-ops.sh
```

部署成功后，终端会显示 **Admin API Key**，请立即保存！

```bash
# 配置 API 管理（使用部署输出的 Key）
./scripts/api.sh configure --url http://localhost:8000 --key cp_live_xxxxx

# 验证部署
./scripts/api.sh diagnose
```

## 目录结构

```
cyber-pulse/                    # 安装目录
├── scripts/
│   ├── cyber-pulse.sh          # 部署管理脚本
│   └── api.sh                  # API 管理脚本
├── deploy/
│   ├── docker-compose.yml      # Docker Compose 配置
│   ├── docker-compose.prod.yml # 生产环境覆盖
│   ├── docker-compose.test.yml # 测试环境覆盖
│   ├── .env                    # 配置文件（自动生成）
│   ├── data/                   # 持久化数据
│   ├── logs/                   # 日志文件
│   └── init/                   # 初始化脚本
├── sources.yaml                # 情报源配置
├── .version                    # 版本文件
└── install-ops.sh              # 安装脚本
```

## 命令详解

### 部署命令

```bash
# 生产环境（使用远程镜像）
./scripts/cyber-pulse.sh deploy --env prod

# 测试环境
./scripts/cyber-pulse.sh deploy --env test
```

### 升级命令

```bash
# 升级到最新版本
./scripts/cyber-pulse.sh upgrade

# 升级到指定版本
./scripts/cyber-pulse.sh upgrade --version v1.6.0
```

升级流程：
1. 拉取新版本镜像
2. 备份当前数据库
3. 执行数据库迁移
4. 重启服务
5. 验证服务健康

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

### 版本管理

```bash
# 查看当前版本
cat .version

# 版本格式: v1.5.0（tag 版本号）
```

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

## 获取 Admin API Key

Admin API Key 在首次部署时自动生成并显示在终端。如果需要重新获取：

```bash
# 重置 Admin Key（旧 Key 失效）
./scripts/cyber-pulse.sh admin reset --force
```

> ⚠️ **重要**：Admin Key 重置后，之前配置的客户端需要更新配置。

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

> ⚠️ **警告**：生产环境执行此操作将丢失所有业务数据，请谨慎操作！

### 方法二：分步清理

如果只想清空数据但保留网络配置：

```bash
# 1. 停止服务
./scripts/cyber-pulse.sh stop

# 2. 删除数据卷（清空数据库和 Redis）
docker volume rm deploy_postgres_data deploy_redis_data

# 3. 清理悬空镜像（可选）
docker image prune -f
```

### 对比

| 方法 | 命令 | 适用场景 |
|------|------|----------|
| **一步式** | `docker compose down -v` | 测试环境完全重置 |
| **分步式** | `stop` + `volume rm` | 清空数据但保留配置 |

> 💡 **说明**：生产环境通常不需要清理数据卷，升级时系统会自动备份和迁移。

## 常见问题

### 1. 镜像拉取失败

**症状**: `Error: image pull failed`

**原因**: 网络问题或镜像不存在

**解决**:
```bash
# 检查网络连接
ping crpi-tuxci06y0zyoionf.cn-guangzhou.personal.cr.aliyuncs.com

# 手动拉取镜像测试
docker pull crpi-tuxci06y0zyoionf.cn-guangzhou.personal.cr.aliyuncs.com/cyberstrat-forge/cyber-pulse:latest
```

### 2. Admin Key 未显示

**症状**: 部署完成但未看到 Admin Key

**原因**: 数据卷保留了旧数据，admin client 已存在

**解决**:
```bash
# 重置 Admin Key
./scripts/cyber-pulse.sh admin reset --force
```

### 3. 数据库迁移失败

**症状**: 容器日志显示迁移错误

**解决**:
```bash
# 检查日志
./scripts/cyber-pulse.sh logs api

# 如需重置数据库（⚠️ 数据将丢失）
./scripts/cyber-pulse.sh stop
docker volume rm deploy_postgres_data deploy_redis_data
./scripts/cyber-pulse.sh deploy --env prod
```

### 4. 端口冲突

**症状**: 部署时端口已被占用

**解决**:
```bash
# 查看端口占用
lsof -i :8000

# 停止冲突的容器
docker stop <container_name>
```

### 5. 升级失败回滚

**症状**: 升级后服务异常

**解决**:
```bash
# 查看快照列表
./scripts/cyber-pulse.sh snapshot list

# 手动恢复快照（升级失败时会自动回滚，通常无需手动操作）
./scripts/cyber-pulse.sh snapshot restore snap_xxxx --force
```

> 💡 **说明**：升级失败时会自动触发回滚，无需手动执行。

## 验证清单

部署完成后，执行以下验证：

```bash
# 1. 健康检查
curl http://localhost:8000/health

# 2. 系统诊断
./scripts/api.sh diagnose

# 3. 版本确认
cat .version
curl -s http://localhost:8000/health | jq '.version'

# 4. 创建测试源
./scripts/api.sh sources create --name "Test" --type rss --url "https://example.com/feed.xml"

# 5. 运行采集任务
./scripts/api.sh jobs run <source_id>
```

## 配置文件

| 文件 | 说明 |
|------|------|
| `~/.config/cyber-pulse/config` | API 管理配置（api.sh） |
| `deploy/.env` | 部署配置（数据库密码等） |
| `sources.yaml` | 情报源配置 |
| `.version` | 版本追踪文件 |

## 安全建议

1. **Admin Key 管理**
   - 妥善保存首次部署时生成的 Key
   - 定期轮换 Key（使用 `admin reset`）
   - 为不同用途创建独立客户端

2. **网络安全**
   - 生产环境应配置防火墙规则
   - 仅开放必要的 API 端口（8000）
   - 考虑使用反向代理（Nginx）配置 HTTPS

3. **数据备份**
   - 定期备份 PostgreSQL 数据
   - 升级前自动备份到 `deploy/backup/`

## 监控与日志

```bash
# 实时查看日志
./scripts/cyber-pulse.sh logs -f api

# 查看最近 100 行日志
./scripts/cyber-pulse.sh logs api --tail 100

# 日志文件位置
ls deploy/logs/
```

## 版本发布说明

| 版本 | 说明 |
|------|------|
| v1.5.0 | 两级全文采集、速率限制、调度重试 |
| v1.4.0 | API 架构重构、Admin API、作业追踪 |
| v1.3.0 | 基础功能稳定版 |

详细变更记录请查看 [CHANGELOG.md](https://github.com/cyberstrat-forge/cyber-pulse/blob/main/CHANGELOG.md)。