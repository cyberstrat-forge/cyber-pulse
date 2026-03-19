# 错误处理

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 恢复策略（宽松恢复）

| 场景 | 处理策略 |
|------|---------|
| **采集失败** | 重试 3 次 → 标记失败 → 继续下一个 Source |
| **数据库连接断开** | 自动重连（最多 5 次）→ 失败后暂停任务 |
| **任务执行异常** | 记录错误日志 → 任务失败 → 不阻塞其他任务 |
| **系统崩溃** | 进程退出 → 依赖外部监控重启（systemd/docker-compose） |

**原则：**
- ✅ 单个 Source 失败不应影响其他 Source
- ✅ 错误日志详细，便于后续分析
- ✅ 支持最终一致性（失败任务可手动重试）

---

## 不同 Connector 的错误处理策略

### RSS Connector
- 失败重试：3 次，指数退避（10s, 20s, 40s）
- 连接超时：30 秒
- 解析失败：记录错误，继续下一个条目

### API Connector
- 失败重试：3 次，遵循 HTTP 重试规范
- 速率限制（429）：自动暂停 60 秒，继续
- 认证失败（401/403）：标记 Source 为 pending_review，通知管理员
- 连接超时：30 秒

### Web Scraper
- 失败重试：3 次，指数退避
- 连接超时：60 秒（网页加载慢）
- 解析失败：使用 trafilatura 的容错模式，如仍失败则记录警告
- 临时错误（500/503）：暂停 30 秒，继续

### 速率限制策略
- 每个 Source 独立的速率限制器
- 默认：每分钟最多 10 次请求
- 可在 Source 配置中调整

### 临时错误 vs 永久错误
- **临时错误**：网络超时、500/503、429 → 重试
- **永久错误**：401/403（认证）、404（资源不存在）、解析错误 → 标记失败，不重试

---

## 错误提示机制

**三层提示设计：**

| 层级 | 时机 | 方式 | 详细程度 |
|------|------|------|---------|
| **1. 实时提示** | 命令执行失败时 | 终端直接输出 | 简短，带修复建议 |
| **2. 状态栏警告** | 后台任务失败时 | 底部状态栏显示 ⚠️ | 汇总数量 |
| **3. 详细日志** | 随时查看 | `/log errors` | 完整堆栈 |

**示例：**

```bash
# 场景 1：命令执行失败
cyber-pulse> /source test freebuf.com
❌ 连接失败：TimeoutError (30s)

💡 建议：
   1. 检查网络连接：ping www.freebuf.com
   2. 检查 URL 是否正确
   3. 如网站需要代理，配置代理：/config set proxy.http http://...
   4. 手动测试：/source test <id>

# 场景 2：后台任务失败
Status: 🟢 Running | Jobs: 3 | ⚠️ 2 个任务失败

cyber-pulse> /log errors --since "1h"
⚠️  [14:25:00] Source "FreeBuf" - HTTP 403 Forbidden
⚠️  [14:28:15] Source "腾讯安全" - 正文提取失败

cyber-pulse> /diagnose sources
✓ 正常: 12 个
⚠️  警告: 3 个
✗ 失败: 2 个
```

---

## 日志格式

**结构化 JSON 日志：**

```json
{
  "timestamp": "2026-03-18T14:25:00Z",
  "level": "ERROR",
  "module": "connector.rss",
  "source_id": "src_123",
  "source_name": "FreeBuf",
  "error_type": "connection",
  "message": "HTTP 403 Forbidden",
  "traceback": "...",
  "retry_count": 3,
  "max_retries": 3,
  "suggestion": "检查网站反爬策略或认证配置"
}
```

**日志文件：**
```bash
./logs/
├── app.log           # 应用日志
├── error.log         # 错误日志
├── access.log        # API 访问日志
└── task.log          # 任务日志
```

---

## 诊断工具

**命令：**

```bash
# 系统健康检查
/diagnose system
→ ✓ PostgreSQL: Connected
   ✓ Redis: Connected
   ✓ API Server: Running (port 8000)
   ✓ Scheduler: Active

# 所有 Source 健康状态
/diagnose sources
→ 正常: 12 个
   警告: 3 个
   失败: 2 个

# 特定 Source 诊断
/diagnose source freebuf-com
→ 连接测试: ✓ 成功
   最近 5 次任务:
     2026-03-18 10:00 ✓ 成功 (8 条)
     2026-03-18 09:00 ✗ 失败 (HTTP 403)
   错误统计:
     连接超时: 2 次
     解析失败: 1 次

# 错误分析报告
/diagnose errors
→ 今日错误分析:
   • 连接超时: 8 次
   • 解析失败: 4 次
   • 建议: 检查 FreeBuf 的反爬策略
```