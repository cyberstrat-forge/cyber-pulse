# 快速入门教程

本教程帮助您在 15 分钟内完成 Cyber Pulse 的基本部署和使用。

## 目录

- [环境准备](#环境准备)
- [部署安装](#部署安装)
- [基础配置](#基础配置)
- [添加情报源](#添加情报源)
- [验证采集](#验证采集)
- [使用 API](#使用-api)
- [下一步](#下一步)

---

## 环境准备

### 系统要求

- Docker 24+ 和 Docker Compose 2.0+
- 4GB+ 可用内存
- 10GB+ 可用磁盘空间

### 验证 Docker

```bash
docker --version
docker-compose --version
```

---

## 部署安装

### 1. 下载项目

```bash
# 使用安装脚本（推荐）
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash

# 或手动克隆
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse
```

### 2. 配置环境变量

```bash
cd deploy

# 创建配置文件
cat > .env << EOF
# 数据库配置（请修改密码）
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=YourStrongPassword123!

# 安全配置
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENVIRONMENT=production

# 日志配置
LOG_LEVEL=INFO
EOF
```

### 3. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 等待服务就绪（约 30 秒）
docker-compose ps
```

### 4. 验证部署

```bash
# 健康检查
curl http://localhost:8000/health

# 预期响应
# {"status":"healthy","database":"connected","redis":"connected"}
```

---

## 基础配置

### 1. 创建管理员客户端

```bash
# 进入 API 容器
docker-compose exec api bash

# 在容器内执行
cyberpulse client create "admin" --description "管理员账户"

# 记录输出的 API Key
# Client ID: cli_xxxxxxxxxxxxxxxx
# API Key: cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. 保存 API Key

```bash
# 设置环境变量（在宿主机）
export API_KEY="cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## 添加情报源

### 添加 RSS 源

```bash
# 添加安全客 RSS 源
docker-compose exec api cyberpulse source add "安全客" rss \
  --tier T1 \
  --url "https://www.anquanke.com/rss.xml" \
  --schedule "0 */6 * * *"

# 记录输出的 Source ID
# Source ID: src_xxxxxxxx
```

### 添加更多源（可选）

```bash
# Hacker News
docker-compose exec api cyberpulse source add "Hacker News" rss \
  --tier T0 \
  --url "https://hnrss.org/frontpage" \
  --schedule "0 */2 * * *"

# FreeBuf
docker-compose exec api cyberpulse source add "FreeBuf" rss \
  --tier T1 \
  --url "https://www.freebuf.com/feed" \
  --schedule "0 */4 * * *"
```

---

## 验证采集

### 手动触发采集

```bash
# 立即执行一次采集
docker-compose exec api cyberpulse job run src_xxxxxxxx

# 查看任务状态
docker-compose exec api cyberpulse job list --limit 5
```

### 检查采集结果

```bash
# 查看采集的内容
docker-compose exec api cyberpulse content list --limit 10

# 查看源统计
docker-compose exec api cyberpulse source stats

# 系统诊断
docker-compose exec api cyberpulse diagnose system
```

---

## 使用 API

### 测试 API 访问

```bash
# 获取内容列表
curl -H "Authorization: Bearer $API_KEY" \
     "http://localhost:8000/api/v1/contents?limit=5"

# 获取情报源列表
curl -H "Authorization: Bearer $API_KEY" \
     "http://localhost:8000/api/v1/sources"
```

### Python 示例

```python
import requests

API_URL = "http://localhost:8000/api/v1"
API_KEY = "cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 获取内容列表
response = requests.get(
    f"{API_URL}/contents",
    headers={"Authorization": f"Bearer {API_KEY}"},
    params={"limit": 10}
)

for content in response.json()["data"]:
    print(f"{content['title']}: {content['url']}")
```

---

## 下一步

### 完成部署检查清单

- [x] 服务启动成功
- [x] 健康检查通过
- [x] 创建管理员客户端
- [x] 添加情报源
- [x] 验证数据采集
- [x] API 访问正常

### 推荐阅读

1. **[部署指南](./deployment-guide.md)** - 生产环境完整部署
2. **[API 使用指南](./api-guide.md)** - 下游系统集成
3. **[安全配置指南](./security-guide.md)** - 安全加固
4. **[故障排查手册](./troubleshooting.md)** - 问题诊断

### 常用运维命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f api

# 重启服务
docker-compose restart api

# 停止服务
docker-compose down

# 备份数据库
docker-compose exec postgres pg_dump -U cyberpulse cyberpulse > backup.sql
```

---

## 常见问题

### Q: 服务启动失败

```bash
# 检查日志
docker-compose logs api

# 常见原因：
# 1. SECRET_KEY 未设置
# 2. POSTGRES_PASSWORD 未设置
# 3. 端口冲突
```

### Q: 采集没有数据

```bash
# 检查情报源连接
docker-compose exec api cyberpulse source test src_xxx

# 检查错误日志
docker-compose exec api cyberpulse log errors --since 1h
```

### Q: API 返回 401

```bash
# 确认 API Key 格式正确
# 格式：cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 确认客户端未禁用
docker-compose exec api cyberpulse client list
```

### Q: 如何更新

```bash
# 拉取最新代码
git pull origin main

# 重新构建并启动
docker-compose up -d --build

# 运行数据库迁移
docker-compose exec api alembic upgrade head
```

---

恭喜！您已完成 Cyber Pulse 快速入门。