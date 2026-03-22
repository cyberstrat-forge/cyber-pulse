# 备份与恢复指南

本指南涵盖 Cyber Pulse 的数据备份策略和恢复流程。

## 目录

- [备份策略](#备份策略)
- [数据库备份](#数据库备份)
- [配置备份](#配置备份)
- [恢复流程](#恢复流程)
- [自动化备份](#自动化备份)
- [最佳实践](#最佳实践)

---

## 备份策略

### 数据分类

| 数据类型 | 重要性 | 备份频率 | 保留期 |
|----------|--------|----------|--------|
| 数据库 | 高 | 每日 | 30 天 |
| 配置文件 | 高 | 变更时 | 90 天 |
| 日志文件 | 中 | 每周 | 14 天 |
| 情报源配置 | 高 | 变更时 | 90 天 |

### 备份方式

| 方式 | 适用场景 | RTO | RPO |
|------|----------|-----|-----|
| pg_dump | 小中型部署 | 1-2 小时 | 24 小时 |
| WAL 归档 | 大型部署 | 15-30 分钟 | 5 分钟 |
| 快照备份 | 云环境 | 5-15 分钟 | 1 小时 |

---

## 数据库备份

### pg_dump 备份（推荐）

**手动备份**：

```bash
# 完整备份
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# 压缩备份
pg_dump $DATABASE_URL | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# 仅结构备份
pg_dump --schema-only $DATABASE_URL > schema.sql

# 仅数据备份
pg_dump --data-only $DATABASE_URL > data.sql
```

**自定义格式备份（推荐）**：

```bash
# 自定义格式（支持并行恢复）
pg_dump -Fc $DATABASE_URL > backup_$(date +%Y%m%d).dump

# 并行备份（加速大数据库）
pg_dump -Fc -j 4 $DATABASE_URL > backup_$(date +%Y%m%d).dump
```

### Docker 环境备份

```bash
# 导出数据库容器数据
docker-compose exec postgres pg_dump -U cyberpulse cyberpulse > backup.sql

# 或者使用 docker exec
docker exec cyberpulse-postgres pg_dump -U cyberpulse cyberpulse > backup.sql
```

### 增量备份（WAL 归档）

**配置 WAL 归档**：

```bash
# postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'cp %p /backup/wal/%f'
```

**使用 pgBackRest**（推荐用于生产）：

```bash
# 安装
apt-get install pgbackrest

# 配置 /etc/pgbackrest/pgbackrest.conf
[global]
repo1-path=/backup/pgbackrest
repo1-retention-full=2

[main]
pg1-path=/var/lib/postgresql/15/main

# 创建备份
pgbackrest --type=full --stanza=main backup
pgbackrest --type=incr --stanza=main backup
```

---

## 配置备份

### 需要备份的配置

```bash
# 环境变量配置
deploy/.env

# Docker Compose 配置
deploy/docker-compose.yml

# Systemd 服务文件
/etc/systemd/system/cyberpulse-*.service

# Nginx 配置
/etc/nginx/sites-available/cyberpulse

# 自定义配置
/etc/cyberpulse/
```

### 配置备份脚本

```bash
#!/bin/bash
# backup-config.sh

BACKUP_DIR="/backup/config"
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR

# 备份环境配置
cp deploy/.env $BACKUP_DIR/env.$DATE

# 备份 Docker Compose
cp deploy/docker-compose.yml $BACKUP_DIR/docker-compose.$DATE.yml

# 备份 Systemd 服务
cp /etc/systemd/system/cyberpulse-*.service $BACKUP_DIR/

# 备份 Nginx 配置
cp /etc/nginx/sites-available/cyberpulse $BACKUP_DIR/nginx.$DATE.conf

# 压缩
tar -czf $BACKUP_DIR/config_$DATE.tar.gz -C $BACKUP_DIR .

# 清理旧备份（保留 90 天）
find $BACKUP_DIR -name "*.tar.gz" -mtime +90 -delete

echo "Config backup completed: $BACKUP_DIR/config_$DATE.tar.gz"
```

---

## 恢复流程

### 数据库恢复

**从 SQL 文件恢复**：

```bash
# 删除现有数据库（谨慎操作）
dropdb cyberpulse

# 创建新数据库
createdb cyberpulse

# 恢复数据
psql $DATABASE_URL < backup_20260322.sql
```

**从自定义格式恢复**：

```bash
# 恢复整个数据库
pg_restore -d cyberpulse backup_20260322.dump

# 并行恢复（加速）
pg_restore -j 4 -d cyberpulse backup_20260322.dump

# 仅恢复特定表
pg_restore -t sources -d cyberpulse backup_20260322.dump
```

**Docker 环境恢复**：

```bash
# 停止服务
docker-compose stop api worker scheduler

# 恢复数据库
cat backup.sql | docker-compose exec -T postgres psql -U cyberpulse cyberpulse

# 重启服务
docker-compose start api worker scheduler
```

### 时间点恢复（PITR）

适用于 WAL 归档配置：

```bash
# 恢复到指定时间点
pg_restore --target-time="2026-03-22 10:00:00" -d cyberpulse backup.dump

# 恢复到指定事务
pg_restore --target-xid="12345" -d cyberpulse backup.dump
```

### 配置恢复

```bash
# 解压配置备份
tar -xzf config_20260322.tar.gz -C /tmp

# 恢复环境变量
cp /tmp/env.20260322 deploy/.env

# 恢复 Docker Compose
cp /tmp/docker-compose.20260322.yml deploy/docker-compose.yml

# 恢复 Systemd 服务
cp /tmp/cyberpulse-*.service /etc/systemd/system/
systemctl daemon-reload
```

---

## 自动化备份

### Cron 定时备份

```bash
# 编辑 crontab
crontab -e

# 添加定时任务
# 每天凌晨 2 点备份数据库
0 2 * * * pg_dump -Fc $DATABASE_URL > /backup/db/cyberpulse_$(date +\%Y\%m\%d).dump

# 每周日凌晨 3 点清理旧备份
0 3 * * 0 find /backup/db -name "*.dump" -mtime +30 -delete

# 每周一凌晨 4 点备份配置
0 4 * * 1 /opt/cyber-pulse/scripts/backup-config.sh
```

### 备份脚本

创建 `/opt/cyber-pulse/scripts/backup.sh`：

```bash
#!/bin/bash
# Cyber Pulse 自动备份脚本

set -e

# 配置
BACKUP_DIR="/backup/cyberpulse"
DB_URL="${DATABASE_URL}"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# 创建备份目录
mkdir -p $BACKUP_DIR/{db,config}

echo "[$(date)] Starting backup..."

# 数据库备份
echo "Backing up database..."
pg_dump -Fc $DB_URL > $BACKUP_DIR/db/cyberpulse_$DATE.dump

# 配置备份
echo "Backing up config..."
tar -czf $BACKUP_DIR/config/config_$DATE.tar.gz \
    deploy/.env \
    deploy/docker-compose.yml \
    /etc/systemd/system/cyberpulse-*.service 2>/dev/null || true

# 清理旧备份
echo "Cleaning old backups..."
find $BACKUP_DIR -name "*.dump" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

# 计算备份大小
BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
echo "[$(date)] Backup completed. Total size: $BACKUP_SIZE"

# 可选：上传到远程存储
# aws s3 sync $BACKUP_DIR s3://your-bucket/cyberpulse-backup/
```

### 验证备份

```bash
#!/bin/bash
# 验证备份完整性

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

echo "Validating backup: $BACKUP_FILE"

# 检查文件大小
SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE")
if [ $SIZE -lt 1000 ]; then
    echo "ERROR: Backup file too small ($SIZE bytes)"
    exit 1
fi

# 验证 pg_dump 格式
if [[ $BACKUP_FILE == *.dump ]]; then
    pg_restore --list $BACKUP_FILE > /dev/null
    if [ $? -eq 0 ]; then
        echo "Backup is valid (PostgreSQL custom format)"
    else
        echo "ERROR: Invalid backup format"
        exit 1
    fi
fi

# 验证 SQL 格式
if [[ $BACKUP_FILE == *.sql ]]; then
    if grep -q "PostgreSQL database dump" $BACKUP_FILE; then
        echo "Backup is valid (SQL format)"
    else
        echo "ERROR: Invalid SQL backup"
        exit 1
    fi
fi

echo "Backup validation passed"
```

---

## 最佳实践

### 备份策略

1. **3-2-1 原则**
   - 3 份副本
   - 2 种存储介质
   - 1 份异地备份

2. **定期验证**
   - 每月测试恢复流程
   - 验证备份完整性
   - 记录恢复时间

3. **监控告警**
   - 监控备份任务状态
   - 备份失败发送告警
   - 监控存储空间

### 恢复测试清单

```bash
# 恢复测试检查项
- [ ] 备份文件存在且完整
- [ ] 数据库可以成功恢复
- [ ] API 服务正常启动
- [ ] 健康检查通过
- [ ] 数据完整性验证（记录数一致）
- [ ] API 认证正常工作
- [ ] 定时任务正常运行
```

### 灾难恢复流程

1. **评估影响**
   - 确定数据丢失范围
   - 确定恢复时间目标

2. **准备恢复环境**
   - 部署新的服务器/容器
   - 安装依赖软件

3. **恢复数据**
   - 恢复数据库
   - 恢复配置文件
   - 恢复环境变量

4. **验证系统**
   - 运行健康检查
   - 验证数据完整性
   - 测试关键功能

5. **恢复服务**
   - 重启所有服务
   - 监控系统状态
   - 通知相关人员