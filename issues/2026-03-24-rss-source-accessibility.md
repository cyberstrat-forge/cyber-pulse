# Issue: 部分导入的 RSS 源无法访问

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: 中（影响情报采集完整性）
**影响范围**: OPML 导入的 146 个源中，约 12 个无法访问

## 测试方法

使用 `curl` 测试 RSS feed URL 的 HTTP 响应状态码：
- HTTP 200: 源可正常访问
- HTTP 403/404: 源拒绝访问或不存在
- HTTP 000: 连接超时或网络错误

## 失败源清单

### 🔴 完全无法访问 (HTTP 403/404)

| 源名称 | Feed URL | HTTP 状态 | 失败原因 |
|--------|----------|-----------|----------|
| Anthropic Press Releases | `https://feedproxy.feedly.com/5b36e586-...` | 403 | Feedly 代理禁止直接访问 |
| Deeplearning.ai | `https://rsshub.app/deeplearning/thebatch` | 403 | RSSHub 反爬限制 |
| OpenAI | `https://blog.openai.com/rss/` | 000 | 域名已迁移至 openai.com |
| karpathy | `https://karpathy.bearblog.dev/feed/` | 403 | Bear Blog 反爬限制 |
| Dark Reading | `http://www.darkreading.com/rss/all.xml` | 403 | 网站反爬限制 |
| Microsoft Security | `http://blogs.technet.com/mmpc/rss.xml` | 404 | RSS 地址已废弃 |
| Sysdig | `http://draios.com/feed/` | 301 | 旧域名重定向 |
| FireEye | `http://www.fireeye.com/blog/feed` | 530 | 服务不可用 |
| CSO Online | `http://www.csoonline.com/index.rss` | 404 | RSS 地址已废弃 |
| tedunangst.com | `https://www.tedunangst.com/flak/rss` | 000 | 连接失败 |
| rachelbythebay.com | `https://rachelbythebay.com/w/atom.xml` | 000 | 连接失败 |
| herman.bearblog.dev | `https://herman.bearblog.dev/feed/` | 403 | Bear Blog 反爬限制 |

### 🟡 需要更新 URL

| 源名称 | 当前 URL | 建议更新 |
|--------|----------|----------|
| OpenAI | `https://blog.openai.com/rss/` | 迁移到 `https://openai.com/blog/rss/` |
| Microsoft Security | `http://blogs.technet.com/mmpc/rss.xml` | 更新到 `https://www.microsoft.com/en-us/security/blog/feed/` |
| Sysdig | `http://draios.com/feed/` | 更新到 `https://www.sysdig.com/feed/` |

## 失败原因分类

### 1. RSS 代理服务限制 (403 Forbidden)

**影响源**:
- Anthropic Press Releases (feedproxy.feedly.com)
- Deeplearning.ai (rsshub.app)
- karpathy (bearblog.dev)
- herman.bearblog.dev

**原因**:
- Feedly 的 `feedproxy.feedly.com` 是付费服务代理，禁止未授权访问
- RSSHub 有反爬虫限制，需要配置专用 instance
- Bear Blog 平台有严格的反爬措施

**解决方案**:
```yaml
# 方案 1: 使用原始 RSS 地址
- name: Anthropic Press Releases
  config:
    feed_url: "https://www.anthropic.com/news?subjects=announcements&format=rss"

# 方案 2: 自建 RSSHub 实例
- name: Deeplearning.ai
  config:
    feed_url: "https://your-rsshub-instance.com/deeplearning/thebatch"

# 方案 3: 使用 Web Scraper 替代
- name: karpathy
  connector_type: web
  config:
    base_url: "https://karpathy.bearblog.dev/"
```

### 2. RSS 地址已废弃 (404 Not Found)

**影响源**:
- Microsoft Security (blogs.technet.com)
- CSO Online (index.rss)

**原因**: 网站已迁移，旧 RSS 地址不再可用

**解决方案**: 更新到新地址
```yaml
- name: Microsoft Security Blog
  config:
    feed_url: "https://www.microsoft.com/en-us/security/blog/feed/"

- name: CSO Online
  config:
    feed_url: "https://www.csoonline.com/feed/"
```

### 3. 域名迁移 (301 Redirect)

**影响源**: Sysdig (draios.com)

**解决方案**: 更新到新域名
```yaml
- name: Sysdig Blog
  config:
    feed_url: "https://www.sysdig.com/feed/"
```

### 4. 连接失败 (HTTP 000)

**影响源**:
- OpenAI (blog.openai.com)
- tedunangst.com
- rachelbythebay.com

**原因**:
- 域名已迁移 (OpenAI)
- 服务器不稳定或网络问题

**解决方案**:
```yaml
- name: OpenAI
  config:
    feed_url: "https://openai.com/blog/rss.xml"
```

## 测试统计

| 类别 | 数量 |
|------|------|
| 测试源总数 | 35 + 32 + 66 = 133 |
| 成功访问 | 27 + 32 + 63 = 122 |
| 访问失败 | 8 + 1 + 3 = 12 |
| 成功率 | 91% |

## 建议操作

### P0 - 立即修复

更新已废弃/迁移的 RSS 地址：

```sql
-- 更新 OpenAI 源
UPDATE sources
SET config = jsonb_set(config, '{feed_url}', '"https://openai.com/blog/rss.xml"')
WHERE name = 'OpenAI';

-- 更新 Microsoft Security 源
UPDATE sources
SET config = jsonb_set(config, '{feed_url}', '"https://www.microsoft.com/en-us/security/blog/feed/"')
WHERE name = 'Microsoft Security Blog';

-- 更新 Sysdig 源
UPDATE sources
SET config = jsonb_set(config, '{feed_url}', '"https://www.sysdig.com/feed/"')
WHERE name = 'Sysdig Blog';
```

### P1 - 源配置增强

1. **添加源测试功能**
   - 在导入时自动测试源可访问性
   - 标记无法访问的源为 `INACTIVE`

2. **支持备用 URL**
   ```yaml
   - name: Anthropic Press Releases
     config:
       feed_url: "https://feedproxy.feedly.com/..."
       fallback_url: "https://www.anthropic.com/news/rss"
   ```

3. **RSSHub 集成**
   - 支持配置自定义 RSSHub 实例
   - 自动处理 RSSHub 特有的参数

### P2 - 长期改进

1. **定期源健康检查**
   - 定时任务检查源可访问性
   - 自动禁用长期不可访问的源

2. **多协议支持**
   - 对于禁止 RSS 访问的站点，支持 Web Scraper 备选

## 验证命令

```bash
# 测试单个源
docker compose -f deploy/docker-compose.yml exec api cyber-pulse source test <source_id>

# 批量测试所有源（建议新增此功能）
docker compose -f deploy/docker-compose.yml exec api cyber-pulse source test --all
```