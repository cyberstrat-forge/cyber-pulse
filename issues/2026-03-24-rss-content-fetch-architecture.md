# Discussion: RSS 内容采集架构改进方案

**讨论日期**: 2026-03-24
**状态**: 待深入讨论
**后续步骤**: 使用 superpowers:brainstorming 开展专题讨论

---

## 问题背景

### RSS 的"信任陷阱"

RSS 表面上是个标准，但实际上各网站实现千差万别：

**理想中的 RSS:**
```xml
<item>
  <title>文章标题</title>
  <description>文章摘要</description>
  <content:encoded>完整正文</content:encoded>
  <link>原文链接</link>
</item>
```

**现实中的 RSS:**
- 有的只有 title，没有 description
- 有的 title 和 description 一样
- 有的 description 是摘要，有的是全文
- 有的用 content:encoded，有的不用
- 有的正文在 CDATA 里，有的直接放
- 有的编码是 UTF-8，有的是 GBK

### 核心问题

**我们太"信任"RSS 会提供完整内容。**

当前架构是"被动接收"模式，RSS 给什么就存什么，给得不够就放弃。

---

## 已发现的问题清单

| 问题 | 影响范围 | 严重程度 |
|------|----------|----------|
| CLI JSON 中文 Unicode 转义 | 100% 中文内容 | P1 |
| 标题=正文（Anthropic Research） | 18条 (1.1%) | P0 |
| RSS 只有标题链接，无正文 | 57个源 (31%) | P1 |
| RSS 源无法访问 | 12个源 (8%) | P1 |

---

## 改进方向：从被动到主动

### 当前架构（被动）

```
RSS Feed → 解析 → 存储标准化 → 完成
              ↓
         (如果内容不够，就放弃了)
```

### 目标架构（主动）

```
RSS Feed → 解析 → 内容够吗？ → 够 → 存储标准化 → 完成
              ↓              ↓
             不够        访问原文链接
                              ↓
                        提取全文内容
                              ↓
                         存储标准化
```

---

## 初步方案：三层防御策略

### 第一层：RSS 源配置增强

给每个源加"性格档案"，告诉系统怎么处理它：

```yaml
sources:
  # 类型 A：RSS 提供完整内容
  - name: "字节跳动安全中心"
    config:
      feed_url: "https://..."
      content_mode: full        # RSS 已有全文
      quality_check: true

  # 类型 B：RSS 只有摘要，需访问原文
  - name: "Anthropic Research"
    config:
      feed_url: "https://..."
      content_mode: summary     # RSS 只有摘要
      fetch_full: true          # 需要访问原文
      title_parser: compound    # 标题格式特殊

  # 类型 C：RSS 只有标题链接
  - name: "paulgraham.com"
    config:
      feed_url: "https://..."
      content_mode: link_only   # RSS 只有链接
      fetch_full: true          # 必须访问原文
      article_selector: "body"  # 正文选择器

  # 类型 D：需要特殊处理
  - name: "Deeplearning.ai"
    config:
      feed_url: "https://rsshub.app/..."
      content_mode: summary
      fetch_full: true
      headers:
        User-Agent: "Mozilla/5.0..."
      proxy: "http://..."
```

### 第二层：智能内容获取器

```python
class ContentFetcher:
    """智能内容获取器 - 根据源配置选择策略"""

    async def fetch(self, source: Source, entry: RSSEntry) -> str:
        # 策略 1：RSS 内容已足够
        if source.content_mode == "full":
            return entry.content

        # 策略 2：检查后决定
        if source.content_mode == "summary":
            content = entry.content or entry.summary
            if self._is_sufficient(content):
                return content

        # 策略 3：访问原文
        return await self._fetch_from_url(entry.url, source)
```

### 第三层：质量门禁 + 自动修复

```python
class QualityGate:
    """质量门禁 - 检测并尝试修复问题"""

    def check_and_repair(self, content: Content) -> Content:
        issues = []

        # 检测：标题=正文
        if content.title == content.body:
            issues.append("title_eq_body")
            # 尝试智能解析标题

        # 检测：正文过短
        if len(content.body) < 100:
            issues.append("body_too_short")

        # 检测：非文章内容
        if self._looks_like_navigation(content.url):
            issues.append("not_article")

        return content
```

---

## 实施路径

### Step 1: 快速修复（1-2天）

- [ ] 修复 JSON Unicode 问题
- [ ] 给源添加 content_mode 配置字段
- [ ] 对已知问题源特殊处理

### Step 2: 核心能力（1-2周）

- [ ] 实现 ContentFetcher 全文获取
- [ ] 实现质量门禁检查
- [ ] 添加源配置管理界面
- [ ] 采集失败自动重试

### Step 3: 智能化（长期）

- [ ] 自动检测源类型
- [ ] 正文提取准确性优化
- [ ] 代理/反爬策略库
- [ ] 质量趋势监控

---

## 待讨论的问题

### 架构决策

1. **content_mode 如何自动检测？**
   - 完全自动 vs 半自动（用户确认）
   - 检测算法的准确率要求

2. **全文获取的时机？**
   - 采集时同步获取（增加延迟）
   - 后台异步任务（增加复杂度）

3. **失败处理策略？**
   - 重试机制
   - 降级方案（使用 RSS 摘要）
   - 用户通知

### 技术选型

4. **正文提取工具选择？**
   - trafilatura（当前使用）
   - newspaper3k
   - 自研 + LLM 辅助

5. **反爬虫应对？**
   - 代理池
   - User-Agent 轮换
   - 请求频率控制

### 产品设计

6. **如何展示采集质量？**
   - CLI 统计命令
   - API 质量指标
   - 监控告警

7. **用户如何参与？**
   - 配置界面
   - 质量反馈
   - 源推荐/禁用

---

## 相关 Issue 文档

- `2026-03-24-cli-json-unicode-escape.md`
- `2026-03-24-content-incomplete.md`
- `2026-03-24-content-quality-report.md`
- `2026-03-24-rss-no-content.md`
- `2026-03-24-rss-source-accessibility.md`

---

## 一句话总结

**不要指望 RSS 给你什么，而是建立"获取能力"，确保无论 RSS 给什么，你都能拿到完整内容。**