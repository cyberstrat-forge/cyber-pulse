# 快速入门教程

本教程帮助您在 10 分钟内完成 Cyber Pulse 的部署和基本使用。

## 目录

- [环境要求](#环境要求)
- [快速部署](#快速部署)
- [基本使用](#基本使用)
- [添加情报源](#添加情报源)
- [验证采集](#验证采集)
- [使用 API](#使用-api)
- [下一步](#下一步)

---

## 环境要求

### 必需软件

| 软件 | 版本要求 | 说明 |
|------|----------|------|
| Docker | 24+ | 容器运行环境 |
| git | 任意版本 | 代码获取 |

> **提示**：数据库、Redis 等服务均由 Docker 容器提供，无需单独安装。

### 系统资源

- 4GB+ 可用内存
- 10GB+ 可用磁盘空间

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
# 执行部署（自动生成配置、启动服务）
./scripts/cyber-pulse.sh deploy
```

部署过程将自动完成：
1. 检查 Docker 环境
2. 生成安全配置（数据库密码、密钥等）
3. 拉取镜像并启动服务
4. 初始化数据库

### 第三步：验证

```bash
# 检查服务状态
./scripts/cyber-pulse.sh status

# 健康检查
curl http://localhost:8000/health

# 预期响应
# {"status":"healthy","database":"connected","redis":"connected"}
```

---

## 基本使用

### 管理命令

```bash
# 查看帮助
./scripts/cyber-pulse.sh --help

# 查看服务状态
./scripts/cyber-pulse.sh status

# 查看日志
./scripts/cyber-pulse.sh logs api

# 重启服务
./scripts/cyber-pulse.sh restart
```

### 创建 API 客户端

```bash
# 进入 API 容器
docker compose exec api bash

# 创建客户端
cyberpulse client create "admin" --description "管理员账户"

# 记录输出的 API Key
# Client ID: cli_xxxxxxxxxxxxxxxx
# API Key: cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 保存 API Key

```bash
# 在宿主机设置环境变量
export API_KEY="cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## 添加情报源

### 添加 RSS 源

```bash
# 添加安全客 RSS 源
docker compose exec api cyberpulse source add "安全客" rss \
  --tier T1 \
  --url "https://www.anquanke.com/rss.xml" \
  --schedule "0 */6 * * *"

# 记录输出的 Source ID
# Source ID: src_xxxxxxxx
```

### 添加更多源（可选）

```bash
# Hacker News
docker compose exec api cyberpulse source add "Hacker News" rss \
  --tier T0 \
  --url "https://hnrss.org/frontpage" \
  --schedule "0 */2 * * *"

# FreeBuf
docker compose exec api cyberpulse source add "FreeBuf" rss \
  --tier T1 \
  --url "https://www.freebuf.com/feed" \
  --schedule "0 */4 * * *"
```

---

## 验证采集

### 手动触发采集

```bash
# 立即执行采集
docker compose exec api cyberpulse job run src_xxxxxxxx

# 查看任务状态
docker compose exec api cyberpulse job list --limit 5
```

### 检查采集结果

```bash
# 查看采集的内容
docker compose exec api cyberpulse content list --limit 10

# 查看源统计
docker compose exec api cyberpulse source stats

# 系统诊断
docker compose exec api cyberpulse diagnose system
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
- [x] 创建 API 客户端
- [x] 添加情报源
- [x] 验证数据采集
- [x] API 访问正常

### 推荐阅读

1. **[部署指南](./deployment-guide.md)** - 多环境部署详解
2. **[API 使用指南](./api-guide.md)** - 下游系统集成
3. **[备份与恢复](./backup-restore.md)** - 数据保护
4. **[升级迁移指南](./upgrade-guide.md)** - 版本升级

### 常用运维命令

```bash
./scripts/cyber-pulse.sh status     # 服务状态
./scripts/cyber-pulse.sh logs api   # 查看日志
./scripts/cyber-pulse.sh restart    # 重启服务
./scripts/cyber-pulse.sh stop       # 停止服务
./scripts/cyber-pulse.sh snapshot   # 创建快照
```

---

## 常见问题

### Q: 服务启动失败

```bash
# 检查日志
./scripts/cyber-pulse.sh logs

# 常见原因：
# 1. Docker 服务未启动
# 2. 端口 8000 被占用
# 3. 内存不足
```

### Q: 采集没有数据

```bash
# 检查情报源连接
docker compose exec api cyberpulse source test src_xxx

# 检查错误日志
docker compose exec api cyberpulse log errors --since 1h
```

### Q: API 返回 401

```bash
# 确认 API Key 格式正确
# 格式：cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 确认客户端未禁用
docker compose exec api cyberpulse client list
```

### Q: 如何更新

```bash
# 使用升级命令（自动快照 + 失败回滚）
./scripts/cyber-pulse.sh upgrade
```

---

恭喜！您已完成 Cyber Pulse 快速入门。