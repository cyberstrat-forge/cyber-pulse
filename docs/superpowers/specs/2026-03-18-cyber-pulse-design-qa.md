# cyber-pulse 设计问题澄清与补充

**日期：** 2026-03-18
**目的：** 对设计文档的补充说明和澄清

---

## 问题 1：单机原型是否需要分级采集频率？

### 答复

**原型阶段建议统一调度频率**，理由如下：

1. **简化设计**
   - 单机原型阶段，情报源数量有限（200-500 个）
   - 统一调度可以减少调度器复杂度
   - 便于测试和调试

2. **实现方案**
   - 默认每小时调度一次所有活跃的 Source
   - 支持手动触发（`./cli job run <source-id>`）
   - 在 Source 配置中保留 `fetch_interval` 字段，为未来分级采集预留

3. **未来扩展**
   - 当扩展到生产版时，可以根据 `tier` 字段配置不同的调度频率：
     - T0: 每小时
     - T1: 每日
     - T2: 每周
   - 这只需要修改 APScheduler 的配置，无需改动核心逻辑

**结论：** 原型阶段采用统一调度，保持简单。

---

## 问题 2：Source 评分低时如何提醒管理员？

### 答复

### 当前设计的降级规则

**自动降级流程：**

```
Source Score < 40
    ↓
自动降级为 T3（观察/降频源）
    ↓
标记为 pending_review
    ↓
状态栏显示警告 ⚠️
```

**具体实现：**

1. **降级触发条件**
   - 连续 2 周评分低于阈值
   - 单周评分低于 30（严重情况立即降级）

2. **管理员通知机制**

   **方式 1：状态栏警告**
   ```
   Status: 🟢 Running | ⚠️ 2 个 Source 需要评估
   ```

   **方式 2：诊断命令**
   ```bash
   # 查看所有需要评估的 Source
   /diagnose sources --pending

   # 输出示例
   → 需要评估的 Source (3 个):
      1. 安全客 (T3, Score: 35)
         - 原因: 连续 3 周评分下降
         - 建议: 检查网站是否改版或失效

      2. FreeBuf (T3, Score: 28)
         - 原因: 噪音比例过高 (60%)
         - 建议: 考虑删除或更新采集规则
   ```

   **方式 3：日志告警**
   ```bash
   /log errors --type review-needed
   ```

3. **管理员操作选项**
   ```bash
   # 选项 1：删除 Source
   /source remove <id>

   # 选项 2：更新配置（如更换 URL、调整规则）
   /source update <id> --url "新地址"

   # 选项 3：手动提升等级（需谨慎）
   /source update <id> --tier T2 --reason "临时恢复"

   # 选项 4：冻结（暂停采集，保留历史）
   /source update <id> --status frozen
   ```

### 建议补充的设计

**增加自动删除提醒机制：**

```bash
# 定期生成评估报告
/server maintenance --generate-review-report

# 报告内容
→ 30 天未更新的 Source: 5 个
→ 评分持续下降的 Source: 3 个
→ 建议删除的 Source: 2 个 (评分 < 20 且 60 天无更新)
```

**结论：** 当前设计已包含降级和通知机制，建议增加定期评估报告功能。

---

## 问题 3：Source 评分是否通过 API 传递给 cyber-nexus？

### 答复

### 当前设计

**Standardized Content Object 数据契约：**

```json
{
  "content_id": "cnt_123",
  "source_id": "src_456",
  "source_name": "安全客",
  "source_tier": "T1",        // ✅ 已包含
  "source_score": 75.5,       // ⚠️ 建议新增
  "normalized_markdown": "...",
  "publish_time": "2026-03-18T10:00:00Z",
  ...
}
```

### 建议补充

**增加 `source_score` 和 `source_quality_metrics` 字段：**

```json
{
  "content_id": "cnt_123",
  "source_id": "src_456",
  "source_name": "安全客",
  "source_tier": "T1",
  "source_score": 75.5,           // 0-100 的评分
  "source_quality_metrics": {     // 可选，详细质量指标
    "content_completeness": 0.92,
    "noise_ratio": 0.08,
    "update_frequency": "daily",
    "stability": 0.95
  },
  "normalized_markdown": "...",
  "publish_time": "2026-03-18T10:00:00Z",
  ...
}
```

### 对 cyber-nexus 的价值

1. **情报可信度评估**
   - 高分来源的内容可信度更高
   - 可用于自动过滤或加权

2. **分析策略优化**
   - 优先处理高分来源的内容
   - 对低分来源的内容增加人工审核

3. **反馈闭环**
   - cyber-nexus 可以基于 `source_score` 调整自己的分析策略
   - 同时通过预留的 API 反馈维度 V 数据

**结论：** 建议在 API 响应中增加 `source_score` 字段，提升数据价值。

---

## 问题 4：情报源添加时如何定义不同类型？

### 答复

### 当前设计的 Source 定义

```yaml
# Source 配置示例
source:
  name: "安全客"
  connector_type: "rss"  # 或 api, web, media, platform
  tier: "T1"
  config:
    url: "https://www.anquanke.com/rss"
    # 其他 Connector 特定配置
```

### 建议补充的 Connector 配置模板

#### 1. RSS Connector

```bash
./cli source add \
  --name "安全客" \
  --connector rss \
  --url "https://www.anquanke.com/rss" \
  --tier T1
```

**自动生成配置：**
```yaml
config:
  feed_url: "https://www.anquanke.com/rss"
  use_auto_discovery: true  # 自动发现 RSS
```

#### 2. API Connector

```bash
./cli source add \
  --name "GitHub Security" \
  --connector api \
  --url "https://api.github.com/security-advisories" \
  --auth-type bearer \
  --auth-token "xxx" \
  --pagination page \
  --tier T0
```

**自动生成配置：**
```yaml
config:
  base_url: "https://api.github.com/security-advisories"
  auth_type: "bearer"
  auth_token: "xxx"  # 加密存储
  pagination_type: "page"
  page_param: "page"
  per_page: 100
```

#### 3. Web Scraper

```bash
./cli source add \
  --name "某博客" \
  --connector web \
  --url "https://example.com/blog" \
  --extraction-mode auto \
  --tier T2
```

**自动生成配置：**
```yaml
config:
  base_url: "https://example.com/blog"
  extraction_mode: "auto"  # auto 或 manual (XPath/CSS)
  link_pattern: "/blog/.*"
  update_frequency: "daily"
```

#### 4. Media API (YouTube)

```bash
./cli source add \
  --name "某 YouTube 频道" \
  --connector media \
  --platform youtube \
  --channel-id "UCxxx" \
  --api-key "xxx" \
  --tier T1
```

**自动生成配置：**
```yaml
config:
  platform: "youtube"
  channel_id: "UCxxx"
  api_key: "xxx"  # 加密存储
  check_captions: true  # 检查字幕是否存在
```

#### 5. Platform Connector (微信公众号)

```bash
./cli source add \
  --name "某微信公众号" \
  --connector platform \
  --platform wechat \
  --official-account "公众号名称" \
  --tier T1
```

**自动生成配置：**
```yaml
config:
  platform: "wechat"
  official_account: "公众号名称"
  # 注意：微信采集需要特殊工具，见问题 5
```

### CLI 交互式添加（推荐）

```bash
./cli source add

# 交互式提示
Name: 安全客
Connector type (rss/api/web/media/platform): rss
URL: https://www.anquanke.com/rss
Tier (T0/T1/T2): T1
Test connection now? (y/n): y
✓ Connection successful
✓ Auto-evaluated quality: 85/100
✓ Assigned to T2 (observation period)
✓ Scheduled for collection
```

**结论：** 支持多种 Connector 配置，建议增加交互式添加功能。

---

## 问题 5：微信公众号采集如何实现？

### 答复

### 微信公众号采集的挑战

1. **官方限制**
   - 微信没有公开的公众号 API
   - 需要登录态和 Cookie
   - 反爬虫机制严格

2. **技术难点**
   - 需要模拟微信客户端行为
   - 动态 Token 管理
   - 频率限制严格

### 可用的开源方案

#### 方案 1: **WechatFeedReader** ⭐ 推荐

```bash
# 安装
pip install wechat-feeds

# 使用
from wechat_feeds import WechatPublicAccount

account = WechatPublicAccount("公众号名称或 ID")
articles = account.get_articles(limit=10)

for article in articles:
    print(article.title)
    print(article.url)
    print(article.publish_time)
```

**特点：**
- ✅ 基于 RSSHub 原理
- ✅ 无需登录
- ✅ 支持 1000+ 公众号
- ✅ 定期更新维护

#### 方案 2: **RSSHub**

```bash
# 部署 RSSHub
docker run -d --name rsshub -p 1200:1200 diygod/rsshub

# 访问公众号 RSS
http://localhost:1200/wechat/ershicimi/公众号ID
```

**配置到 cyber-pulse：**
```bash
./cli source add \
  --name "某公众号" \
  --connector rss \
  --url "http://localhost:1200/wechat/ershicimi/公众号ID" \
  --tier T1
```

#### 方案 3: **itchat + itchatmp**

```python
# 需要微信账号登录，不推荐用于生产
import itchat

itchat.auto_login(hotReload=True)
mps = itchat.search_mps(name="公众号名称")
articles = itchat.get_mps_articles(mps[0]['UserName'])
```

**⚠️ 风险：**
- 需要真实微信账号
- 可能被封号
- 不稳定

### 建议的设计方案

**采用 RSSHub 包装方案：**

```
┌─────────────────────────────────────────────┐
│          cyber-pulse                        │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐     ┌─────────────────┐  │
│  │ RSS Connector│     │  RSSHub 服务    │  │
│  │ (内置)       │     │  (独立部署)     │  │
│  └──────┬───────┘     └────────┬────────┘  │
│         │                      │           │
│         └──────────┬───────────┘           │
│                    │                       │
│         微信公众号 RSS 地址                  │
│  http://localhost:1200/wechat/xxx          │
│                                             │
└─────────────────────────────────────────────┘
```

**操作流程：**

```bash
# 1. 部署 RSSHub
docker run -d --name rsshub -p 1200:1200 diygod/rsshub

# 2. 添加微信公众号到 cyber-pulse
./cli source add \
  --name "安全内参" \
  --connector rss \
  --url "http://localhost:1200/wechat/ershicimi/safety-info" \
  --tier T1 \
  --test

# 3. 验证采集
./cli source test "安全内参"
```

**优势：**
- ✅ 无需微信账号
- ✅ 社区维护，支持广泛
- ✅ cyber-pulse 无需特殊处理
- ✅ 符合"外部服务 Connector"设计理念

**结论：** 推荐使用 RSSHub 包装微信公众号，作为外部服务集成方案。

---

## 问题 6：术语修正 - "战略价值初筛" → "数据结构质量控制"

### 答复

**已完成修正：**

- ✅ 1.1 目标与定位：已修改
- ✅ 1.2 单机原型范围：已修改
- ✅ 全文档搜索：无"战略价值初筛"字样

**修正后的表述：**

- "数据清洗与标准化（转为 Markdown）"
- "数据结构质量控制"
- "质量控制阶段（Quality Gate）"

---

## 问题 7：cyber-nexus 如何实现消费者职责？

### 答复

### 当前设计的缺失

设计文档定义了 Pull + Cursor 模型，但**未提供消费者实现样例**。

### 建议补充的实现样例

#### Python 客户端示例

```python
# cyber-nexus 消费者实现
import requests
import json
import time

class CyberPulseConsumer:
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.cursor = self._load_cursor()  # 从本地文件加载

    def _load_cursor(self):
        """从本地文件加载 cursor"""
        try:
            with open("cursor.txt", "r") as f:
                return int(f.read().strip())
        except:
            return 0  # 首次运行

    def _save_cursor(self, cursor):
        """保存 cursor 到本地文件"""
        with open("cursor.txt", "w") as f:
            f.write(str(cursor))

    def fetch_incremental(self, limit=100):
        """拉取增量数据"""
        params = {
            "cursor": self.cursor,
            "limit": limit
        }

        response = requests.get(
            f"{self.api_url}/api/v1/content",
            headers=self.headers,
            params=params
        )

        if response.status_code == 200:
            data = response.json()
            contents = data["data"]

            if contents:
                # 处理数据（去重、写入 iNBox）
                self._process_contents(contents)

                # 更新 cursor
                self.cursor = data["next_cursor"]
                self._save_cursor(self.cursor)

                print(f"✓ Fetched {len(contents)} items, new cursor: {self.cursor}")

            return contents
        else:
            print(f"✗ Error: {response.status_code}")
            return []

    def _process_contents(self, contents):
        """处理内容（去重、写入 iNBox）"""
        for content in contents:
            content_id = content["content_id"]

            # 幂等性检查（基于 content_id）
            if not self._exists_in_inbox(content_id):
                # 写入 iNBox
                self._write_to_inbox(content)

    def _exists_in_inbox(self, content_id):
        """检查是否已存在（幂等性）"""
        # 实现：检查本地数据库或文件
        pass

    def _write_to_inbox(self, content):
        """写入 iNBox"""
        # 实现：保存为 Markdown 文件
        filename = f"inbox/{content['content_id']}.md"
        with open(filename, "w") as f:
            f.write(self._format_markdown(content))

    def _format_markdown(self, content):
        """格式化为 Markdown"""
        md = f"""# {content['original_title']}

来源: {content['source_name']} ({content['source_tier']})
发布时间: {content['publish_time']}
Score: {content.get('source_score', 'N/A')}

{content['normalized_markdown']}
"""
        return md

    def run_forever(self, interval=300):
        """持续运行，定期拉取"""
        while True:
            try:
                self.fetch_incremental()
                time.sleep(interval)  # 每 5 分钟拉取一次
            except KeyboardInterrupt:
                print("Stopped by user")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)  # 错误后等待 1 分钟

# 使用示例
if __name__ == "__main__":
    consumer = CyberPulseConsumer(
        api_url="http://localhost:8000",
        api_key="sk_live_xxx"
    )

    # 启动消费者
    consumer.run_forever(interval=300)
```

#### 关键要点

1. **Cursor 管理**
   - 本地文件存储 (`cursor.txt`)
   - 每次拉取后更新并持久化

2. **幂等性处理**
   - 基于 `content_id` 去重
   - 避免重复处理

3. **错误处理**
   - 网络错误自动重试
   - 记录失败日志

4. **数据存储**
   - 写入 iNBox 目录
   - 格式化为 Markdown

### 建议补充到设计文档

在"4.5.1 接口模型"章节后增加：

```markdown
### 4.5.5 消费者实现样例

[提供上述 Python 示例代码]

**关键要点：**
- Cursor 本地持久化
- 基于 content_id 幂等处理
- 定期轮询（建议 5-10 分钟）
- 错误重试机制
```

**结论：** 建议在设计文档中补充消费者实现样例。

---

## 问题 8：content get 命令的参数合理性

### 答复

### 当前设计

```bash
/content get <content-id>  # 仅支持 ID 查询
```

### 建议补充

**增加时间维度和过滤参数：**

```bash
# 按 ID 查询（现有）
/content get <content-id>

# 按时间范围查询（新增）
/content get --since "2026-03-18" --until "2026-03-19" --limit 10

# 按 Source 查询（新增）
/content get --source "安全客" --limit 5

# 组合查询（新增）
/content get --source "安全客" --since "2026-03-18" --limit 10
```

### 具体设计

```bash
Usage: /content get [OPTIONS]

Options:
  --id <content-id>           # 按 ID 精确查询
  --since <timestamp>         # 起始时间（含）
  --until <timestamp>         # 结束时间（含）
  --source <name>             # 按 Source 过滤
  --tier <T0|T1|T2>           # 按等级过滤
  --limit <number>            # 返回数量限制（默认 100）
  --format <json|markdown>    # 输出格式（默认 json）

Examples:
  /content get cnt_123                    # 精确查询
  /content get --since "2h"               # 最近 2 小时
  /content get --since "2026-03-18"       # 某天之后
  /content get --source "安全客" --limit 5
  /content get --tier T0 --limit 10       # 最新的 T0 内容
```

**结论：** 建议增加时间维度和过滤参数，提升实用性。

---

## 问题 9：交互式界面的初始显示和执行结果

### 答复

### 当前设计缺失

设计文档描述了布局结构，但**未说明具体内容**。

### 建议补充的详细设计

#### 初始进入时显示

```
┌─────────────────────────────────────────────────────────┐
│  🚀 cyber-pulse CLI (v1.0)                              │
│  Type '/help' for available commands                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Welcome to cyber-pulse!                                │
│                                                          │
│  System Status:                                         │
│  • API Server: 🟢 Running on port 8000                  │
│  • Database: 🟢 Connected                                │
│  • Redis: 🟢 Connected                                   │
│  • Active Sources: 12 (T0: 2, T1: 5, T2: 5)             │
│  • Scheduled Jobs: 1                                     │
│                                                          │
│  Recent Activity:                                       │
│  [2026-03-18 10:30:15] ✓ Source "安全客" added (T2)    │
│  [2026-03-18 10:30:20] 📅 Scheduled for daily fetch     │
│                                                          │
│  Tips:                                                  │
│  • Run '/source list' to see all sources                │
│  • Run '/diagnose system' to check system health        │
│  • Run '/help' to see all commands                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
│  cyber-pulse>                                            │
├─────────────────────────────────────────────────────────┤
│  Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1 │
└─────────────────────────────────────────────────────────┘
```

#### 命令执行后显示

**场景 1：成功执行**

```
cyber-pulse> /source list --tier T1

┌──────────────────────────────────────────────┐
│  Sources (T1) - 5 items                      │
├──────────────────────────────────────────────┤
│  1. 安全客                                    │
│     URL: https://www.anquanke.com            │
│     Status: active | Score: 75.5             │
│                                              │
│  2. FreeBuf                                  │
│     URL: https://www.freebuf.com             │
│     Status: active | Score: 82.3             │
│                                              │
│  ...                                         │
└──────────────────────────────────────────────┘

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1
```

**场景 2：失败执行**

```
cyber-pulse> /source test invalid-id

❌ Error: Source not found

💡 Suggestion:
   • Run '/source list' to see available sources
   • Check the source ID or name

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1
```

**场景 3：长时间任务**

```
cyber-pulse> /job run security-news

🔄 Starting job for "安全客"...
⏳ Fetching data from source...
⏳ Processing 8 items...
✓ Job completed successfully
  • Retrieved: 8 items
  • Passed QC: 8 items
  • Failed: 0 items

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 0
```

**场景 4：实时日志**

```
cyber-pulse> /log tail -f

[2026-03-18 14:30:05] INFO     Task started: source_security-news
[2026-03-18 14:30:06] INFO     Fetching from RSS feed...
[2026-03-18 14:30:08] INFO     Retrieved 8 items
[2026-03-18 14:30:10] INFO     Normalizing content...
[2026-03-18 14:30:12] INFO     Quality check passed: 8/8
[2026-03-18 14:30:13] INFO     Task completed successfully
^C (Ctrl+C to stop)

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 0
```

### 界面行为规范

| 行为 | 说明 |
|------|------|
| **初始显示** | 欢迎信息 + 系统状态 + 最近活动 + 使用提示 |
| **命令执行** | 显示执行结果（表格/列表/错误信息） |
| **实时输出** | 长时间任务显示进度，日志显示实时流 |
| **错误提示** | 红色文字 + 建议修复方案 |
| **成功提示** | 绿色勾号 ✓ + 统计信息 |

**结论：** 建议在设计文档中补充详细的界面行为规范。

---

## 问题 10：设备性能要求

### 答案

### 建议补充的硬件要求

#### 最低配置（开发/测试环境）

```
CPU: 2 核
内存: 4 GB
磁盘: 20 GB (SSD 推荐)
网络: 100 Mbps
操作系统: Linux / macOS / Windows (WSL2)
```

**适用场景：**
- 开发调试
- 小规模测试（< 50 个 Source）
- 日处理量 < 1,000 条

#### 推荐配置（原型验证环境）

```
CPU: 4 核
内存: 8 GB
磁盘: 50 GB SSD
网络: 1 Gbps
操作系统: Linux (Ubuntu 20.04+)
```

**适用场景：**
- 单机原型运行
- 200-500 个 Source
- 日处理量 1,000-10,000 条

#### 高性能配置（接近生产）

```
CPU: 8 核
内存: 16 GB
磁盘: 100 GB SSD + 500 GB HDD (数据存储)
网络: 1 Gbps
操作系统: Linux (CentOS 7+ / Ubuntu 20.04+)
```

**适用场景：**
- 500+ 个 Source
- 日处理量 10,000+ 条
- 需要长时间稳定运行

### 资源占用估算

| 组件 | 内存 | 磁盘 | 说明 |
|------|------|------|------|
| PostgreSQL | 512 MB | 10 GB | 根据数据量增长 |
| Redis | 256 MB | 1 GB | 缓存和队列 |
| App (Python) | 512 MB | 5 GB | 代码 + 运行时 |
| 原始数据存储 | - | 20 GB | 1 年数据估算 |
| 日志文件 | - | 5 GB | 结构化日志 |

**总计：**
- 内存：~1.5 GB (运行时)
- 磁盘：~40 GB (1 年数据 + 系统)

### 网络带宽估算

**日采集 10,000 条：**
- 平均每条 50 KB (HTML + 图片)
- 日流量：~500 MB
- 月流量：~15 GB

**建议：**
- 宽带：至少 100 Mbps
- 流量：月 50 GB 以上套餐

### Docker 资源限制

```yaml
# docker-compose.yml
services:
  app:
    mem_limit: 1g
    cpus: 2.0

  postgres:
    mem_limit: 1g
    cpus: 1.0

  redis:
    mem_limit: 512m
    cpus: 0.5
```

### 监控建议

```bash
# 系统资源监控
docker stats  # 实时查看容器资源

# 磁盘空间
df -h  # 查看磁盘使用

# 内存
free -h  # 查看内存使用
```

**结论：** 建议在"6. 部署与运维"章节增加"6.4 硬件要求"小节。

---

## 总结与下一步

### 已确认的修改

1. ✅ 术语修正："战略价值初筛" → "数据结构质量控制"
2. ✅ 调度器简化：统一调度频率（原型阶段）
3. ✅ 其他问题：需更新设计文档

### 需要更新设计文档的内容

1. **增加章节：** 4.5.5 消费者实现样例
2. **完善章节：** 4.6.3 交互式界面详细行为
3. **增加章节：** 4.1.4 Source 评分提醒机制
4. **补充字段：** API 响应增加 `source_score`
5. **扩展命令：** `/content get` 增加时间过滤
6. **增加章节：** 6.4 硬件要求
7. **补充说明：** 微信公众号采集方案（RSSHub）

**建议：** 我将更新设计文档，然后请您再次审核。

---

**文档结束**
