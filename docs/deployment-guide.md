# 部署指南

本指南涵盖 Cyber Pulse 在生产环境的完整部署流程。

## 目录

- [环境要求](#环境要求)
- [部署方式](#部署方式)
- [Docker Compose 部署](#docker-compose-部署)
- [手动部署](#手动部署)
- [安全配置](#安全配置)
- [验证部署](#验证部署)
- [生产环境检查清单](#生产环境检查清单)

---

## 环境要求

### 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 存储 | 50 GB SSD | 100 GB+ SSD |

### 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 运行环境 |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 任务队列 |
| Docker | 24+ | 容器运行时（可选） |
| Docker Compose | 2.0+ | 容器编排（可选） |

---

## 部署方式

| 方式 | 适用场景 | 复杂度 |
|------|----------|--------|
| Docker Compose | 生产环境、快速部署 | ⭐ 推荐 |
| 手动部署 | 定制化需求、裸机部署 | ⭐⭐⭐ |

---

## Docker Compose 部署

### 1. 准备配置文件

```bash
# 克隆仓库
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse

# 创建环境变量文件
cp deploy/.env.example deploy/.env
```

### 2. 配置环境变量

编辑 `deploy/.env`：

```bash
# 数据库配置（必需）
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=cyberpulse

# 应用配置
ENVIRONMENT=production
SECRET_KEY=your_secret_key_at_least_32_characters_long
LOG_LEVEL=INFO

# 可选配置
API_HOST=0.0.0.0
API_PORT=8000
```

> ⚠️ **安全警告**:
> - `SECRET_KEY` 必须是至少 32 字符的随机字符串
> - `POSTGRES_PASSWORD` 必须使用强密码
> - 生产环境禁止使用默认值

### 3. 启动服务

```bash
cd deploy

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f api
```

### 4. 服务组件

| 服务 | 端口 | 说明 |
|------|------|------|
| api | 8000 | FastAPI REST API |
| worker | - | Dramatiq 任务处理 |
| scheduler | - | APScheduler 定时调度 |
| postgres | 5432 | PostgreSQL 数据库 |
| redis | 6379 | Redis 缓存/队列 |

### 5. 初始化数据

```bash
# 进入 API 容器
docker-compose exec api bash

# 运行数据库迁移
alembic upgrade head

# 创建管理员客户端
cyberpulse client create "admin" --description "管理员"
```

---

## 手动部署

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .

# 安装生产依赖（如使用 PostgreSQL）
pip install psycopg2-binary
```

### 2. 配置环境变量

创建 `/etc/cyberpulse/config.env`：

```bash
# 数据库
DATABASE_URL=postgresql://cyberpulse:password@localhost:5432/cyberpulse

# Redis
REDIS_URL=redis://localhost:6379/0
DRAMATIQ_BROKER_URL=redis://localhost:6379/1

# 安全
ENVIRONMENT=production
SECRET_KEY=your_secret_key_at_least_32_characters_long

# 日志
LOG_LEVEL=INFO
LOG_FILE=/var/log/cyberpulse/cyberpulse.log
```

### 3. 初始化数据库

```bash
# 创建数据库
createdb -U postgres cyberpulse

# 运行迁移
alembic upgrade head
```

### 4. 配置 Systemd 服务

创建 `/etc/systemd/system/cyberpulse-api.service`：

```ini
[Unit]
Description=Cyber Pulse API Service
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=cyberpulse
Group=cyberpulse
WorkingDirectory=/opt/cyber-pulse
EnvironmentFile=/etc/cyberpulse/config.env
ExecStart=/opt/cyber-pulse/.venv/bin/uvicorn cyberpulse.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

创建 `/etc/systemd/system/cyberpulse-worker.service`：

```ini
[Unit]
Description=Cyber Pulse Worker Service
After=network.target redis.service

[Service]
Type=simple
User=cyberpulse
Group=cyberpulse
WorkingDirectory=/opt/cyber-pulse
EnvironmentFile=/etc/cyberpulse/config.env
ExecStart=/opt/cyber-pulse/.venv/bin/dramatiq cyberpulse.tasks --processes 2 --threads 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

创建 `/etc/systemd/system/cyberpulse-scheduler.service`：

```ini
[Unit]
Description=Cyber Pulse Scheduler Service
After=network.target redis.service

[Service]
Type=simple
User=cyberpulse
Group=cyberpulse
WorkingDirectory=/opt/cyber-pulse
EnvironmentFile=/etc/cyberpulse/config.env
ExecStart=/opt/cyber-pulse/.venv/bin/python -m cyberpulse.scheduler.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5. 启动服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启动服务
systemctl enable --now cyberpulse-api
systemctl enable --now cyberpulse-worker
systemctl enable --now cyberpulse-scheduler

# 检查状态
systemctl status cyberpulse-api
```

---

## 安全配置

### 必需的安全配置

1. **SECRET_KEY** - 必须设置强随机密钥

   ```bash
   # 生成随机密钥
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **数据库密码** - 使用强密码，禁止使用默认值

3. **网络安全**
   - API 服务仅暴露必要的 8000 端口
   - PostgreSQL 和 Redis 不应暴露公网
   - 使用防火墙限制访问

4. **API 文档**
   - 生产环境自动禁用 `/docs` 和 `/redoc`
   - 确保 `ENVIRONMENT=production`

### 推荐的安全配置

1. **HTTPS** - 使用反向代理配置 SSL

   Nginx 示例：

   ```nginx
   server {
       listen 443 ssl http2;
       server_name api.cyberpulse.example.com;

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

2. **API Key 管理**
   - 定期轮换 API Key
   - 为不同系统创建独立客户端
   - 设置合理的过期时间

---

## 验证部署

### 1. 健康检查

```bash
# 检查 API 健康状态
curl http://localhost:8000/health

# 预期响应
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

### 2. API 测试

```bash
# 创建测试客户端
cyberpulse client create "test"

# 使用 API Key 测试
curl -H "Authorization: Bearer cp_live_xxx" \
     http://localhost:8000/api/v1/contents
```

### 3. 系统诊断

```bash
# 运行系统诊断
cyberpulse diagnose system
```

---

## 生产环境检查清单

部署前请确认以下项目：

### 安全配置

- [ ] `SECRET_KEY` 已设置为强随机值（≥32 字符）
- [ ] `POSTGRES_PASSWORD` 已设置为强密码
- [ ] `ENVIRONMENT` 设置为 `production`
- [ ] API 文档已自动禁用（`/docs` 返回 404）
- [ ] 数据库端口未暴露公网
- [ ] Redis 端口未暴露公网

### 功能验证

- [ ] 健康检查端点返回 `healthy`
- [ ] 已创建管理员客户端
- [ ] API Key 认证正常工作
- [ ] 日志正常记录到文件

### 运维配置

- [ ] 配置了日志轮转
- [ ] 配置了数据库备份
- [ ] 配置了监控告警
- [ ] 配置了 HTTPS（推荐）

---

## 常见问题

### 服务无法启动

1. 检查环境变量是否正确设置
2. 检查数据库和 Redis 连接
3. 查看日志：`docker-compose logs api` 或 `journalctl -u cyberpulse-api`

### 数据库连接失败

1. 确认 PostgreSQL 服务运行中
2. 检查 `DATABASE_URL` 格式
3. 检查网络连通性

### Redis 连接失败

1. 确认 Redis 服务运行中
2. 检查 `REDIS_URL` 格式
3. 检查防火墙规则

---

## 下一步

- [API 使用指南](./api-guide.md) - 学习如何使用 API
- [安全配置指南](./security-guide.md) - 详细安全配置
- [故障排查手册](./troubleshooting.md) - 问题诊断与解决