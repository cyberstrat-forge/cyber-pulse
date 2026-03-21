# cyber-pulse 验证系统使用指南

## 概述

验证系统用于确认 cyber-pulse 部署正确、功能完整，支持回归测试。

## 快速开始

### 1. 准备情报源

编辑 `sources.yaml`，添加实际可用的情报源：

```yaml
sources:
  - name: 安全客
    connector_type: rss
    config:
      feed_url: https://www.anquanke.com/vul/rss.xml
    tier: T2
```

### 2. 启动服务

```bash
docker-compose up -d
```

### 3. 运行验证

```bash
make verify
```

## 验证流程

### Level 1: 系统就绪

检查项：
- 数据库连接
- Redis 连接
- API 服务健康
- Worker 运行状态
- Scheduler 运行状态

### Level 2: 功能验证

检查项：
- API Client 管理（create/list/disable/enable）
- 情报源添加与连接测试
- 数据采集任务执行
- CLI 数据查询
- API 查询功能

## 命令参考

```bash
# 终端输出
make verify

# 生成 Markdown 报告
make verify-report

# 指定情报源清单
./scripts/verify.sh --sources custom-sources.yaml

# 保留测试情报源
./scripts/verify.sh --keep-sources

# 仅清理测试数据
./scripts/verify.sh --cleanup

# 显示帮助
./scripts/verify.sh --help
```

## 故障排查

### Level 1 失败

| 症状 | 可能原因 | 排查命令 |
|------|----------|----------|
| Database 连接失败 | PostgreSQL 未启动或配置错误 | `docker-compose logs postgres` |
| Redis 连接失败 | Redis 未启动 | `docker-compose logs redis` |
| Worker 未运行 | Worker 容器崩溃 | `docker-compose logs worker` |
| Scheduler 未运行 | Scheduler 容器崩溃 | `docker-compose logs scheduler` |

### Level 2 失败

| 症状 | 可能原因 | 排查命令 |
|------|----------|----------|
| 情报源连接失败 | URL 不可达或格式错误 | 检查网络连接 |
| 采集无数据 | 情报源无内容或解析错误 | `docker-compose logs worker` |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_URL` | `http://localhost:8000` | API 服务地址 |
| `DEBUG` | `false` | 启用调试输出 |

## 注意事项

1. **数据质量**：REJECTED items 是正常的业务结果，不作为验证失败条件
2. **并发**：验证脚本使用文件锁，同一时间只能运行一个实例
3. **清理**：验证完成后自动清理测试数据，除非指定 `--keep-sources`

## 扩展验证（可选）

### 日志功能验证

v1.2.0 新增了日志导出和清理功能，可手动验证：

```bash
# 导出日志
docker exec cyber-pulse-api-1 cyber-pulse log export --output /tmp/verify.log

# 查看日志统计
docker exec cyber-pulse-api-1 cyber-pulse log stats

# 查看错误日志（JSON 格式）
docker exec cyber-pulse-api-1 cyber-pulse log errors --format json

# 诊断增强功能
docker exec cyber-pulse-api-1 cyber-pulse diagnose system  # 含 API/队列状态
docker exec cyber-pulse-api-1 cyber-pulse diagnose errors  # 含 Rejection Reason
```

### 日志清理验证

```bash
# 清理 7 天前的日志（需确认）
docker exec cyber-pulse-api-1 cyber-pulse log clear --older-than 7d

# 跳过确认直接清理
docker exec cyber-pulse-api-1 cyber-pulse log clear --older-than 30d --yes
```