# 情报源配置示例

本文档提供各类情报源的配置示例。

## 目录

- [RSS 源配置](#rss-源配置)
- [API 源配置](#api-源配置)
- [Web 抓取源配置](#web-抓取源配置)
- [配置模板](#配置模板)
- [常见问题](#常见问题)

---

## RSS 源配置

### 基础 RSS 源

```bash
cyberpulse source add "安全客" rss \
  --tier T1 \
  --url "https://www.anquanke.com/rss.xml" \
  --schedule "0 */6 * * *"
```

### RSS 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `feed_url` | string | RSS/Atom 订阅地址（必需） |
| `timeout` | int | 请求超时时间（秒），默认 30 |
| `max_items` | int | 单次最大采集数量，默认 50 |

### 带配置的 RSS 源

```bash
cyberpulse source add "FreeBuf" rss \
  --tier T1 \
  --url "https://www.freebuf.com/feed" \
  --config '{"timeout": 60, "max_items": 100}' \
  --schedule "0 */4 * * *"
```

### 常见 RSS 源示例

| 源名称 | 类型 | URL | 建议分级 |
|--------|------|-----|----------|
| 安全客 | rss | https://www.anquanke.com/rss.xml | T1 |
| FreeBuf | rss | https://www.freebuf.com/feed | T1 |
| Hacker News | rss | https://hnrss.org/frontpage | T0 |
| The Hacker News | rss | https://feeds.feedburner.com/TheHackersNews | T1 |
| Security Week | rss | https://www.securityweek.com/rss.xml | T2 |
| Krebs on Security | rss | https://krebsonsecurity.com/feed/ | T0 |
| SANS ISC | rss | https://isc.sans.edu/rssfeed.xml | T1 |

---

## API 源配置

### 基础 API 源

```bash
cyberpulse source add "VirusTotal" api \
  --tier T0 \
  --url "https://www.virustotal.com/api/v3" \
  --config '{"api_key": "your_api_key", "endpoint": "/intelligence/files"}' \
  --schedule "0 */2 * * *"
```

### API 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `api_key` | string | API 认证密钥 |
| `endpoint` | string | API 端点路径 |
| `method` | string | HTTP 方法，默认 GET |
| `headers` | object | 自定义请求头 |
| `params` | object | 查询参数 |
| `timeout` | int | 请求超时时间（秒） |
| `rate_limit` | int | 每分钟请求限制 |
| `pagination` | object | 分页配置 |

### REST API 配置示例

**带认证的 API**：

```bash
cyberpulse source add "ThreatFox" api \
  --tier T1 \
  --url "https://threatfox-api.abuse.ch/api/v1" \
  --config '{
    "api_key": "your_api_key",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    },
    "params": {
      "query": "get_iocs",
      "days": 1
    }
  }' \
  --schedule "0 6 * * *"
```

**带分页的 API**：

```bash
cyberpulse source add "CVE Details" api \
  --tier T1 \
  --url "https://cvedetails.com/api/v1/vulnerabilities" \
  --config '{
    "api_key": "your_api_key",
    "pagination": {
      "type": "offset",
      "param": "offset",
      "limit_param": "limit",
      "limit": 100
    }
  }' \
  --schedule "0 0 * * *"
```

### OAuth 认证配置

```bash
cyberpulse source add "Enterprise API" api \
  --tier T0 \
  --url "https://api.enterprise.com/v2" \
  --config '{
    "auth_type": "oauth2",
    "oauth": {
      "token_url": "https://auth.enterprise.com/token",
      "client_id": "your_client_id",
      "client_secret": "your_client_secret",
      "scope": "read"
    }
  }' \
  --schedule "0 */3 * * *"
```

---

## Web 抓取源配置

### 基础 Web 源

```bash
cyberpulse source add "Security Blog" web \
  --tier T2 \
  --url "https://example-security-blog.com/articles" \
  --config '{"selector": "article.post", "link_selector": "a.title"}' \
  --schedule "0 8 * * *"
```

### Web 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `selector` | string | 文章列表 CSS 选择器 |
| `link_selector` | string | 链接 CSS 选择器 |
| `title_selector` | string | 标题 CSS 选择器 |
| `content_selector` | string | 正文 CSS 选择器 |
| `date_selector` | string | 日期 CSS 选择器 |
| `author_selector` | string | 作者 CSS 选择器 |
| `pagination` | object | 分页配置 |
| `exclude_selectors` | array | 排除元素选择器 |
| `timeout` | int | 请求超时时间（秒） |
| `user_agent` | string | 自定义 User-Agent |

### 复杂 Web 抓取配置

```bash
cyberpulse source add "Tech Security News" web \
  --tier T1 \
  --url "https://tech-security-news.com/latest" \
  --config '{
    "selector": "div.article-card",
    "link_selector": "h2 a",
    "title_selector": "h2",
    "content_selector": "div.article-content",
    "date_selector": "time.pubdate",
    "author_selector": "span.author-name",
    "pagination": {
      "type": "next_link",
      "selector": "a.next-page"
    },
    "exclude_selectors": [
      "div.advertisement",
      "aside.sidebar",
      "footer"
    ],
    "timeout": 60
  }' \
  --schedule "0 */4 * * *"
```

### 分页配置选项

**下一页链接模式**：

```json
{
  "pagination": {
    "type": "next_link",
    "selector": "a.next-page"
  }
}
```

**页码模式**：

```json
{
  "pagination": {
    "type": "page_number",
    "param": "page",
    "max_pages": 10
  }
}
```

**无限滚动模式**：

```json
{
  "pagination": {
    "type": "scroll",
    "api_url": "https://example.com/api/articles",
    "param": "offset"
  }
}
```

---

## 配置模板

### RSS 源模板

```json
{
  "feed_url": "https://example.com/feed.xml",
  "timeout": 30,
  "max_items": 50
}
```

### API 源模板

```json
{
  "api_key": "your_api_key",
  "endpoint": "/v1/data",
  "method": "GET",
  "headers": {
    "Accept": "application/json"
  },
  "params": {
    "limit": 100
  },
  "timeout": 30,
  "rate_limit": 60,
  "pagination": {
    "type": "cursor",
    "param": "cursor"
  }
}
```

### Web 源模板

```json
{
  "selector": "article",
  "link_selector": "a.title",
  "title_selector": "h1",
  "content_selector": "div.content",
  "date_selector": "time",
  "author_selector": "span.author",
  "exclude_selectors": ["div.ads", "nav"],
  "timeout": 30
}
```

---

## 常见问题

### RSS 源常见问题

**问题：RSS 解析失败**

```bash
# 检查 RSS 格式
curl -s "https://example.com/feed.xml" | head -50

# 测试连接
cyberpulse source test src_xxx --timeout 60
```

**问题：内容为空**

某些 RSS 只提供摘要，需要通过 Web 源获取完整内容：

```bash
# 先添加 RSS 获取链接
cyberpulse source add "Source RSS" rss \
  --url "https://example.com/feed.xml"

# 再添加 Web 源获取完整内容
cyberpulse source add "Source Web" web \
  --url "https://example.com/articles"
```

### API 源常见问题

**问题：认证失败**

```bash
# 验证 API Key
curl -H "Authorization: Bearer your_api_key" \
     "https://api.example.com/v1/test"

# 检查配置
cyberpulse source test src_xxx
```

**问题：请求频率限制**

在配置中设置 `rate_limit`：

```json
{
  "api_key": "xxx",
  "rate_limit": 30
}
```

### Web 源常见问题

**问题：选择器不匹配**

```bash
# 调试选择器
# 使用浏览器开发者工具检查页面结构
# 或使用 curl 获取页面源码分析
curl -s "https://example.com/articles" | grep -o '<article[^>]*>'
```

**问题：内容提取不完整**

调整 `content_selector` 或添加 `exclude_selectors`：

```json
{
  "content_selector": "div.article-body",
  "exclude_selectors": [
    "div.related-articles",
    "div.comments"
  ]
}
```

**问题：网站禁止爬虫**

设置 `user_agent` 或添加延迟：

```json
{
  "user_agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)",
  "delay": 1
}
```

---

## 测试与验证

### 测试情报源

```bash
# 测试连接
cyberpulse source test src_xxx --timeout 60

# 手动运行采集
cyberpulse job run src_xxx

# 查看采集结果
cyberpulse content list --source-id src_xxx --limit 10
```

### 调试模式

```bash
# 设置日志级别
cyberpulse config set log_level DEBUG

# 运行采集并查看详细日志
cyberpulse job run src_xxx

# 查看日志
cyberpulse log search "src_xxx" --level DEBUG
```

### 验证内容质量

```bash
# 查看源统计
cyberpulse source stats --source-id src_xxx

# 查看错误诊断
cyberpulse diagnose errors --source src_xxx
```