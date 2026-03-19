# Connector 体系

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 内置 Connector

**技术选型：**

| Connector | 开源库 | 说明 |
|-----------|--------|------|
| **RSSConnector** | `feedparser` + `feedfinder2` | RSS/Atom 解析，自动发现 RSS 地址 |
| **APIConnector** | `httpx` | 通用 API 采集，支持认证、分页 |
| **WebScraper** | `httpx` + `trafilatura` | 网页抓取 + 正文提取 |
| **MediaAPIConnector** | `google-api-python-client` | YouTube/Twitter 等媒体平台 |

**CLI 配置示例：**

### 1. RSS Connector
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

### 2. API Connector
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

### 3. Web Scraper
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

### 4. Media API (YouTube)
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

## 微信公众号采集方案

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

## 外部服务集成（可选扩展）

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