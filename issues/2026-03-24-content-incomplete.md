# Issue: RSS 采集内容不完整且标题正文混淆

## 问题概述

**发现日期**: 2026-03-24
**严重程度**: 高（影响数据质量和可用性）
**影响范围**: RSS 采集的内容，特别是微信公众号和 Anthropic Research

## 问题复现

### 案例 1：Anthropic Research（标题正文完全相同）

```bash
docker compose -f deploy/docker-compose.yml exec api cyber-pulse content get cnt_20260324114919_f2bfef59
```

**输出**：
```json
{
  "normalized_title": "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides...",
  "normalized_body": "AlignmentDec 18, 2024Alignment faking in large language modelsThis paper provides...",
}
```

**问题**：
- `normalized_title` 和 `normalized_body` 完全相同
- 标题中混合了：分类(Alignment) + 日期(Dec 18, 2024) + 标题 + 摘要
- 论文正文完全没有获取

### 案例 2：微信公众号（内容极短）

```bash
docker compose -f deploy/docker-compose.yml exec api cyber-pulse content get cnt_20260324121106_bf53f2ad
```

**输出**：
```json
{
  "normalized_title": "看点揭晓 | Agent全生命周期安全如何打造？",
  "normalized_body": "本周见的 2025-12-15 19:04 北京\n\nAgent安全防护指南\n\n直播通道点击原文链接",
  "content_completeness": 0.2
}
```

**问题**：`normalized_body` 只有 49 个字符，内容明显不完整。

## 根因分析

### 数据对比

| content_id | title | raw_len | body_len | completeness | 问题 |
|------------|-------|---------|----------|--------------|------|
| cnt_...bf53f2ad | Agent全生命周期安全 | 2944 | **49** | 0.2 | ⚠️ 严重不完整 |
| cnt_...75b9983f | 校招宣讲预告 | 978 | **19** | 0.2 | ⚠️ 严重不完整 |
| cnt_...7ffd4d55 | ByteSRC AI业务收录 | 18211 | 2304 | 1.0 | ✅ 正常 |
| cnt_...ed46f4d7 | 火山引擎金融大模型 | 32879 | 4114 | 1.0 | ✅ 正常 |

### 问题原因

**核心问题：RSS 采集只获取摘要，未获取全文**

1. **数据来源问题**
   - 所有受影响内容均来自微信公众号（通过 `wechat2rss` 服务转 RSS）
   - URL 格式：`https://mp.weixin.qq.com/s?__biz=...`

2. **RSS Feed 限制**
   - 微信公众号 RSS（wechat2rss）只提供文章摘要/预览
   - 原始 `raw_content` 本身就不完整（只有 2944 字符）
   - 主要内容是一张活动宣传图片和简短描述

3. **标准化处理过程**
   - `trafilatura.extract()` 使用 `favor_precision=True` 参数
   - 对于图片为主、文字较少的内容，提取结果会更少
   - 大量 HTML 标签被清理，只保留纯文本

### 原始内容示例

```html
<p><span>本周见的</span> <span>2025-12-15 19:04</span>...</p>
<p><img src="https://wechat2rss.xlab.app/img-proxy/..." /></p>
<p>Agent安全防护指南</p>
<!-- 大量样式和图片 -->
<p><span>直播通道点击原文链接</span></p>
```

文章主要内容是一张活动海报图片，真正的文字内容本身就很少。

## 涉及代码

### 数据采集

- **文件**: `src/cyberpulse/services/rss_connector.py`
- **方法**: `_get_content()` (第 219-239 行)
- **逻辑**:
  1. 优先取 `entry.content` 字段
  2. 回退到 `entry.summary` 或 `entry.description`
  3. **问题**：RSS feed 本身只提供摘要，无法获取全文

### 内容标准化

- **文件**: `src/cyberpulse/services/normalization_service.py`
- **方法**: `_extract_markdown()` (第 84-117 行)
- **逻辑**:
  ```python
  markdown = trafilatura.extract(
      raw_content,
      url=url,
      output_format="markdown",
      include_comments=False,
      include_tables=True,
      favor_precision=True,  # 精确模式可能丢失部分内容
  )
  ```

### 质量评估

- **文件**: `src/cyberpulse/services/quality_gate_service.py`
- **方法**: `_calculate_content_completeness()` (第 296-319 行)
- **评分逻辑**:
  - body >= 500 字符: 1.0
  - body >= 200 字符: 0.7
  - body >= 50 字符: 0.4
  - body < 50 字符: 0.2

## 解决方案建议

### 方案 1：RSS 采集增强（推荐）

#### 1.1 检测并获取全文

```python
# 在 rss_connector.py 中
async def _fetch_full_content(self, url: str, content: str) -> str:
    """Fetch full content if RSS content is incomplete."""
    if len(content) < 200:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True, timeout=30)
                full_content = trafilatura.extract(response.text)
                return full_content or content
        except Exception:
            pass
    return content
```

#### 1.2 智能标题解析

针对 Anthropic Research 等特殊格式：

```python
def _parse_compound_title(self, title: str) -> tuple[str, str, str]:
    """Parse compound title like 'AlignmentDec 18, 2024Alignment faking...'"""
    # 使用正则或 LLM 提取：分类、日期、真正标题、摘要
    pass
```

### 方案 2：质量门禁增强

在 `quality_gate_service.py` 中添加检查：

```python
def _validate_content_quality(self, norm: NormalizationResult) -> List[str]:
    """Additional content quality checks."""
    errors = []

    # 检测标题与正文相同
    if norm.normalized_title == norm.normalized_body:
        errors.append("Title and body are identical")

    # 检测正文过短
    if len(norm.normalized_body) < 100:
        errors.append("Body content too short")

    # 检测标题格式异常（包含日期模式）
    if re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', norm.normalized_title):
        errors.append("Title contains date - possible parsing issue")

    return errors
```

### 方案 3：数据模型扩展

```python
class Content(Base):
    # 现有字段...
    normalized_body = Column(Text)
    full_content = Column(Text, nullable=True)  # 异步获取的全文
    content_completeness = Column(Float)

    # 新增字段
    needs_full_fetch = Column(Boolean, default=False)  # 标记需要获取全文
    title_parsed = Column(Boolean, default=True)  # 标题是否已正确解析
```

### 方案 4：源配置标注

```yaml
- name: "Anthropic Research"
  connector_type: rss
  config:
    feed_url: "https://..."
  content_type: summary  # 标注为摘要型
  title_format: compound  # 标注标题格式为复合型
  full_content_fetch: true  # 启用全文获取
```

### 方案 5：API 层面过滤

在 CLI 和 API 中过滤或标记低质量内容：

```python
# 在 content get 命令中
if content.content_completeness < 0.5:
    console.print("[yellow]⚠️ Warning: Content may be incomplete[/yellow]")
```

## 影响评估

### 按来源统计

| 来源 | 总数 | 标题=正文 | 正文<100字 | 问题类型 |
|------|------|-----------|------------|----------|
| Anthropic Research | 18 | **18 (100%)** | 14 (78%) | 标题正文混淆 + 内容不完整 |
| 字节跳动安全中心 | 多条 | 0 | 多条 | 内容不完整 |

### 按问题类型统计

| 问题类型 | 描述 | 影响 |
|----------|------|------|
| **标题正文相同** | RSS feed 中 title 和 summary 相同，标准化后未分离 | 18 条 |
| **内容极短** | RSS 只提供摘要，未获取全文 | 多条 |
| **格式混杂** | 标题中混合分类、日期、标题、摘要 | 18 条 |

## 根因深度分析

### 问题 1：RSS Feed 数据结构问题

**Anthropic Research RSS Feed 特点**：
```
<item>
  <title>AlignmentDec 18, 2024Alignment faking in large language models...</title>
  <description>AlignmentDec 18, 2024Alignment faking in large language models...</description>
  <link>https://www.anthropic.com/research/alignment-faking</link>
</item>
```

**问题**：
- `<title>` 和 `<description>` 内容完全相同
- 标题中混合了多个字段（分类 + 日期 + 标题 + 摘要）
- 没有独立的正文字段

### 问题 2：标准化逻辑未处理此场景

当前 `_extract_markdown()` 使用 trafilatura 提取内容，但对于：
1. 只有摘要的 RSS 内容，提取结果与标题相同
2. 没有智能分离标题中的混杂信息

### 问题 3：缺乏内容质量校验

当前质量检查只验证 `normalized_body` 非空，未检测：
- 标题与正文是否相同
- 正文是否过于简短
- 标题格式是否异常

## 验证方法

```bash
# 查询标题与正文相同的内容
docker compose -f deploy/docker-compose.yml exec postgres psql -U cyberpulse -d cyberpulse -c "
SELECT c.content_id, s.name as source, LENGTH(c.normalized_body) as body_len
FROM contents c
JOIN items i ON i.content_id = c.content_id
JOIN sources s ON i.source_id = s.source_id
WHERE c.normalized_title = c.normalized_body
ORDER BY body_len;
"

# 查询低完整度内容
docker compose -f deploy/docker-compose.yml exec postgres psql -U cyberpulse -d cyberpulse -c "
SELECT content_id, normalized_title, LENGTH(normalized_body) as body_len, content_completeness
FROM contents c
JOIN items i ON i.content_id = c.content_id
WHERE i.content_completeness < 0.5
ORDER BY body_len;
"

# 统计各源的数据质量
docker compose -f deploy/docker-compose.yml exec postgres psql -U cyberpulse -d cyberpulse -c "
SELECT s.name,
       COUNT(*) as total,
       SUM(CASE WHEN c.normalized_title = c.normalized_body THEN 1 ELSE 0 END) as title_eq_body,
       AVG(i.content_completeness) as avg_completeness
FROM contents c
JOIN items i ON i.content_id = c.content_id
JOIN sources s ON i.source_id = s.source_id
GROUP BY s.name
ORDER BY avg_completeness;
"
```

## 相关 Issue

- #1: CLI JSON 输出中文显示为 Unicode 转义序列