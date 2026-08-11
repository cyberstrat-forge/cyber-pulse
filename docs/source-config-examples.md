# 情报源配置示例

本文档提供各类情报源的配置示例。

## 目录

- [RSS 源配置](#rss-源配置)
- [API 源配置](#api-源配置)
- [Web 抓取源配置](#web-抓取源配置)
- [YouTube 源配置](#youtube-源配置)
- [配置模板](#配置模板)
- [常见问题](#常见问题)

---

## RSS 源配置

### 基础 RSS 源

```bash
cyber-pulse source add "安全客" rss "https://www.anquanke.com/rss.xml" \
  --tier T1 --yes
```

### RSS 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `feed_url` | string | RSS/Atom 订阅地址（必需） |
| `timeout` | int | 请求超时时间（秒），默认 30 |
| `max_items` | int | 单次最大采集数量，默认 50 |

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
cyber-pulse source add "VirusTotal" api "https://www.virustotal.com/api/v3" \
  --tier T0 --yes
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
cyber-pulse source add "ThreatFox" api "https://threatfox-api.abuse.ch/api/v1" \
  --tier T1 --yes
```

**带分页的 API**：

```bash
cyber-pulse source add "CVE Details" api "https://cvedetails.com/api/v1/vulnerabilities" \
  --tier T1 --yes
```

### OAuth 认证配置

```bash
cyber-pulse source add "Enterprise API" api "https://api.enterprise.com/v2" \
  --tier T0 --yes
```

---

## Web 抓取源配置

### 基础 Web 源

```bash
./scripts/api.sh sources create --name "Security Blog" --type web \
  --url "https://example-security-blog.com/articles" --tier T2
```

### Web 源配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `base_url` | string | 必填 | listing 页 URL（决定收录范围，如 Perplexity `/` 5 篇 vs `/articles` 9 篇） |
| `extraction_mode` | string | `auto` | `auto`（trafilatura）/ `manual`（selectors） |
| `link_pattern` | string | 无 | 文章链接正则过滤（强烈建议配置，避免混入导航链接） |
| `link_selector` | string | 无 | 文章链接 XPath |
| `article_url_pattern` | string | 无 | 文章页 URL 判定正则（配置后完全信任） |
| `selectors` | object | 无 | manual 模式：title/content/author/date XPath |
| `pagination_type` | string | `none` | `none` / `page` |
| `pagination_param` | string | `page` | 分页查询参数名 |
| `max_pages` | int | 10 | 分页上限 |
| `user_agent` / `headers` | string/object | 内置浏览器头 | 请求伪装 |
| `render_js` | bool | `false` | httpx 失败或正文不足时降级 Playwright 渲染 |
| `min_content_length` | int | 150 | 正文质量门：提取 ≥ 阈值才入库 |

### 复杂 Web 抓取配置

```bash
# api.sh 创建 web 源，--config 透传 link_pattern 等配置
./scripts/api.sh sources create --name "Tech Security News" --type web \
  --url "https://tech-security-news.com/latest" --tier T1 \
  --config '{"link_pattern":"\\.tech-security-news\\.com/latest/","article_url_pattern":"\\.tech-security-news\\.com/latest/"}'
```

### 分页配置选项

**页码模式**（`pagination_type=page`，按 `pagination_param` 递增直到 `max_pages`）：

```json
{
  "pagination_type": "page",
  "pagination_param": "page",
  "max_pages": 10
}
```

---

## YouTube 源配置

### 前置配置：YouTube Data API Key（必需）

YouTube 频道源需要配置 **YouTube Data API v3 Key** 才能正常工作。

> ⚠️ **重要**：YouTube RSS Feed 已逐步停止服务，必须配置有效的 API Key。

#### 获取 API Key

1. **创建 Google Cloud 项目**
   ```bash
   访问: https://console.cloud.google.com/
   创建新项目或选择现有项目
   ```

2. **启用 YouTube Data API v3**
   ```bash
   访问: https://console.cloud.google.com/apis/library
   搜索 "YouTube Data API v3"
   点击 "启用"
   ```

3. **创建 API 凭据**
   ```bash
   访问: https://console.cloud.google.com/apis/credentials
   点击 "创建凭据" → "API 密钥"
   （可选）限制密钥仅允许 YouTube Data API
   ```

4. **配置 API Key**
   ```bash
   # 开发环境
   ./scripts/api.sh --env dev api-keys set YOUTUBE_API_KEY your_api_key_here

   # 生产环境
   ./scripts/api.sh --env prod api-keys set YOUTUBE_API_KEY your_api_key_here

   # 重启服务使配置生效
   ./scripts/cyber-pulse.sh restart
   ```

#### 验证 API Key

```bash
# 查看 API Keys 配置状态
./scripts/api.sh api-keys list

# 直接测试 API Key（替换 YOUR_KEY）
curl -s "https://www.googleapis.com/youtube/v3/channels?part=snippet&id=UCJ6q9Ie29ajGqKApbLqfBOg&key=YOUR_KEY" | jq '.items[0].snippet.title'
# 预期输出: "Black Hat"
```

### 基础 YouTube 源

```bash
./scripts/api.sh sources create --name "Black Hat Official" --type youtube --url "https://www.youtube.com/@BlackHatOfficialYT" --tier T1
```

### YouTube 源配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `channel_url` | string | YouTube 频道 URL（必需） |

### 支持的 URL 格式

| 格式 | 示例 |
|------|------|
| @Handle | `https://www.youtube.com/@BlackHatOfficialYT` |
| Channel ID | `https://www.youtube.com/channel/UCJ6q9Ie29ajGqKApbLqfBOg` |

### 内容说明

- **视频列表**：通过 YouTube Data API v3 获取最近 15 条视频
- **正文内容**：使用 Playwright 无头浏览器提取视频字幕，无字幕时使用视频描述
- **字幕提取**：支持自动生成字幕，隐藏浏览器窗口、静音运行

### 常见 YouTube 源示例

| 源名称 | 类型 | URL | 建议分级 |
|--------|------|-----|----------|
| Black Hat Official | youtube | https://www.youtube.com/@BlackHatOfficialYT | T1 |
| OWASP Global | youtube | https://www.youtube.com/@OWASPGLOBAL | T1 |
| DEF CON | youtube | https://www.youtube.com/@DEFCONConference | T1 |

### 故障排查

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `API_KEY_INVALID` | API Key 无效或未启用 | 检查 Google Cloud Console 配置 |
| `quotaExceeded` | API 配额耗尽 | 等待配额重置或申请更高配额 |
| `HTTP 404 (RSS)` | RSS Feed 不可用 | 必须配置有效的 API Key |

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
  "base_url": "https://example.com/articles",
  "extraction_mode": "auto",
  "link_pattern": "\\.example\\.com/articles/",
  "article_url_pattern": "\\.example\\.com/articles/",
  "pagination_type": "none",
  "pagination_param": "page",
  "max_pages": 10,
  "user_agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)",
  "render_js": false,
  "min_content_length": 150
}
```

> **manual 模式示例**（使用 `selectors` 精确定位，`extraction_mode` 必须为 `manual`）：
>
> ```json
> {
>   "extraction_mode": "manual",
>   "selectors": {
>     "title": "//h1[@class='title']",
>     "content": "//div[@class='article-body']",
>     "author": "//span[@class='author']",
>     "date": "//time/@datetime"
>   }
> }
> ```

### YouTube 源模板

```json
{
  "channel_url": "https://www.youtube.com/@ChannelHandle"
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
cyber-pulse source test src_xxx --timeout 60
```

**问题：内容为空**

某些 RSS 只提供摘要，需要通过 Web 源获取完整内容：

```bash
# 先添加 RSS 获取链接
cyber-pulse source add "Source RSS" rss "https://example.com/feed.xml" --yes

# 再添加 Web 源获取完整内容
cyber-pulse source add "Source Web" web "https://example.com/articles" --yes
```

### API 源常见问题

**问题：认证失败**

```bash
# 验证 API Key
curl -H "Authorization: Bearer your_api_key" \
     "https://api.example.com/v1/test"

# 检查配置
cyber-pulse source test src_xxx
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

**问题：采集混入导航/无关页面**

配置 `link_pattern` 限定文章链接形态，正文质量门（`min_content_length`）兜底：

```json
{
  "link_pattern": "\\.example\\.com/articles/"
}
```

**问题：链接选择器不匹配（需要精确定位文章链接）**

配置 `link_selector`（XPath）限定链接范围：

```json
{
  "link_selector": "//div[@class='post-list']//a[@href]"
}
```

**问题：内容提取不完整（auto 模式不准）**

改用 manual 模式 + `selectors` 精确定位正文：

```json
{
  "extraction_mode": "manual",
  "selectors": {
    "content": "//div[@class='article-body']"
  }
}
```

**问题：SPA 站点（React/Next.js）正文为空**

开启 JS 渲染兜底（Playwright 渲染后重抓）：

```json
{
  "render_js": true
}
```

**问题：网站禁止爬虫**

设置 `user_agent` 或自定义 `headers`：

```json
{
  "user_agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)",
  "headers": {
    "Accept-Language": "en-US,en;q=0.9"
  }
}
```

> **已知限制**：web 源的文章发布日期取自页面元数据（`metadata.date`），部分站点返回页面生成日期而非真实发布时间（存在偏差）。
> 系统仅做轻量校验（明显未来日期回退收录时间）。精确场景请使用 manual 模式的 `selectors.date` 选择器自行定位。

---

## 测试与验证

### 测试情报源

```bash
# 测试连接
cyber-pulse source test src_xxx --timeout 60

# 手动运行采集
cyber-pulse job run src_xxx

# 查看采集结果
cyber-pulse content list --source-id src_xxx --limit 10
```

### 调试模式

```bash
# 设置日志级别
cyber-pulse config set log_level DEBUG

# 运行采集并查看详细日志
cyber-pulse job run src_xxx

# 查看日志
cyber-pulse log search "src_xxx" --level DEBUG
```

### 验证内容质量

```bash
# 查看源统计
cyber-pulse source stats --source-id src_xxx

# 查看错误诊断
cyber-pulse diagnose errors --source src_xxx
```