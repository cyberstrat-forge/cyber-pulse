# cyber-pulse 单机原型版技术规格说明书

**版本：** v1.1
**日期：** 2026-03-18
**作者：** 老罗
**状态：** 草案

---

## 1. 项目概述

### 1.1 目标与定位

cyber-pulse 是一个**内部战略情报采集与标准化系统**，定位为"数据生产引擎层"，负责：

- 从多个情报源自动化采集数据
- 内容抽取与结构化处理
- 数据清洗与标准化（转为 Markdown）
- 数据结构质量控制
- 增量更新机制
- 通过拉取式 API 向下游分析系统提供数据

**关键定位：**
- ✅ **职责分离**：只负责数据生产，不负责情报分析
- ✅ **下游系统**：cyber-nexus（情报分析应用）负责长期存储情报卡片、主题报告等战略资产
- ✅ **数据保留**：cyber-pulse 数据保留 1 年，长期价值数据由 cyber-nexus 保存

---

### 1.2 单机原型范围

**本次实现范围（v1 单机原型）：**
- ✅ 单机部署，适合开发验证
- ✅ 支持 200-500 个情报源
- ✅ 日处理量 1,000-10,000 条
- ✅ 核心功能完整（采集、标准化、数据结构质量控制、API 服务）
- ✅ 完整的 Source Governance 体系

**暂不实现：**
- ❌ 分布式部署
- ❌ 大数据架构（Kafka、Flink 等）
- ❌ 消息队列（单机场景不需要）
- ❌ 多租户模式

---

### 1.3 与生产版的差异

| 方面 | 单机原型版 | 生产版 |
|------|-----------|--------|
| 数据库 | PostgreSQL | CockroachDB |
| 调度器 | APScheduler | Airflow |
| 任务队列 | Dramatiq | Celery + Redis Cluster |
| 存储 | 本地文件系统 | S3/MinIO |
| 消息组件 | 无 | Kafka（如需） |
| 部署方式 | `docker-compose up` | Kubernetes |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    cyber-pulse (单机原型)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Connector Layer                          │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  内置 Connector (轻量)         外部服务 Connector      │  │
│  │  • RSS (feedparser)           • RSSHub (包装为 RSS)   │  │
│  │  • API (httpx)                • FreshRSS (订阅模式)   │  │
│  │  • Web (trafilatura)          • Nifi (HTTP 推送)      │  │
│  │  • Media (google-api)         • ...                   │  │
│  │                                                       │  │
│  └───────────────┬───────────────────────┬───────────────┘  │
│                  │                       │                  │
│  ┌───────────────▼───────────────────────▼───────────────┐  │
│  │           Normalization & Quality Gate                │  │
│  │      (内容抽取 → 清洗 → 质量控制 → 标准化)             │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              Source Governance Layer                  │  │
│  │      (Source Score + 治理 + 等级演化)                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              PostgreSQL (核心存储)                     │  │
│  │  • Source 表 (永久)                                    │  │
│  │  • Item 表 (365 天)                                    │  │
│  │  • Content 表 (365 天)                                 │  │
│  │  • api_clients 表 (永久)                               │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              API Layer (FastAPI)                      │  │
│  │      • 增量拉取 API (Pull + Cursor)                    │  │
│  │      • API Key 认证                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              APScheduler (调度器)                      │  │
│  │      • 统一调度频率（原型阶段简化）                    │  │
│  │      • 默认每小时一次（所有活跃 Source）               │  │
│  │      • 支持手动触发                                    │  │
│  │      • 保留 fetch_interval 配置（未来分级预留）       │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              Dramatiq (任务队列)                       │  │
│  │      • 采集任务                                          │  │
│  │      • 标准化任务                                        │  │
│  │      • 质量控制任务                                      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              CLI 工具 (终端 TUI)                        │  │
│  │      • source / job / content / client 管理             │  │
│  │      • config / log / diagnose 诊断工具                 │  │
│  │      • 交互式模式 (类似 Claude Code)                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 技术栈选型

| 层级 | 技术 | 说明 |
|------|------|------|
| **运行时** | Python 3.11+ | 主语言，生态成熟 |
| **Web 框架** | FastAPI | 类型安全，自动生成 API docs |
| **数据库** | PostgreSQL 15 | 单机部署简单，支持 JSONB |
| **调度器** | APScheduler | 单机调度，无需 Airflow 复杂度 |
| **任务队列** | Dramatiq + Redis | 轻量级，单 worker 足够 |
| **缓存** | Redis | 去重、状态管理、速率控制 |
| **存储** | 本地文件系统 | 开发期直接写入本地目录 |
| **CLI 工具** | Typer + Prompt Toolkit + Rich | 终端 TUI，交互式体验 |
| **正文提取** | trafilatura | 高质量正文提取 |
| **HTTP 客户端** | httpx | 支持 async，功能强大 |
| **RSS 解析** | feedparser + feedfinder2 | 标准库，稳定可靠 |

---

### 2.3 数据流

```
用户添加 Source
    ↓
[检查重复] - 检查 name 或 URL 是否已存在
    ↓ (重复) 标记为重复，提示用户
    ↓ (不存在)
[快速准入评估]
  • 连接测试
  • 首次采集（5-10 条样本）
  • 质量评估（元数据、正文、噪音）
    ↓
达标 → 定级为 T2 → 立即加入调度队列
    ↓
APScheduler 统一调度（每小时触发所有活跃 Source）
    ↓
Connector 采集原始数据 → Item
    ↓
Normalization（正文提取、清洗、转 Markdown）
    ↓
Quality Gate（数据结构质量控制）
    ↓
达标 → 关联/创建 Content → 写入数据库
    ↓
Source Score 更新（统计反馈）
    ↓
cyber-nexus 通过 Pull API 拉取增量数据
```

---

## 3. 核心数据模型

### 3.1 数据实体

[引用自 `docs/2026-03-17 cyber-pulse Core Data Model 设计.md`]

系统核心包含三个实体：

- **Source**：情报来源元数据（分级、评分、采集配置）
- **Item**：每次采集的原始记录（追加写入，按 `external_id`/`url` 去重）
- **Content**：去重后的逻辑内容实体（多个 Item 可映射到同一 Content）

关系：`Source → Item → Content`

---

### 3.2 数据保留策略

| 表 | 保留周期 | 说明 |
|-----|---------|------|
| **Source** | 永久 | 治理历史需长期追溯 |
| **Item** | **365 天** | 原始采集记录（含失败记录） |
| **Content** | **365 天** | 标准化内容 |
| **api_clients** | 永久 | API 客户端配置 |
| **source_score_history** | 永久 | 评分变化历史 |

**理由：**
- ✅ cyber-pulse 是"数据生产引擎层"，不存储长期价值数据
- ✅ 长期战略资产（情报卡片、主题报告）由 cyber-nexus 保存
- ✅ **统一 365 天周期**，清晰明确，便于运维管理

---

## 4. 功能模块设计

### 4.1 Source 管理

#### 4.1.1 分级模型

[引用自 `docs/2026-03-17 cyber-pulse Source 分级模型设计说明.md`]

| 等级 | 含义 | 采集频率 | 评分范围 | 说明 |
|------|------|---------|---------|------|
| **T0** | 核心战略源 | 高频 | ≥ 80 | 高可信度、高战略相关性、长期持续输出 |
| **T1** | 重要参考源 | 中频 | 60–80 | 有价值但存在波动，需要规则过滤 |
| **T2** | 普通观察源 | 低频 | 40–60 | 潜在价值，不确定性高，用于趋势探索 |
| **T3** | 观察/降频源 | 极低频或暂停 | < 40 | 质量不达标，需评估是否保留 |

**原型阶段调度说明：**
- ✅ **统一调度频率**：所有活跃 Source 统一每小时调度一次
- ✅ **简化设计**：便于测试和调试
- ✅ **未来预留**：Source 配置中保留 `fetch_interval` 字段，生产版可根据 `tier` 配置不同频率

---

#### 4.1.2 准入流程

[本次设计新增]

**优化方案：立即评估 → 快速定级**

```
用户添加 Source
    ↓
[检查重复] - 检查 name 或 URL 是否已存在
    ↓ (存在)
标记为重复，提示用户
    ↓ (不存在)
[连接测试] - 能否访问？
    ↓ (失败)
标记为 pending_review，提示用户
    ↓ (成功)
[首次采集] - 获取 5-10 条样本
    ↓
[质量评估]
  • 元数据完整度 ≥ 80% ?
  • 正文完整度 ≥ 70% ?
  • 噪音比例 ≤ 30% ?
  • 无异常错误？
    ↓ (不达标)
标记为 pending_review，记录失败原因
    ↓ (达标)
自动定级为 T2
    ↓
标记为观察期（is_in_observation = true，30 天）
    ↓
立即加入调度队列，开始采集
```

**观察期保护（软观察期）：**
- 前 30 天为"观察期"
- 观察期内：
  - ✅ 可正常采集
  - ✅ 可晋升到 T1（如表现优秀，需连续 2 周达标）
  - ✅ 可降级到 T3（如质量差）
  - ❌ 不允许晋升到 T0（需要完整运行数据）
  - ✅ 如发现质量问题，可快速降级或冻结

> ⚠️ **与已有文档的差异**
>
> 在 `docs/2026-03-17 cyber-pulse Source Governance Model.md` 中，新来源默认进入"未分级观察期"，30 天后才开始采集。
>
> **本次调整为：立即评估 → 达标即入 T2 → 立即开始采集**
>
> **理由：**
> - 用户体验更好（类似 RSS 订阅，添加即用）
> - 充分利用早期数据（不浪费前 30 天）
> - 风险可控（观察期内可快速降级）
> - 符合单机原型验证场景的快速迭代需求
>
> **治理原则不变：**
> - 新来源不会直接成为 T0（需 30 天观察期后评估）
> - 观察期内的异常表现可触发快速降级

---

#### 4.1.3 等级演化规则

[引用自 `docs/2026-03-17 cyber-pulse Source Governance Model.md`]

**晋升逻辑：**
- 长期评分达到阈值
- 多周期稳定达标（连续 2-3 周）
- 价值信号持续存在

**降级逻辑：**
- 长期评分低于阈值
- 连续 2 周不达标
- 稳定性不足或噪音比例过高

**强制复审：**
- T0 来源：每 90 天自动复审一次，避免等级固化

---

#### 4.1.4 评分低的提醒与管理员操作

[本次设计新增]

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

**降级触发条件：**
- 连续 2 周评分低于阈值
- 单周评分低于 30（严重情况立即降级）

**管理员通知机制：**

1. **状态栏警告**
   ```
   Status: 🟢 Running | ⚠️ 2 个 Source 需要评估
   ```

2. **诊断命令**
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

3. **日志告警**
   ```bash
   /log errors --type review-needed
   ```

**管理员操作选项：**
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

**建议的定期评估报告：**
```bash
# 定期生成评估报告
/server maintenance --generate-review-report

# 报告内容
→ 30 天未更新的 Source: 5 个
→ 评分持续下降的 Source: 3 个
→ 建议删除的 Source: 2 个 (评分 < 20 且 60 天无更新)
```

---

### 4.2 Connector 体系

#### 4.2.1 内置 Connector

**技术选型：**

| Connector | 开源库 | 说明 |
|-----------|--------|------|
| **RSSConnector** | `feedparser` + `feedfinder2` | RSS/Atom 解析，自动发现 RSS 地址 |
| **APIConnector** | `httpx` | 通用 API 采集，支持认证、分页 |
| **WebScraper** | `httpx` + `trafilatura` | 网页抓取 + 正文提取 |
| **MediaAPIConnector** | `google-api-python-client` | YouTube/Twitter 等媒体平台 |

**CLI 配置示例：**

**1. RSS Connector**
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

**2. API Connector**
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

**3. Web Scraper**
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

**4. Media API (YouTube)**
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

---

#### 4.2.2 微信公众号采集方案

[本次设计新增]

**挑战：**
- 微信无公开 API，需要登录态和 Cookie
- 反爬虫机制严格

**推荐方案：使用 RSSHub 包装**

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
  --url "http://localhost:1200/wechat/ershicimi/公众号ID" \
  --tier T1 \
  --test

# 3. 验证采集
./cli source test "安全内参"
```

**优势：**
- ✅ 无需微信账号
- ✅ 社区维护，支持广泛
- ✅ 符合"外部服务 Connector"设计理念

---

#### 4.2.3 外部服务集成（可选扩展）

**场景：** 将无 RSS 网站包装为 RSS

**推荐工具：**
- **RSSHub**：最流行的 RSS 生成器，支持 1000+ 网站
  - 包括微信公众号、微博、知乎、GitHub 等平台
  - **微信公众号路由**：`/wechat/ershicimi/:id` （公众号名称或 ID）
- **FreshRSS**：自托管 RSS 阅读器

**集成方式：**
```
网站 A (无 RSS)  →  RSSHub  →  cyber-pulse (RSS Connector)
```

**操作流程：**

**1. 部署 RSSHub（独立服务）**
```bash
docker run -d --name rsshub -p 1200:1200 diygod/rsshub
```

**2. 配置 cyber-pulse 订阅 RSSHub**

```bash
# 示例 1：GitHub Trending
./cli source add \
  --name "GitHub Trending" \
  --connector rss \
  --tier T1 \
  --config 'feed_url=http://localhost:1200/github/trending/daily'

# 示例 2：微信公众号
./cli source add \
  --name "安全内参" \
  --connector rss \
  --tier T1 \
  --config 'feed_url=http://localhost:1200/wechat/ershicimi/安全内参'
```

**优势：**
- ✅ 无需微信账号，避免封号风险
- ✅ 社区维护，支持广泛的平台
- ✅ cyber-pulse 无需特殊处理，统一使用 RSSConnector
- ✅ 符合"外部服务 Connector"设计理念

---

### 4.3 数据处理流水线

[引用自 `docs/2026-03-17 cyber-pulse 业务 Workflow.md` 和相关文档]

#### 4.3.1 采集阶段（Ingestion）

**输入：** Source 配置
**输出：** Item（原始记录）

**处理：**
1. 调用对应的 Connector
2. 获取原始数据（HTML/RSS/JSON）
3. 提取基础字段（title, url, published_at）
4. 生成 `content_hash`
5. 写入 Item 表

---

#### 4.3.2 标准化阶段（Normalization）

**输入：** Item
**输出：** 标准化内容（Markdown）

**处理流程：**

1. **正文提取**
   - 使用 `trafilatura` 提取正文
   - 处理 JavaScript 动态内容（如需）

2. **数据清洗（标准清洗）**
   - 移除 HTML 标签
   - 转换为 Markdown（标题、段落、列表、表格、代码块、引用）
   - 统一换行符（`\n`）
   - 去除多余空白
   - Unicode 标准化
   - 移除广告标识（"广告"、"推广"、"推荐阅读"等）

3. **元数据补全**
   - `source_id`, `source_name`, `source_tier`
   - `publish_time`（UTC + ISO 8601）
   - `connector_type`
   - `language`（可选）

4. **去重处理**
   - 计算 `canonical_hash`（标题 + 正文）
   - 如已存在相同 hash，复用已有 Content
   - 新 Item 关联到该 Content

---

#### 4.3.3 质量控制阶段（Quality Gate）

[引用自 `docs/2026-03-17 cyber-pulse 业务 Workflow.md`]

**目标：** 确保进入可用域的数据满足最低质量契约

**核心字段（必须满足，否则拒绝）：**

| 字段 | 要求 | 失败处理 |
|------|------|---------|
| `published_at` | 有效日期（非空、合理范围） | ❌ 拒绝 |
| `title` | 非空、长度 ≥ 5 字符 | ❌ 拒绝 |
| `body`（正文） | 非空 | ❌ 拒绝 |
| `url` | 非空、格式合法 | ❌ 拒绝 |

**可选字段（缺失仅警告，但允许通过）：**

| 字段 | 要求 | 失败处理 |
|------|------|---------|
| `author` | 可选 | ⚠️ 标记警告 |
| `body_length` | 短文本检测 | ⚠️ 标记"短正文" |

**统计指标（用于 Source Score，不影响准入）：**
- 正文纯文本比例
- 广告/噪音比例
- HTML 标签密度
- 标题-正文一致性
- 元数据完整度

**处理结果：**
- ✅ **Pass** → 进入 Curated Storage（对外 API 数据源）
- ❌ **Drop** → 不进入可用数据域（记录拒绝原因）

---

### 4.4 Source Score 系统

[引用自 `docs/2026-03-17 cyber-pulse Source Score v2.2.md`]

#### 4.4.1 实现范围（标准版）

**包含：**
- ✅ 自闭环评分（维度 C：采集质量指标）
- ✅ 预留战略价值接口（维度 V：API 端点）
- ✅ 权重配置化（JSON 配置，可人工调整）
- ✅ 等级最小停留周期（防震荡）
- ✅ 强制复审机制（T0 每 90 天）
- ✅ 异常检测（指标突变标记）

**不包含：**
- ❌ 在线自学习（权重自动调整）

**原型阶段特殊处理：**
- **维度 V（战略价值）**：原型阶段暂设为默认值 `V=0.5`（中等价值）
- **理由**：cyber-nexus 系统尚未接入，无法获取实际反馈数据
- **未来扩展**：当 cyber-nexus 就绪后，通过预留的 API 接口提供真实的战略价值评分

> ⚠️ **说明：** 原型阶段的评分可能不够准确（缺少维度 V），但可以验证治理流程（等级演化、强制复审、异常检测）。当 cyber-nexus 接入后，评分系统将自动使用真实的维度 V 数据。

---

#### 4.4.2 评分维度

**维度一：采集健康度 C（自闭环）**

| 指标 | 权重 | 说明 |
|------|------|------|
| 源稳定性 Cs | 30% | 过去 30 天至少 1 次更新 |
| 更新活跃度 Cf | 30% | 周期发布数 / 参考值 |
| 内容规范度 Cq | 40% | 元数据完整度 + 正文完整度 + 信噪比 + 重复率 |

**维度二：战略价值 V（外部反馈）**

| 指标 | 权重 | 说明 |
|------|------|------|
| 信息相关性 Vi | 50% | 由 cyber-nexus 提供 |
| 决策贡献 Vr | 30% | 由 cyber-nexus 提供 |
| 持续价值 Vc | 20% | 由 cyber-nexus 提供 |

**综合评分：**
```
SourceScore = w_c * C + w_v * V + w_t * T
```

其中 `w_c + w_v + w_t = 1`，初始建议：`w_c=0.5`, `w_v=0.4`, `w_t=0.1`

---

#### 4.4.3 等级划分

| 等级 | 分数范围 | 说明 |
|------|---------|------|
| T0 | ≥ 80 | 核心战略源 |
| T1 | 60–80 | 重要参考源 |
| T2 | 40–60 | 普通观察源 |
| T3 | < 40 | 观察/降频源 |

---

### 4.5 API 服务

[引用自 `docs/2026-03-17 cyber-pulse 数据服务接口规范.md`]

#### 4.5.1 接口模型

**Pull + Cursor 增量模型**

数据流：
```
Source → cyber-pulse → Curated Storage → Pull API → cyber-nexus → iNBox → 情报卡片
```

**关键特性：**
- ✅ 不采用事件推送
- ✅ 不记录消费状态
- ✅ 不维护下游系统的处理记录
- ✅ 支持多消费者并行
- ✅ 支持增量与重算
- ✅ 语义为 at-least-once

**消费者职责（cyber-nexus）：**
- ✅ 维护自己的 cursor
- ✅ 基于 `content_id` 实现幂等
- ✅ 写入本地 iNBox 目录
- ✅ 生成情报卡片并长期保存

---

#### 4.5.2 API 端点设计

**获取内容：**

```http
GET /api/v1/content?cursor=12345&since=2026-03-18T10:00:00Z&limit=100
Authorization: Bearer sk_live_xxx
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `cursor` | int | 基于 ID 的游标（上次读取的最大 `content_id`） |
| `since` | timestamp | 基于时间的游标（某时间之后的数据） |
| `limit` | int | 每页数量（默认 100，最大 1000） |
| `source_tier` | enum | 可选：按等级过滤（T0/T1/T2） |

**响应格式：**

```json
{
  "data": [
    {
      "content_id": "cnt_123",
      "source_id": "src_456",
      "source_name": "安全客",
      "source_tier": "T1",
      "source_score": 75.5,
      "source_quality_metrics": {
        "content_completeness": 0.92,
        "noise_ratio": 0.08,
        "update_frequency": "daily",
        "stability": 0.95
      },
      "original_title": "XXX 漏洞分析",
      "publish_time": "2026-03-18T10:00:00Z",
      "processed_time": "2026-03-18T10:05:00Z",
      "normalized_markdown": "...",
      "content_hash": "abc123...",
      "language": "zh",
      "metadata": {
        "author": "张三",
        "word_count": 1500
      }
    }
  ],
  "next_cursor": 12445,
  "has_more": true,
  "count": 100,
  "server_timestamp": "2026-03-18T10:30:00Z"
}
```

**关键字段说明：**
- `source_score`：0-100 评分，为 cyber-nexus 提供情报可信度评估依据
- `source_quality_metrics`：可选详细质量指标，用于细粒度可信度计算

---

#### 4.5.3 认证机制

**API Key 认证**

```http
Authorization: Bearer sk_live_xxx
```

**API 客户端管理：**

```bash
# 创建 API 客户端
./cli client create --name "cyber-nexus" --permissions read

# → 生成 API Key: sk_live_a1b2c3d4e5f6...

# 列出所有客户端
./cli client list

# 禁用客户端
./cli client disable <client-id>
```

**数据模型：**

```sql
CREATE TABLE api_clients (
    client_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    permissions JSONB,
    rate_limit INT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);
```

---

#### 4.5.4 错误模型

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数错误 |
| 401 | 认证失败 |
| 403 | 未授权（未来扩展） |
| 404 | 不适用资源 |
| 429 | 限流（达到 rate_limit） |
| 500 | 内部错误 |
| 503 | 服务不可用 |

---

#### 4.5.5 消费者实现样例（cyber-nexus）

[本次设计新增]

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
Score: {content.get('source_score', 'N/A')}
发布时间: {content['publish_time']}

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

**关键要点：**
- Cursor 本地持久化（文件存储）
- 基于 `content_id` 幂等处理
- 定期轮询（建议 5-10 分钟）
- 错误重试机制

---

### 4.6 CLI 工具

#### 4.6.1 命令结构

**非交互式模式（脚本/终端直接执行）：**
```bash
./cli <模块> <子命令> [参数]
```

**交互式模式（`./cli` 或 `./cli shell`）：**
```bash
cyber-pulse> /<模块> <子命令> [参数]
```

---

#### 4.6.2 模块与子命令

```
cyber-pulse CLI (v1.1)
├── source [子命令]
│   ├── list [--tier T0|T1|T2]
│   ├── add --name <name> --url <url> ...
│   ├── update <id> [--tier T1]
│   ├── remove <id>
│   ├── test <id>
│   └── stats
│
├── job [子命令]
│   ├── list [--status running|failed]
│   ├── run <source-id>
│   ├── cancel <job-id>
│   └── status <job-id>
│
├── content [子命令]
│   ├── list [--limit 10]
│   ├── get [--id <content-id>] [--since <timestamp>] [--until <timestamp>] [--source <name>] [--tier <T0|T1|T2>] [--limit <number>] [--format <json|markdown>]
│   └── stats
│
├── client [子命令]
│   ├── create --name <name> ...
│   ├── list
│   ├── update <id> ...
│   ├── disable <id>
│   ├── enable <id>
│   └── delete <id>
│
├── config [子命令]
│   ├── get <key>
│   ├── set <key> <value>
│   ├── list
│   └── reset
│
├── log [子命令]
│   ├── tail [-n N] [-f]
│   ├── errors [--since TIME] [--source <name>]
│   ├── search <text>
│   ├── stats
│   └── clear
│
├── diagnose [子命令]
│   ├── system
│   ├── sources [--pending]
│   ├── source <id>
│   └── errors
│
├── server [子命令]
│   ├── start
│   ├── stop
│   ├── restart
│   ├── status
│   ├── health
│   └── maintenance --generate-review-report
│
├── help
├── version
└── exit
```

---

#### 4.6.3 交互式界面设计

[本次设计新增]

**布局结构：**
```
┌─────────────────────────────────────────────────────────┐
│  🚀 cyber-pulse CLI (v1.1)                              │
│  Type '/help' for available commands                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Output Area: 命令执行结果/历史记录]                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
│  cyber-pulse> [Input Area]                              │
├─────────────────────────────────────────────────────────┤
│  Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: X │
└─────────────────────────────────────────────────────────┘
```

**初始进入时显示：**

```
┌─────────────────────────────────────────────────────────┐
│  🚀 cyber-pulse CLI (v1.1)                              │
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
│  [2026-03-18 10:30:20] 📅 Scheduled for collection      │
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

**命令执行后显示：**

**场景 1：成功执行（表格输出）**
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

**场景 2：失败执行（错误提示）**
```
cyber-pulse> /source test invalid-id

❌ Error: Source not found

💡 Suggestion:
   • Run '/source list' to see available sources
   • Check the source ID or name

Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 1
```

**场景 3：长时间任务（进度显示）**
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

**场景 4：实时日志（流式输出）**
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

**界面行为规范：**

| 行为 | 说明 |
|------|------|
| **初始显示** | 欢迎信息 + 系统状态 + 最近活动 + 使用提示 |
| **命令执行** | 显示执行结果（表格/列表/错误信息） |
| **实时输出** | 长时间任务显示进度，日志显示实时流 |
| **错误提示** | 红色文字 ❌ + 修复建议 |
| **成功提示** | 绿色勾号 ✓ + 统计信息 |
| **命令历史** | ↑↓ 键浏览历史，Ctrl+R 搜索 |
| **自动补全** | Tab 键补全命令/参数 |

**状态栏字段：**
```
Status: 🟢 Running | API: 8000 | DB: Connected | Jobs: 2 | Memory: 256MB
```

**content get 命令详细参数：**

```bash
Usage: /content get [OPTIONS]

Options:
  --id <content-id>           # 按 ID 精确查询
  --since <timestamp>         # 起始时间（含），支持相对时间如 "2h"、"1d"
  --until <timestamp>         # 结束时间（含）
  --source <name>             # 按 Source 过滤
  --tier <T0|T1|T2>           # 按等级过滤
  --limit <number>            # 返回数量限制（默认 100，最大 1000）
  --format <json|markdown>    # 输出格式（默认 json）

Examples:
  /content get cnt_123                    # 精确查询
  /content get --since "2h"               # 最近 2 小时
  /content get --since "2026-03-18"       # 某天之后
  /content get --source "安全客" --limit 5
  /content get --tier T0 --limit 10       # 最新的 T0 内容
```

---

#### 4.6.4 配置管理

**配置文件位置：**
```bash
# 默认配置
~/.cyber-pulse/config.yaml    # 用户级
./data/config.yaml            # 项目级（与数据同目录）
```

**配置示例：**
```yaml
api:
  port: 8000
  host: "0.0.0.0"
  cors_enabled: true

database:
  url: "postgresql://user:pass@localhost:5432/cyber_pulse"
  pool_size: 10

scheduler:
  enabled: true
  timezone: "Asia/Shanghai"
  unified_interval: "1h"  # 原型阶段统一调度间隔

retention:
  item_days: 365
  content_days: 365

logging:
  level: "INFO"
  format: "json"

wechat:
  use_rsshub: true  # 是否使用 RSSHub 包装微信公众号
  rsshub_url: "http://localhost:1200"
```

**CLI 操作：**
```bash
# 查看配置
./cli config get api.port

# 修改配置
./cli config set api.port 9000

# 列出所有配置
./cli config list
```

---

### 4.7 错误处理

#### 4.7.1 恢复策略（宽松恢复）

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

#### 4.7.2 不同 Connector 的错误处理策略

**RSS Connector：**
- 失败重试：3 次，指数退避（10s, 20s, 40s）
- 连接超时：30 秒
- 解析失败：记录错误，继续下一个条目

**API Connector：**
- 失败重试：3 次，遵循 HTTP 重试规范
- 速率限制（429）：自动暂停 60 秒，继续
- 认证失败（401/403）：标记 Source 为 pending_review，通知管理员
- 连接超时：30 秒

**Web Scraper：**
- 失败重试：3 次，指数退避
- 连接超时：60 秒（网页加载慢）
- 解析失败：使用 trafilatura 的容错模式，如仍失败则记录警告
- 临时错误（500/503）：暂停 30 秒，继续

**速率限制策略：**
- 每个 Source 独立的速率限制器
- 默认：每分钟最多 10 次请求
- 可在 Source 配置中调整

**临时错误 vs 永久错误：**
- **临时错误**：网络超时、500/503、429 → 重试
- **永久错误**：401/403（认证）、404（资源不存在）、解析错误 → 标记失败，不重试

---

#### 4.7.3 错误提示机制

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

#### 4.7.4 日志格式

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

#### 4.7.5 诊断工具

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

---

## 5. 质量保障

### 5.1 日志与监控

#### 5.1.1 结构化日志

**日志级别：**

| 级别 | 说明 |
|------|------|
| DEBUG | 详细调试信息 |
| INFO | 常规操作（任务开始/结束） |
| WARNING | 警告（可选字段缺失） |
| ERROR | 错误（任务失败） |
| CRITICAL | 严重错误（系统级问题） |

**日志查看：**

```bash
# 查看最近 50 行日志
/log tail -n 50

# 实时跟踪日志
/log tail -f

# 查看错误日志（最近 1 小时）
/log errors --since "1h"

# 按 Source 过滤错误
/log errors --source "安全客"

# 搜索关键词
/log search "403 Forbidden"

# 查看日志统计
/log stats
```

---

#### 5.1.2 核心指标

**通过 CLI 查看：**

```bash
/log stats
→ 今日日志：1,245 条
   错误日志：15 条
   警告日志：23 条
```

**核心指标：**

| 指标 | 说明 |
|------|------|
| 今日采集量 | 按 Source Tier 统计 |
| 任务成功率 | 最近 24 小时 |
| 平均延迟 | 采集 → 可用 |
| 队列积压情况 | 待处理任务数 |
| API 调用统计 | 按客户端统计 |

---

### 5.2 数据校验规则

#### 5.2.1 入库校验

**Item 表：**
- ✅ `external_id` 或 `url` 唯一
- ✅ `source_id` 外键约束
- ✅ `fetched_at` 非空

**Content 表：**
- ✅ `canonical_hash` 唯一
- ✅ `first_seen_at` ≤ `last_seen_at`

---

#### 5.2.2 业务校验

**重复采集检测：**
- 同一 Source 的重复采集不会生成重复 Item（通过 `external_id` 或 `url` 唯一约束）

**跨源去重：**
- 计算 `canonical_hash`（标准化后的标题 + 正文）
- 如果已存在相同 hash，复用已有 Content

---

## 6. 部署与运维

### 6.1 单机部署方案

**环境要求：**
- ✅ Python 3.11+
- ✅ PostgreSQL 15
- ✅ Redis 7
- ✅ 磁盘空间：至少 10GB（数据 + 日志）

---

#### 6.1.1 Docker Compose 部署

**docker-compose.yml：**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: cyber_pulse
      POSTGRES_USER: cyber
      POSTGRES_PASSWORD: cyber123
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    mem_limit: 1g
    cpus: 1.0

  redis:
    image: redis:7
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    mem_limit: 512m
    cpus: 0.5

  app:
    build: .
    environment:
      DATABASE_URL: postgresql://cyber:cyber123@postgres:5432/cyber_pulse
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    mem_limit: 1g
    cpus: 2.0

volumes:
  postgres_data:
  redis_data:
```

**启动流程：**
```bash
# 🌅 早上上班
cd cyber-pulse
docker-compose up -d              # 启动所有服务
./cli server status               # 检查状态

# 🌙 下班关闭
docker-compose down               # 停止所有服务（数据保留）
```

**重启后：**
- ✅ 所有 Source 配置保留
- ✅ 所有采集历史保留
- ✅ 调度任务保留（APScheduler 从数据库恢复）
- ✅ 未完成任务可继续

---

### 6.2 配置管理

**环境变量：**

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://...` |
| `REDIS_URL` | Redis 连接字符串 | `redis://localhost:6379` |
| `API_PORT` | API 服务端口 | `8000` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

### 6.3 备份与恢复

**数据备份：**

```bash
# 备份数据库
pg_dump -U cyber cyber_pulse > backup_$(date +%Y%m%d).sql

# 备份配置文件
cp ~/.cyber-pulse/config.yaml backup_config.yaml

# 备份原始数据（可选）
tar -czf data_backup.tar.gz ./data
```

**数据恢复：**

```bash
# 恢复数据库
psql -U cyber cyber_pulse < backup_20260318.sql

# 恢复配置文件
cp backup_config.yaml ~/.cyber-pulse/config.yaml
```

---

### 6.4 硬件要求

[本次设计新增]

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

---

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

---

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

---

#### 资源占用估算

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

---

#### 网络带宽估算

**日采集 10,000 条：**
- 平均每条 50 KB (HTML + 图片)
- 日流量：~500 MB
- 月流量：~15 GB

**建议：**
- 宽带：至少 100 Mbps
- 流量：月 50 GB 以上套餐

---

#### 监控建议

```bash
# 系统资源监控
docker stats  # 实时查看容器资源

# 磁盘空间
df -h  # 查看磁盘使用

# 内存
free -h  # 查看内存使用
```

---

## 7. 未来扩展

### 7.1 生产版演进路径

| 组件 | 原型版 | 生产版 | 迁移成本 |
|------|--------|--------|---------|
| PostgreSQL | PostgreSQL 15 | CockroachDB | 低（SQL 兼容） |
| APScheduler | APScheduler | Airflow | 中（需重写 DAG） |
| Dramatiq | Dramatiq | Celery + Redis Cluster | 低（概念相同） |
| 本地文件系统 | 本地文件系统 | S3/MinIO | 低（抽象为 Storage Layer） |
| 单机部署 | `docker-compose up` | Kubernetes | 高（需容器化） |

**迁移策略：**
1. **数据库层**：CockroachDB 完全兼容 PostgreSQL 协议，只需修改连接字符串
2. **任务队列**：Celery 与 Dramatiq 概念相似（Producer/Worker），重写任务定义即可
3. **存储层**：实现统一的 Storage Interface，切换底层存储无需改业务逻辑
4. **调度器**：APScheduler 的作业定义可作为 Airflow DAG 的参考

---

### 7.2 待实现功能清单

**v2（增强版）：**
- [ ] 在线自学习（权重自动调整）
- [ ] 战略价值反馈接口（接收 cyber-nexus 数据）
- [ ] Web 界面（可选）
- [ ] 邮件通知（错误告警）

**v3（生产版）：**
- [ ] 分布式部署
- [ ] 消息队列（Kafka）
- [ ] 多租户模式
- [ ] 完整监控栈（Prometheus + Grafana）

---

### 7.3 与 cyber-nexus 的集成路径

**阶段 1：原型独立运行**
- cyber-pulse 独立运行，使用默认的维度 V 值
- 验证采集、标准化、治理流程

**阶段 2：API 对接**
- cyber-nexus 开发完成后，接入 Pull API
- cyber-nexus 开始消费增量数据

**阶段 3：反馈闭环**
- cyber-nexus 通过预留的 API 端点提供维度 V 评分
- Source Score 系统使用真实的维度 V 数据

---

## 8. 非功能需求（NFR）

[引用自 `docs/2026-03-17 cyber-pulse NFR Specification v1.0.md`]

### 8.1 性能指标

| 指标 | 目标 | 说明 |
|------|------|------|
| 采集延迟 | T0 ≤ 1 小时 | 从发布到可拉取 |
| 单任务处理时间 | ≤ 30 秒 | 采集 + 标准化 + 质量控制 |
| API 响应时间 | ≤ 100ms | P95 |
| 系统可用性 | ≥ 99% | 单机原型 |

---

### 8.2 可扩展性

- ✅ 支持 200-500 个 Source
- ✅ 日处理量 1,000-10,000 条
- ✅ 可扩展至 2,000 个 Source，50,000 条/日

---

### 8.3 安全性

#### 认证与授权
- ✅ **API Key 认证**：所有外部访问必须携带有效的 API Key
- ✅ **支持 HTTPS**：生产环境必须启用 TLS
- ✅ **访问日志记录**：记录所有 API 调用，包含 client_id、timestamp、endpoint
- ✅ **速率限制（rate_limit）**：每个 API 客户端独立的速率限制

#### 凭证管理
- ✅ **API Key 加密存储**：API Key 在数据库中使用哈希存储（bcrypt/scrypt）
- ✅ **Source 配置加密**：包含认证信息的 Source 配置（如 API Token）使用 AES 加密存储
- ✅ **环境变量管理**：敏感配置通过环境变量传递，不写入代码

#### 输入验证
- ✅ **Web 抓取内容验证**：使用白名单过滤，防止 XSS 和恶意脚本
- ✅ **Markdown 安全处理**：过滤危险的 HTML 标签和脚本
- ✅ **URL 验证**：防止 SSRF 攻击，限制可访问的域名范围
- ✅ **参数验证**：所有 API 参数使用 Pydantic 进行类型和范围验证

#### 安全审计
- ✅ **操作日志**：记录所有关键操作（Source 添加/删除、配置修改）
- ✅ **错误日志**：记录安全相关错误（认证失败、权限拒绝）
- ✅ **定期审计**：建议每月审查访问日志和异常活动

#### 原型阶段限制
- ⚠️ **默认配置**：原型阶段可能使用默认密码/密钥，生产部署前必须修改
- ⚠️ **本地部署**：单机原型默认不启用 HTTPS，生产环境必须启用

---

## 9. 附录

### 9.1 术语表

| 术语 | 说明 |
|------|------|
| **Source** | 情报来源，如"安全客"、"FreeBuf" |
| **Item** | 每次采集的原始记录 |
| **Content** | 去重后的逻辑内容实体 |
| **Connector** | 采集器，如 RSSConnector、WebScraper |
| **Curated Storage** | 通过质量控制后的标准化数据存储 |
| **Pull API** | 拉取式增量数据接口 |
| **Cursor** | 增量游标，用于标记消费位置 |
| **Source Score** | 情报来源评分系统 |
| **T0/T1/T2** | Source 分级（核心/重要/普通） |
| **iNBox** | cyber-nexus 的本地数据目录 |

---

### 9.2 参考文档索引

| 文档 | 说明 |
|------|------|
| `docs/2026-03-17 cyber-pulse 系统架构.md` | 整体架构 |
| `docs/2026-03-17 cyber-pulse Core Data Model 设计.md` | 核心数据模型 |
| `docs/2026-03-17 cyber-pulse Source Governance Model.md` | 源治理模型 |
| `docs/2026-03-17 cyber-pulse Source Score v2.2.md` | 源评分体系 |
| `docs/2026-03-17 cyber-pulse 数据服务接口规范.md` | API 规范 |
| `docs/2026-03-17 cyber-pulse NFR Specification v1.0.md` | 非功能需求 |

---

### 9.3 技术栈依赖清单

**Python 依赖（requirements.txt）：**

```txt
# Web 框架
fastapi>=0.104.0
uvicorn>=0.24.0

# 数据库
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
alembic>=1.12.0

# 调度器
apscheduler>=3.10.0

# 任务队列
dramatiq>=1.14.0
redis>=5.0.0

# HTTP 客户端
httpx>=0.25.0

# RSS 处理
feedparser>=6.0.10
feedfinder2>=0.0.4

# 正文提取
trafilatura>=1.6.0
beautifulsoup4>=4.12.0

# 媒体 API
google-api-python-client>=2.100.0

# CLI 工具
typer>=0.9.0
prompt_toolkit>=3.0.0
rich>=13.0.0
pygments>=2.15.0

# 工具库
python-dateutil>=2.8.2
pydantic>=2.0.0
```

---

## 10. 修订记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-03-18 | 老罗 | 初始版本 |
| v1.1 | 2026-03-18 | 老罗 | 整合 Q&A 澄清，修正术语，完善细节 |

**v1.1 主要更新：**
- ✅ 统一调度频率（原型阶段简化）
- ✅ Source 评分低的提醒机制
- ✅ API 响应增加 `source_score` 和 `source_quality_metrics`
- ✅ 微信公众号采集方案（RSSHub）
- ✅ 消费者实现样例（cyber-nexus）
- ✅ content get 命令增强（时间过滤、多条件）
- ✅ 交互式界面详细行为规范
- ✅ 硬件要求文档

---

**文档结束**
