# 部署指南

本指南涵盖 Cyber Pulse 的完整部署流程，包括多环境部署配置。

## 目录

- [环境要求](#环境要求)
- [快速部署](#快速部署)
- [多环境部署](#多环境部署)
- [管理命令详解](#管理命令详解)
- [安全配置](#安全配置)
- [验证部署](#验证部署)
- [生产环境检查清单](#生产环境检查清单)

---

## 环境要求

### 必需软件

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Docker | 24+ | 容器运行环境 |
| git | 任意版本 | 代码获取 |

> **提示**：数据库、Redis 等服务均由 Docker 容器提供，无需单独安装。

### 系统资源

| 环境 | CPU | 内存 | 存储 |
|------|-----|------|------|
| 开发环境 | 2 核 | 4 GB | 50 GB SSD |
| 测试环境 | 2 核 | 4 GB | 50 GB SSD |
| 生产环境 | 4 核+ | 8 GB+ | 100 GB+ SSD |

### 验证环境

```bash
docker --version
git --version
```

---

## 快速部署

### 第一步：安装

```bash
# 使用安装脚本
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash

# 进入项目目录
cd cyber-pulse
```

### 第二步：部署

```bash
# 执行部署
./scripts/cyber-pulse.sh deploy
```

部署命令自动完成：

1. **环境检查** - 验证 Docker 和 Docker Compose
2. **配置生成** - 自动生成安全配置（数据库密码、密钥等）
3. **镜像构建** - 构建应用镜像
4. **服务启动** - 启动所有服务
5. **数据库初始化** - 运行迁移脚本

### 第三步：验证

```bash
# 查看服务状态
./scripts/cyber-pulse.sh status

# 健康检查
curl http://localhost:8000/health
```

---

## 多环境部署

Cyber Pulse 支持三种部署环境：

| 环境 | 用途 | 特点 |
|------|------|------|
| dev | 开发环境 | DEBUG 日志、代码热重载、端口全部暴露 |
| test | 测试环境 | INFO 日志、中等资源限制 |
| prod | 生产环境 | WARNING 日志、资源优化、安全加固 |

### 切换环境

```bash
# 设置环境
./scripts/cyber-pulse.sh config set-env dev    # 开发环境
./scripts/cyber-pulse.sh config set-env test   # 测试环境
./scripts/cyber-pulse.sh config set-env prod   # 生产环境

# 查看当前环境
./scripts/cyber-pulse.sh config get-env
```

### 开发环境部署

```bash
# 设置为开发环境
./scripts/cyber-pulse.sh config set-env dev

# 部署
./scripts/cyber-pulse.sh deploy
```

开发环境特点：
- DEBUG 日志级别
- API 代码热重载
- PostgreSQL 5432 端口暴露
- Redis 6379 端口暴露

### 测试环境部署

```bash
# 设置为测试环境
./scripts/cyber-pulse.sh config set-env test

# 部署
./scripts/cyber-pulse.sh deploy
```

测试环境特点：
- INFO 日志级别
- 中等资源限制
- 2 API workers
- 内置验证脚本支持

### 生产环境部署

```bash
# 设置为生产环境
./scripts/cyber-pulse.sh config set-env prod

# 部署
./scripts/cyber-pulse.sh deploy
```

生产环境特点：
- WARNING 日志级别
- 资源优化配置
- 安全加固（数据库端口不暴露）
- API 文档禁用

---

## 管理命令详解

### 服务管理

```bash
# 部署服务
./scripts/cyber-pulse.sh deploy

# 启动服务
./scripts/cyber-pulse.sh start

# 停止服务
./scripts/cyber-pulse.sh stop

# 重启服务
./scripts/cyber-pulse.sh restart

# 查看状态
./scripts/cyber-pulse.sh status
```

### 日志查看

```bash
# 查看所有日志
./scripts/cyber-pulse.sh logs

# 查看特定服务日志
./scripts/cyber-pulse.sh logs api
./scripts/cyber-pulse.sh logs worker
./scripts/cyber-pulse.sh logs scheduler

# 实时跟踪
./scripts/cyber-pulse.sh logs -f api
```

### 配置管理

```bash
# 查看配置
./scripts/cyber-pulse.sh config show

# 设置环境
./scripts/cyber-pulse.sh config set-env prod

# 重新生成安全配置
./scripts/cyber-pulse.sh config regenerate
```

### 升级管理

```bash
# 检查更新
./scripts/cyber-pulse.sh check-update

# 升级系统（自动快照 + 失败回滚）
./scripts/cyber-pulse.sh upgrade
```

### 快照与备份

```bash
# 创建快照（用于升级前备份）
./scripts/cyber-pulse.sh snapshot

# 创建备份
./scripts/cyber-pulse.sh backup

# 恢复备份
./scripts/cyber-pulse.sh restore <backup-file>
```

---

## 安全配置

### 自动配置

部署时自动生成：

- `POSTGRES_PASSWORD` - 数据库密码
- `SECRET_KEY` - 应用密钥

配置文件位置：`<项目根目录>/.env`（权限 600）

### 手动配置

如需自定义配置：

```bash
# 编辑配置文件
nano .env
```

配置示例：

```bash
# 数据库配置
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=your_secure_password_here

# 应用配置
SECRET_KEY=your_secret_key_at_least_32_characters_long
ENVIRONMENT=production
LOG_LEVEL=WARNING

# 可选：外部数据库
# DATABASE_URL=postgresql://user:pass@external-db:5432/cyberpulse
```

### 安全建议

1. **网络安全**
   - 生产环境仅暴露 API 端口 8000
   - 数据库和 Redis 端口不对外暴露

2. **HTTPS 配置**（推荐）
   使用反向代理配置 SSL：

   ```nginx
   server {
       listen 443 ssl http2;
       server_name api.example.com;

       ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. **API Key 管理**
   - 为不同系统创建独立客户端
   - 定期轮换 API Key

---

## 验证部署

### 健康检查

```bash
# API 健康检查
curl http://localhost:8000/health

# 预期响应
# {"status":"healthy","database":"connected","redis":"connected"}
```

### 创建 API 客户端

```bash
# 进入容器
docker compose exec api bash

# 创建客户端
cyberpulse client create "admin" --description "管理员账户"

# 记录 API Key
# Client ID: cli_xxxxxxxxxxxxxxxx
# API Key: cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### API 测试

```bash
# 设置 API Key
export API_KEY="cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 测试 API
curl -H "Authorization: Bearer $API_KEY" \
     "http://localhost:8000/api/v1/contents?limit=5"
```

### 系统诊断

```bash
# 进入容器
docker compose exec api bash

# 运行诊断
cyberpulse diagnose system
```

---

## 生产环境检查清单

### 部署前

- [ ] 环境设置为 `prod`
- [ ] 配置文件权限正确（.env 为 600）
- [ ] 端口 8000 可访问
- [ ] 数据库端口未暴露公网

### 部署后

- [ ] 健康检查返回 `healthy`
- [ ] 已创建管理员客户端
- [ ] API Key 认证正常
- [ ] 日志正常记录

### 运维配置

- [ ] 配置日志轮转
- [ ] 配置数据库备份（`./scripts/cyber-pulse.sh snapshot`）
- [ ] 配置监控告警
- [ ] 配置 HTTPS（推荐）

---

## 常见问题

### 服务无法启动

```bash
# 检查日志
./scripts/cyber-pulse.sh logs

# 检查 Docker 状态
docker info

# 常见原因：
# 1. Docker 服务未启动
# 2. 端口冲突
# 3. 内存不足
```

### 数据库连接失败

```bash
# 检查 PostgreSQL 状态
./scripts/cyber-pulse.sh status

# 查看数据库日志
./scripts/cyber-pulse.sh logs postgres
```

### 配置丢失

```bash
# 重新生成配置
./scripts/cyber-pulse.sh config regenerate
```

---

## 下一步

- [API 使用指南](./api-guide.md) - 下游系统集成
- [备份与恢复](./backup-restore.md) - 数据保护
- [升级迁移指南](./upgrade-guide.md) - 版本升级
- [故障排查手册](./troubleshooting.md) - 问题诊断