# 安全配置指南

本指南涵盖 Cyber Pulse 的安全配置要求，特别是 v1.2.0 版本后的安全加固。

## 目录

- [安全概述](#安全概述)
- [必需配置](#必需配置)
- [网络安全](#网络安全)
- [API 安全](#api-安全)
- [数据库安全](#数据库安全)
- [日志与审计](#日志与审计)
- [安全检查清单](#安全检查清单)

---

## 安全概述

### v1.2.0 安全更新

| 修复项 | 影响 | 配置要求 |
|--------|------|----------|
| /clients 端点认证 | 管理员权限验证 | 需要创建 admin 客户端 |
| SSRF 防护 | 防止内部服务访问 | 无需额外配置 |
| 生产环境 secret_key 验证 | 启动时强制检查 | 必须设置 SECRET_KEY |
| API 文档禁用 | 生产环境隐藏 | 设置 ENVIRONMENT=production |
| 默认密码移除 | Docker Compose 安全 | 必须设置 POSTGRES_PASSWORD |

---

## 必需配置

### 1. SECRET_KEY 配置

**要求**：生产环境必须设置强随机密钥（≥32 字符）

**生成方法**：

```bash
# Python 生成
python -c "import secrets; print(secrets.token_hex(32))"

# OpenSSL 生成
openssl rand -hex 32
```

**配置方式**：

```bash
# 环境变量
export SECRET_KEY="your_64_character_hex_string_here"

# Docker Compose (.env 文件)
SECRET_KEY=your_64_character_hex_string_here
```

**验证**：

```bash
# 启动服务时检查日志
# 如果 SECRET_KEY 为默认值，生产环境将拒绝启动
# 错误信息：SECURITY ERROR: secret_key is set to the default value in production!
```

### 2. 数据库密码

**要求**：禁止使用默认密码，必须设置强密码

**Docker Compose 配置**：

```bash
# deploy/.env
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=your_strong_password_here
```

**密码强度要求**：

- 最少 16 个字符
- 包含大小写字母、数字、特殊字符
- 禁止使用字典词汇

### 3. 环境标识

**要求**：生产环境必须设置 `ENVIRONMENT=production`

**效果**：

- 禁用 API 文档（`/docs`, `/redoc`）
- 启用 SECRET_KEY 验证
- 启用安全日志级别

```bash
export ENVIRONMENT=production
```

---

## 网络安全

### 端口暴露

**最小暴露原则**：

| 服务 | 端口 | 暴露建议 |
|------|------|----------|
| API | 8000 | 暴露（通过反向代理） |
| PostgreSQL | 5432 | 不暴露 |
| Redis | 6379 | 不暴露 |

**Docker Compose 配置**：

```yaml
# deploy/docker-compose.yml
services:
  postgres:
    # 不暴露端口到宿主机
    # ports:
    #   - "5432:5432"  # 注释掉

  redis:
    # 不暴露端口到宿主机
    # ports:
    #   - "6379:6379"  # 注释掉
```

### 防火墙规则

```bash
# 仅允许本地访问数据库
iptables -A INPUT -p tcp --dport 5432 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP

# 仅允许本地访问 Redis
iptables -A INPUT -p tcp --dport 6379 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP
```

### 反向代理配置

**Nginx 示例**：

```nginx
# 限制请求速率
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

server {
    listen 443 ssl http2;
    server_name api.cyberpulse.example.com;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 速率限制
    limit_req zone=api burst=20 nodelay;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTP 重定向 HTTPS
server {
    listen 80;
    server_name api.cyberpulse.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## API 安全

### API Key 管理

**创建客户端**：

```bash
# 创建管理员客户端（用于 /clients 端点管理）
cyberpulse client create "admin" --description "系统管理员"

# 创建下游系统客户端
cyberpulse client create "分析系统" --description "下游分析系统"
```

**权限说明**：

| 权限 | 说明 | 端点访问 |
|------|------|----------|
| read | 读取内容 | /contents, /sources |
| admin | 管理权限 | /clients（需要 admin） |

**最佳实践**：

1. 为每个下游系统创建独立客户端
2. 设置合理的过期时间
3. 定期轮换 API Key
4. 禁用不再使用的客户端

### API Key 保护

**禁止**：

- 将 API Key 提交到版本控制
- 在日志中记录完整 API Key
- 在 URL 参数中传递 API Key

**推荐**：

```bash
# 使用环境变量存储 API Key
export CYBERPULSE_API_KEY="cp_live_xxx"

# 在请求头中传递
curl -H "Authorization: Bearer $CYBERPULSE_API_KEY" \
     https://api.example.com/api/v1/contents
```

### 客户端端点保护

从 v1.2.0 开始，`/api/v1/clients` 端点需要 admin 权限：

```bash
# 创建 admin 客户端
cyberpulse client create "admin"

# 使用 admin API Key 访问 /clients
curl -H "Authorization: Bearer cp_live_admin_key" \
     https://api.example.com/api/v1/clients
```

---

## 数据库安全

### 连接加密

**PostgreSQL SSL 配置**：

```bash
# postgresql.conf
ssl = on
ssl_cert_file = '/etc/postgresql/ssl/server.crt'
ssl_key_file = '/etc/postgresql/ssl/server.key'

# 连接串
DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require
```

### 用户权限

**最小权限原则**：

```sql
-- 创建专用用户
CREATE USER cyberpulse WITH PASSWORD 'strong_password';

-- 授予必要权限
GRANT CONNECT ON DATABASE cyberpulse TO cyberpulse;
GRANT USAGE ON SCHEMA public TO cyberpulse;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cyberpulse;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cyberpulse;

-- 禁止超级用户权限
REVOKE SUPERUSER FROM cyberpulse;
```

### 连接池

**生产环境推荐配置**：

```bash
# 使用连接池（如 PgBouncer）
DATABASE_URL=postgresql://cyberpulse:password@pgbouncer:6432/cyberpulse
```

---

## 日志与审计

### 日志级别

**生产环境推荐**：

```bash
LOG_LEVEL=INFO
```

**调试模式**（仅用于排查问题）：

```bash
LOG_LEVEL=DEBUG
```

### 敏感信息保护

日志中自动脱敏以下信息：

- API Key（仅显示前 8 位）
- 数据库密码
- SECRET_KEY

### 审计日志

**关键操作记录**：

- 客户端创建/禁用/删除
- 情报源添加/修改/删除
- 认证失败

```bash
# 查看审计日志
cyberpulse log search "client create" --level INFO
cyberpulse log search "authentication failed" --level WARNING
```

---

## 安全检查清单

### 部署前检查

- [ ] `SECRET_KEY` 已设置为强随机值（≥32 字符）
- [ ] `POSTGRES_PASSWORD` 已设置为强密码
- [ ] `ENVIRONMENT` 设置为 `production`
- [ ] API 文档已禁用（访问 `/docs` 返回 404）
- [ ] 数据库端口未暴露公网
- [ ] Redis 端口未暴露公网
- [ ] 已配置 HTTPS
- [ ] 已创建管理员客户端

### 定期检查（每月）

- [ ] 审查活跃客户端列表
- [ ] 禁用不再使用的客户端
- [ ] 检查异常认证日志
- [ ] 验证备份完整性
- [ ] 检查安全更新

### API Key 管理

- [ ] 为每个下游系统创建独立客户端
- [ ] 设置合理的过期时间
- [ ] 定期轮换 API Key
- [ ] API Key 未存储在代码仓库中

---

## SSRF 防护说明

系统已内置 SSRF 防护，防止通过情报源配置访问内部服务：

### 防护机制

1. **URL Scheme 验证**：仅允许 `http` 和 `https`
2. **私有 IP 检测**：禁止访问私有 IP 地址
   - RFC 1918 私有地址（10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16）
   - Loopback 地址（127.0.0.0/8）
   - Link-local 地址（169.254.0.0/16，防止 AWS 元数据访问）
   - IPv6 私有地址
3. **DNS 解析验证**：检查解析后的 IP 是否为私有地址

### 测试 SSRF 防护

```bash
# 尝试添加访问内部服务的情报源（会被拒绝）
cyberpulse source add "test" rss --url "http://127.0.0.1:8080/feed.xml"
# 错误：Access to localhost is not allowed

cyberpulse source add "test" rss --url "http://10.0.0.1/feed.xml"
# 错误：Access to private IP address is not allowed
```

---

## 安全更新

订阅安全更新：

1. Watch GitHub 仓库：https://github.com/cyberstrat-forge/cyber-pulse
2. 关注 CHANGELOG.md 中的 Security 部分
3. 及时更新到最新版本