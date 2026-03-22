# 环境变量参考

本文档列出 Cyber Pulse 所有支持的环境变量。

## 核心配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | ✅ 是 | - | PostgreSQL 连接串 |
| `REDIS_URL` | ✅ 是 | - | Redis 连接串 |
| `SECRET_KEY` | ✅ (生产) | - | 应用密钥（≥32字符） |
| `ENVIRONMENT` | 否 | `development` | 运行环境：`development` 或 `production` |

## 数据库配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | ✅ | - | 格式：`postgresql://user:pass@host:port/db` |
| `DATABASE_POOL_SIZE` | 否 | 5 | 连接池大小 |
| `DATABASE_MAX_OVERFLOW` | 否 | 10 | 连接池溢出数量 |

## Redis 配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `REDIS_URL` | ✅ | - | 格式：`redis://host:port/db` |
| `DRAMATIQ_BROKER_URL` | 否 | - | Dramatiq Broker URL（默认使用 REDIS_URL） |

## API 服务配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `API_HOST` | 否 | `0.0.0.0` | API 监听地址 |
| `API_PORT` | 否 | `8000` | API 监听端口 |
| `API_WORKERS` | 否 | 1 | Worker 进程数 |

## 日志配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `LOG_LEVEL` | 否 | `INFO` | 日志级别：DEBUG, INFO, WARNING, ERROR |
| `LOG_FILE` | 否 | - | 日志文件路径 |

## 调度器配置

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `SCHEDULER_ENABLED` | 否 | `true` | 是否启用调度器 |
| `SCHEDULER_INTERVAL` | 否 | 60 | 调度检查间隔（秒） |

## Docker Compose 专用

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `POSTGRES_USER` | ✅ | - | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | ✅ | - | PostgreSQL 密码 |
| `POSTGRES_DB` | 否 | `cyberpulse` | PostgreSQL 数据库名 |

---

## 连接串格式

### DATABASE_URL

```
postgresql://用户名:密码@主机:端口/数据库名
```

示例：
```
postgresql://cyberpulse:password@localhost:5432/cyberpulse
postgresql://cyberpulse:password@postgres:5432/cyberpulse  # Docker 内部
```

### REDIS_URL

```
redis://主机:端口/数据库编号
```

示例：
```
redis://localhost:6379/0
redis://redis:6379/0  # Docker 内部
```

---

## 配置文件示例

### 开发环境 (.env)

```bash
# 数据库
DATABASE_URL=postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse
REDIS_URL=redis://localhost:6379/0

# 环境
ENVIRONMENT=development

# 日志
LOG_LEVEL=DEBUG
```

### 生产环境 (.env)

```bash
# 数据库（使用强密码）
DATABASE_URL=postgresql://cyberpulse:StrongPassword123!@localhost:5432/cyberpulse
REDIS_URL=redis://localhost:6379/0

# 安全（必需）
SECRET_KEY=your_64_character_hex_string_generated_by_secrets_token_hex_32
ENVIRONMENT=production

# 日志
LOG_LEVEL=INFO
LOG_FILE=/var/log/cyberpulse/cyberpulse.log

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### Docker Compose (.env)

```bash
# PostgreSQL（必需）
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=YourStrongPassword123!

# 应用（必需）
SECRET_KEY=your_64_character_hex_string_here
ENVIRONMENT=production

# 日志
LOG_LEVEL=INFO
```

---

## 生成 SECRET_KEY

```bash
# Python
python -c "import secrets; print(secrets.token_hex(32))"

# OpenSSL
openssl rand -hex 32

# /dev/urandom
head -c 32 /dev/urandom | xxd -p -c 32
```

---

## 环境变量优先级

配置加载顺序（后者覆盖前者）：

1. 默认值
2. 配置文件
3. 环境变量
4. 命令行参数