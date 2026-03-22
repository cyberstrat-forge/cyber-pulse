# 故障排查手册

本手册涵盖 Cyber Pulse 常见问题的诊断与解决方法。

## 目录

- [诊断工具](#诊断工具)
- [服务启动问题](#服务启动问题)
- [数据库问题](#数据库问题)
- [Redis 问题](#redis-问题)
- [API 问题](#api-问题)
- [采集任务问题](#采集任务问题)
- [性能问题](#性能问题)
- [日志分析](#日志分析)

---

## 诊断工具

### 系统诊断命令

```bash
# 全面系统诊断
cyber-pulse diagnose system

# 情报源诊断
cyber-pulse diagnose sources

# 错误分析
cyber-pulse diagnose errors --since 24h
```

### 健康检查

```bash
# API 健康检查
curl http://localhost:8000/health

# 预期响应
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

### 日志查看

```bash
# 实时日志
cyber-pulse log tail -f

# 错误日志
cyber-pulse log errors --since 1h

# 搜索日志
cyber-pulse log search "timeout"
```

---

## 服务启动问题

### 问题：服务无法启动

**症状**：
- Docker 容器频繁重启
- Systemd 服务启动失败

**诊断步骤**：

```bash
# Docker 部署
docker-compose logs api

# 手动部署
journalctl -u cyberpulse-api -n 100
```

**常见原因与解决**：

| 错误信息 | 原因 | 解决方法 |
|----------|------|----------|
| `SECRET_KEY is set to the default value` | 生产环境使用默认密钥 | 设置 SECRET_KEY 环境变量 |
| `connection refused` | 数据库/Redis 未就绪 | 检查依赖服务状态 |
| `permission denied` | 文件权限问题 | 检查目录权限 |

### 问题：SECRET_KEY 验证失败

**错误信息**：
```
SECURITY ERROR: secret_key is set to the default value in production!
```

**解决方法**：

```bash
# 生成安全密钥
python -c "import secrets; print(secrets.token_hex(32))"

# 设置环境变量
export SECRET_KEY="生成的64字符十六进制字符串"

# 或在 .env 文件中设置
echo "SECRET_KEY=your_key_here" >> deploy/.env
```

---

## 数据库问题

### 问题：数据库连接失败

**症状**：
- 健康检查返回 `database: disconnected`
- API 返回 500 错误

**诊断步骤**：

```bash
# 检查 PostgreSQL 状态
docker-compose ps postgres
# 或
systemctl status postgresql

# 测试数据库连接
psql $DATABASE_URL -c "SELECT 1"

# 检查连接串格式
echo $DATABASE_URL
```

**常见原因与解决**：

| 原因 | 解决方法 |
|------|----------|
| PostgreSQL 未启动 | `systemctl start postgresql` |
| 连接串格式错误 | 检查 `DATABASE_URL` 格式 |
| 用户名/密码错误 | 验证凭据是否正确 |
| 网络不通 | 检查防火墙和网络配置 |
| 数据库不存在 | `createdb cyberpulse` |

**连接串格式**：

```
postgresql://用户名:密码@主机:端口/数据库名
```

### 问题：数据库迁移失败

**症状**：
- `alembic upgrade head` 报错
- 表结构不一致

**诊断步骤**：

```bash
# 检查当前迁移版本
alembic current

# 检查迁移历史
alembic history

# 查看待执行迁移
alembic show head
```

**解决方法**：

```bash
# 回退到上一版本
alembic downgrade -1

# 重新执行迁移
alembic upgrade head

# 强制标记当前版本（谨慎使用）
alembic stamp head
```

### 问题：数据库性能下降

**症状**：
- API 响应缓慢
- 查询超时

**诊断步骤**：

```bash
# 检查连接数
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"

# 检查慢查询
psql $DATABASE_URL -c "SELECT query, state, duration FROM pg_stat_activity WHERE state = 'active';"

# 检查表大小
psql $DATABASE_URL -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;"
```

**解决方法**：

```bash
# 分析表（更新统计信息）
psql $DATABASE_URL -c "ANALYZE;"

# 重建索引
psql $DATABASE_URL -c "REINDEX DATABASE cyberpulse;"

# 清理旧数据
cyber-pulse diagnose errors --since 30d  # 检查数据量
```

---

## Redis 问题

### 问题：Redis 连接失败

**症状**：
- 任务队列不工作
- 健康检查返回 `redis: disconnected`

**诊断步骤**：

```bash
# 检查 Redis 状态
docker-compose ps redis
# 或
systemctl status redis

# 测试 Redis 连接
redis-cli ping
# 预期响应：PONG

# 检查连接串
echo $REDIS_URL
```

**常见原因与解决**：

| 原因 | 解决方法 |
|------|----------|
| Redis 未启动 | `systemctl start redis` |
| 连接串格式错误 | 检查 `REDIS_URL` 格式 |
| 密码错误 | 验证 Redis 密码 |
| 内存不足 | 检查 Redis 内存使用 |

### 问题：任务队列阻塞

**症状**：
- 采集任务不执行
- Worker 进程卡住

**诊断步骤**：

```bash
# 检查队列状态
redis-cli LLEN dramatiq:default

# 检查 Worker 进程
ps aux | grep dramatiq

# 查看 Worker 日志
docker-compose logs worker
```

**解决方法**：

```bash
# 重启 Worker
docker-compose restart worker
# 或
systemctl restart cyberpulse-worker

# 清空阻塞的任务（谨慎使用）
redis-cli DEL dramatiq:default
```

---

## API 问题

### 问题：401 Unauthorized

**症状**：
- API 返回 401 错误
- 认证失败

**诊断步骤**：

```bash
# 验证 API Key 格式
echo $API_KEY
# 应为：cp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 测试认证
curl -H "Authorization: Bearer $API_KEY" \
     http://localhost:8000/api/v1/contents
```

**常见原因与解决**：

| 原因 | 解决方法 |
|------|----------|
| API Key 缺失 | 添加 `Authorization` 请求头 |
| API Key 格式错误 | 使用完整 API Key |
| 客户端已禁用 | `cyber-pulse client enable cli_xxx` |
| 客户端已过期 | 创建新客户端 |

### 问题：403 Forbidden

**症状**：
- 访问 `/clients` 端点返回 403

**原因**：v1.2.0 后 `/clients` 端点需要 admin 权限

**解决方法**：

```bash
# 创建管理员客户端
cyber-pulse client create "admin"

# 使用管理员 API Key 访问
curl -H "Authorization: Bearer cp_live_admin_key" \
     http://localhost:8000/api/v1/clients
```

### 问题：404 Not Found

**症状**：
- 访问 `/docs` 返回 404

**原因**：生产环境自动禁用 API 文档

**解决方法**：

这是预期行为。如需启用文档（仅限开发环境）：

```bash
export ENVIRONMENT=development
```

### 问题：429 Rate Limited

**症状**：
- API 返回 429 错误

**解决方法**：

```python
# 实现指数退避重试
import time

def request_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url)
        if response.status_code != 429:
            return response
        wait_time = 2 ** attempt  # 1, 2, 4 秒
        time.sleep(wait_time)
    return response
```

---

## 采集任务问题

### 问题：任务执行失败

**症状**：
- 任务状态为 `failed`
- 内容未更新

**诊断步骤**：

```bash
# 查看失败任务
cyber-pulse job list --status failed

# 查看任务详情
cyber-pulse job status job_xxx

# 查看相关错误日志
cyber-pulse log errors --source src_xxx
```

**常见原因与解决**：

| 原因 | 解决方法 |
|------|----------|
| 情报源 URL 不可达 | `cyber-pulse source test src_xxx` |
| RSS 格式错误 | 检查 RSS 源格式 |
| 超时 | 增加超时时间配置 |
| SSRF 防护拦截 | URL 访问了私有地址 |

### 问题：情报源连接失败

**症状**：
- `source test` 失败
- 采集无数据

**诊断步骤**：

```bash
# 测试情报源
cyber-pulse source test src_xxx --timeout 60

# 手动运行采集
cyber-pulse job run src_xxx

# 查看错误日志
cyber-pulse diagnose errors --source src_xxx
```

**SSRF 防护相关错误**：

```
SSRFError: Access to localhost is not allowed
SSRFError: Access to private IP address is not allowed
```

这是安全防护，说明情报源 URL 尝试访问内部服务。请使用公开可访问的 URL。

### 问题：内容质量低

**症状**：
- `quality_score` 很低
- 内容为空或格式错误

**诊断步骤**：

```bash
# 查看被拒绝的 Item
cyber-pulse diagnose errors --since 7d

# 查看源统计
cyber-pulse source stats --source-id src_xxx
```

**常见原因**：

- RSS 源缺少 `content` 或 `description`
- 正文提取失败（Web 源）
- 元数据不完整

---

## 性能问题

### 问题：API 响应缓慢

**诊断步骤**：

```bash
# 检查数据库性能
psql $DATABASE_URL -c "SELECT count(*) FROM contents;"

# 检查 Redis 内存
redis-cli INFO memory

# 检查系统资源
docker stats
```

**解决方法**：

1. **数据库优化**
   ```bash
   # 创建索引
   psql $DATABASE_URL -c "CREATE INDEX IF NOT EXISTS idx_contents_fetched_at ON contents(fetched_at);"

   # 分析表
   psql $DATABASE_URL -c "ANALYZE;"
   ```

2. **减少每次请求的数据量**
   ```bash
   # 使用较小的 limit
   curl "https://api.example.com/api/v1/contents?limit=20"
   ```

### 问题：内存使用过高

**诊断步骤**：

```bash
# 检查进程内存
ps aux --sort=-%mem | head -10

# 检查 Redis 内存
redis-cli INFO memory | grep used_memory_human
```

**解决方法**：

1. 减少 Worker 进程数
   ```bash
   # docker-compose.yml
   command: dramatiq cyberpulse.tasks --processes 1 --threads 2
   ```

2. 设置 Redis 内存限制
   ```bash
   # redis.conf
   maxmemory 1gb
   maxmemory-policy allkeys-lru
   ```

---

## 日志分析

### 关键日志模式

| 日志内容 | 含义 | 处理 |
|----------|------|------|
| `Connection refused` | 服务连接失败 | 检查目标服务 |
| `Timeout` | 请求超时 | 增加超时或检查网络 |
| `SSRFError` | SSRF 防护触发 | 使用公开 URL |
| `IntegrityError` | 数据库约束冲突 | 检查重复数据 |
| `Rate limited` | 请求被限流 | 降低请求频率 |

### 日志导出与分析

```bash
# 导出日志
cyber-pulse log export --output /tmp/logs.txt --since 7d

# 统计错误类型
grep "ERROR" /tmp/logs.txt | cut -d'-' -f4 | sort | uniq -c | sort -rn

# 按时间分析错误分布
grep "ERROR" /tmp/logs.txt | cut -d' ' -f1-2 | cut -d':' -f1 | uniq -c
```

---

## 联系支持

如果以上方法无法解决问题：

1. 收集诊断信息
   ```bash
   cyber-pulse diagnose system > diagnostic.txt
   cyber-pulse log export --output logs.txt --since 24h
   ```

2. 在 GitHub 创建 Issue：https://github.com/cyberstrat-forge/cyber-pulse/issues

3. 提供以下信息：
   - 系统版本：`cyber-pulse version`
   - 部署方式：Docker / 手动
   - 问题描述和复现步骤
   - 诊断日志