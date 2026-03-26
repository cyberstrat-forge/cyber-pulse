# Issue: 部分 RSS 源只提供标题链接，无正文内容

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: 中（影响情报采集完整性）
**影响范围**: 146 个源中，约 57 个源有条目但无内容

## 测试背景

批量执行采集任务后统计：
- 总源数: 146
- 有条目的源: 89 (61%)
- 有内容的源: 82 (56%)
- 总条目数: 1857
- 总内容数: 1581

## 问题分析

### 分类 1: RSS Feed 只提供标题和链接

这些 RSS 源的结构中 `<description>` 为空或极短，无法获取正文内容：

| 源名称 | Feed URL | 条目数 | 原因 |
|--------|----------|--------|------|
| paulgraham.com | `http://www.aaronsw.com/2002/feeds/pgessays.rss` | 50 | 代理 RSS，无正文 |
| fabiensanglard.net | `https://fabiensanglard.net/rss.xml` | 50 | RSS 无正文 |
| mitchellh.com | `https://mitchellh.com/feed.xml` | 47 | RSS 无正文 |
| chadnauseam.com | `https://chadnauseam.com/rss.xml` | 40 | RSS 无正文 |
| Google Cloud Security Blog | `https://cloudblog.withgoogle.com/products/identity-security/rss/` | 20 | RSS 无正文 |
| ericmigi.com | `https://ericmigi.com/rss.xml` | 14 | RSS 无正文 |
| hey.paris | `https://hey.paris/index.xml` | 11 | RSS 无正文 |
| beej.us | `https://beej.us/blog/rss.xml` | 9 | RSS 无正文 |
| jyn.dev | `https://jyn.dev/atom.xml` | 6 | RSS 无正文 |
| Group-IB Blog | `https://www.group-ib.com/feed/blogfeed/` | 4 | RSS 无正文 |

### 分类 2: 非 blog 内容（Events/News）

这些源采集的是事件/新闻列表，非文章：

| 源名称 | Feed URL | 条目数 | 类型 |
|--------|----------|--------|------|
| Palo Alto Networks Events | `https://investors.paloaltonetworks.com/rss/events.xml` | 10 | 投资者事件 |
| CrowdStrike Holdings, Inc. Events | `https://ir.crowdstrike.com/rss/events.xml` | 10 | 投资者事件 |

### 分类 3: 部分 RSS 提供正文

这些源 RSS 提供了部分内容，但正文较短：

| 源名称 | 条目数 | 平均正文长度 | 问题 |
|--------|--------|--------------|------|
| danielwirtz.com | 9 | 29字符 | 极短 |
| chiark.greenend.org.uk/~sgtatham | 27 | 120字符 | 较短 |
| Auth0 Blog | 10 | 131字符 | 较短 |
| Anthropic Engineering Blog | 18 | 157字符 | 较短 |

## 数据库验证

```sql
-- 查看有条目但无内容的源
SELECT s.name, s.config->>'feed_url' as feed_url, COUNT(i.item_id) as items
FROM sources s
JOIN items i ON i.source_id = s.source_id
LEFT JOIN contents c ON c.content_id = i.content_id
WHERE c.content_id IS NULL
GROUP BY s.name, s.config->>'feed_url'
ORDER BY items DESC;
```

## 解决方案建议

### 方案 1: 启用全文获取

对于 RSS 只提供摘要的源，需要访问原文链接获取全文：

```python
# 在 rss_connector.py 中添加全文获取逻辑
async def _fetch_full_content(self, url: str) -> str:
    """Fetch full content from article URL when RSS content is insufficient."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30)
            full_content = trafilatura.extract(response.text)
            return full_content or ""
    except Exception:
        return ""
```

### 方案 2: 源配置标注

在源配置中标注是否需要全文获取：

```yaml
- name: "paulgraham.com"
  connector_type: rss
  config:
    feed_url: "http://www.aaronsw.com/2002/feeds/pgessays.rss"
    fetch_full_content: true  # 启用全文获取
    full_content_selector: "body"  # 可选：CSS 选择器
```

### 方案 3: 过滤非文章源

对于 Events/News 类源，建议在导入时过滤或标记为特殊类型：

```yaml
- name: "Palo Alto Networks Events"
  connector_type: rss
  config:
    feed_url: "https://investors.paloaltonetworks.com/rss/events.xml"
    content_type: event  # 标记为事件类型，非文章
    enabled: false  # 或直接禁用
```

## 相关 Issue

- `2026-03-24-content-incomplete.md`: RSS 采集内容不完整
- `2026-03-24-rss-source-accessibility.md`: 部分 RSS 源无法访问