# 升级与迁移指南

本指南涵盖 Cyber Pulse 版本升级和数据迁移流程。

## 目录

- [快速升级](#快速升级)
- [升级前准备](#升级前准备)
- [手动升级](#手动升级)
- [数据库迁移](#数据库迁移)
- [回滚操作](#回滚操作)
- [兼容性说明](#兼容性说明)

---

## 快速升级

### 使用管理脚本（推荐）

```bash
# 检查是否有更新
./scripts/cyber-pulse.sh check-update

# 执行升级（自动快照 + 失败回滚）
./scripts/cyber-pulse.sh upgrade
```

升级命令自动完成：
1. 创建快照备份
2. 拉取最新代码
3. 拉取最新镜像
4. 运行数据库迁移
5. 重启服务
6. 验证升级结果

如果升级失败，系统自动回滚到快照状态。

---

## 升级前准备

### 检查清单

- [ ] 阅读目标版本的 CHANGELOG
- [ ] 备份数据库
- [ ] 备份配置文件
- [ ] 确认兼容性要求
- [ ] 准备回滚计划

### 备份

```bash
# 备份数据库
pg_dump -Fc $DATABASE_URL > backup_before_upgrade_$(date +%Y%m%d).dump

# 备份配置
cp deploy/.env deploy/.env.backup
cp deploy/docker-compose.yml deploy/docker-compose.yml.backup
```

### 查看当前版本

```bash
# 查看安装版本
cyberpulse version

# 或查看 git 标签
git describe --tags
```

---

## 手动升级

如果需要手动控制升级过程：

```bash
# 1. 创建快照
./scripts/cyber-pulse.sh snapshot

# 2. 检查更新
./scripts/cyber-pulse.sh check-update

# 3. 停止服务
./scripts/cyber-pulse.sh stop

# 4. 拉取最新代码
git fetch --tags
git checkout v1.3.0  # 替换为目标版本

# 5. 启动服务（自动运行迁移）
./scripts/cyber-pulse.sh start

# 6. 验证
./scripts/cyber-pulse.sh status
curl http://localhost:8000/health
```

### 升级到指定版本

```bash
# 查看可用版本
git tag

# 切换到指定版本
git checkout v1.2.0

# 重新部署
./scripts/cyber-pulse.sh deploy
```

---

## 数据库迁移

### Alembic 迁移

**查看迁移状态**：

```bash
# 查看当前版本
alembic current

# 查看待执行迁移
alembic show head

# 查看迁移历史
alembic history --verbose
```

**执行迁移**：

```bash
# 升级到最新版本
alembic upgrade head

# 升级到指定版本
alembic upgrade <revision>

# 升级一步
alembic upgrade +1
```

**回退迁移**：

```bash
# 回退一步
alembic downgrade -1

# 回退到指定版本
alembic downgrade <revision>

# 回退所有迁移（危险操作）
alembic downgrade base
```

### 迁移故障排除

**问题：迁移冲突**

```bash
# 错误信息
# "Can't locate revision identified by 'xxx'"

# 解决方法
alembic stamp head  # 强制标记当前版本
alembic upgrade head
```

**问题：迁移卡住**

```bash
# 检查数据库锁
psql $DATABASE_URL -c "SELECT * FROM pg_locks WHERE NOT granted;"

# 终止阻塞的进程
psql $DATABASE_URL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%alembic%';"
```

---

## 配置迁移

### v1.1.x → v1.2.0 配置变更

**新增必需配置**：

```bash
# 必须设置 SECRET_KEY（生产环境）
SECRET_KEY=your_64_char_hex_string

# 必须设置 ENVIRONMENT（生产环境）
ENVIRONMENT=production
```

**Docker Compose 变更**：

```yaml
# v1.2.0 要求显式设置环境变量
# 之前版本有默认值，现在必须设置

environment:
  POSTGRES_USER: ${POSTGRES_USER}      # 必须设置
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # 必须设置
```

**创建 .env 文件**：

```bash
# deploy/.env
POSTGRES_USER=cyberpulse
POSTGRES_PASSWORD=your_secure_password
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
ENVIRONMENT=production
```

### 配置迁移脚本

```bash
#!/bin/bash
# 从旧版本迁移配置

OLD_ENV="/opt/cyber-pulse-old/deploy/.env"
NEW_ENV="/opt/cyber-pulse/deploy/.env"

# 复制现有配置
cp $OLD_ENV $NEW_ENV

# 添加新必需配置
if ! grep -q "SECRET_KEY" $NEW_ENV; then
    echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> $NEW_ENV
fi

if ! grep -q "ENVIRONMENT" $NEW_ENV; then
    echo "ENVIRONMENT=production" >> $NEW_ENV
fi

echo "Configuration migrated successfully"
```

---

## 回滚操作

### 使用快照回滚（推荐）

```bash
# 列出可用快照
./scripts/cyber-pulse.sh snapshot --list

# 恢复到指定快照
./scripts/cyber-pulse.sh restore <snapshot-file>
```

### 快速回滚

```bash
# 停止服务
docker-compose down
# 或
sudo systemctl stop cyberpulse-api cyberpulse-worker cyberpulse-scheduler

# 切换到旧版本
git checkout v1.1.0  # 替换为之前版本

# 恢复数据库
dropdb cyberpulse
createdb cyberpulse
pg_restore -d cyberpulse backup_before_upgrade.dump

# 启动服务
docker-compose up -d
# 或
sudo systemctl start cyberpulse-api cyberpulse-worker cyberpulse-scheduler
```

### 部分回滚（仅代码）

如果数据库结构兼容：

```bash
# 仅回滚代码
git checkout v1.1.0

# 重启服务
docker-compose restart api worker scheduler
```

### 数据库回滚

```bash
# 回退到之前版本的数据库迁移
alembic downgrade <previous_revision>

# 或恢复备份
dropdb cyberpulse
createdb cyberpulse
pg_restore -d cyberpulse backup_before_upgrade.dump
```

---

## 兼容性说明

### 版本兼容矩阵

| 版本 | Python | PostgreSQL | Redis | Alembic |
|------|--------|------------|-------|---------|
| v1.2.0 | 3.11+ | 15+ | 7+ | 001-008 |
| v1.1.0 | 3.11+ | 15+ | 7+ | 001-007 |
| v1.0.0 | 3.11+ | 15+ | 7+ | 001-006 |

### Breaking Changes

#### v1.2.0

| 变更 | 影响 | 迁移操作 |
|------|------|----------|
| SECRET_KEY 强制验证 | 生产环境启动检查 | 设置 SECRET_KEY 环境变量 |
| Docker 默认密码移除 | 现有部署需配置 | 创建 .env 文件设置密码 |
| /clients 端点认证 | 需 admin 权限 | 创建 admin 客户端 |
| API 文档生产禁用 | /docs 返回 404 | 正常，安全特性 |

#### v1.1.0

| 变更 | 影响 | 迁移操作 |
|------|------|----------|
| DRAMATIQ_BROKER_URL | 任务队列配置 | 添加环境变量 |

### API 兼容性

API 端点保持向后兼容：

| 版本 | API 版本 | 兼容性 |
|------|----------|--------|
| v1.2.0 | v1 | 向后兼容 v1.0.0+ |
| v1.1.0 | v1 | 向后兼容 v1.0.0+ |
| v1.0.0 | v1 | 基础版本 |

---

## 升级后验证

### 功能验证

```bash
# 健康检查
curl http://localhost:8000/health

# API 测试
curl -H "Authorization: Bearer $API_KEY" \
     http://localhost:8000/api/v1/contents?limit=1

# 系统诊断
cyberpulse diagnose system

# 数据库检查
psql $DATABASE_URL -c "SELECT count(*) FROM sources;"
psql $DATABASE_URL -c "SELECT count(*) FROM contents;"
```

### 版本确认

```bash
# 确认版本
cyberpulse version

# 确认数据库迁移版本
alembic current

# 确认服务状态
docker-compose ps
# 或
systemctl status cyberpulse-api
```

### 监控验证

```bash
# 检查错误日志
cyberpulse log errors --since 1h

# 检查服务指标
curl http://localhost:8000/health
```

---

## 常见升级问题

### 问题：数据库迁移失败

**症状**：
```
alembic upgrade head
ERROR: relation "xxx" already exists
```

**解决**：
```bash
# 检查当前版本
alembic current

# 强制标记版本
alembic stamp head
```

### 问题：依赖版本冲突

**症状**：
```
ERROR: Cannot install package xxx
```

**解决**：
```bash
# 清理并重新安装
pip uninstall -y cyber-pulse
pip cache purge
pip install -e ".[dev]"
```

### 问题：服务启动失败

**症状**：
```
SECURITY ERROR: secret_key is set to the default value
```

**解决**：
```bash
# 设置 SECRET_KEY
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### 问题：API Key 不工作

**症状**：
```
401 Unauthorized
```

**解决**：
```bash
# 检查客户端状态
cyberpulse client list

# 重新创建客户端
cyberpulse client create "test"
```