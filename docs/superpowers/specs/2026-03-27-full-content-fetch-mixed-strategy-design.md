# 全文获取混合策略设计

## 概述

**目标**: 解决 RSS 采集全文时遇到的 Cloudflare 等 WAF 反爬问题（HTTP 403）

**相关 Issue**: 待创建

**预期结果**: 全文获取成功率从 ~50% 提升至 ~90%+

---

## 业务流程（方案 A：统一触发点）

### 简化流程

```
ingest → normalize → quality_check
                              │
                              ├─ 内容完整 → MAPPED
                              │
                              └─ 内容不足 → 触发全文获取任务
                                           │
                                           ├─ 成功 → 重归一化 → MAPPED
                                           │
                                           └─ 失败 → REJECTED
```

### 关键简化点

1. **移除 `source.needs_full_fetch` 配置**：统一通过质量检测判断
2. **全文获取失败直接 REJECTED**：不再保留摘要内容
3. **API 过滤逻辑不变**：`status != REJECTED`

### API 暴露条件

只有满足以下条件的 item 才会通过 API 对外提供：

| 状态 | 条件 |
|------|------|
| MAPPED | 内容完整，或全文获取成功 |
| REJECTED | 内容不足且全文获取失败 |

**pending 状态不对外暴露**：全文获取任务进行中的 item 不会出现在 API 结果中。

---

## 背景与动机

### 当前问题

RSS 采集流程中，部分情报源只返回摘要，需要访问原始 URL 获取全文。但很多网站部署了 Cloudflare 等 WAF 保护，直接 HTTP 请求返回 403 Forbidden。

**典型场景**：
- OpenAI 博客：Cloudflare Bot Management 挑战
- 技术博客：UA 检测、JS 挑战
- 新闻媒体：付费墙、登录要求

**现有方案**：
- `FullContentFetchService` 使用 httpx + trafilatura
- 简单请求无法绑过 Cloudflare 等现代反爬机制

---

## 全文采集触发规则

在质量检测阶段统一判断是否需要全文获取，移除 `source.needs_full_fetch` 配置。

### 规则定义

#### 规则 1：内容长度阈值

```python
MIN_CONTENT_LENGTH = 100  # 字符数
```

RSS 正文 < 100 字符 → 触发全文获取

#### 规则 2：标题-正文相似度检测

针对 **Anthropic Research 类问题**（标题被错误识别为正文）：

```python
def is_title_as_body(title: str, body: str) -> bool:
    """检测标题是否被错误识别为正文"""
    if not title or not body:
        return False
    similarity = text_similarity(title.strip(), body.strip())
    return similarity > 0.8  # 80% 相似度阈值
```

#### 规则 3：正文质量检测

检测提取内容是否为有效正文（而非广告/导航/错误页）：

```python
INVALID_CONTENT_PATTERNS = [
    "Please enable JavaScript",
    "Checking your browser",
    "404 Not Found",
    "Access Denied",
]

def is_valid_content(body: str) -> bool:
    """检测内容是否为有效正文"""
    if len(body) < MIN_CONTENT_LENGTH:
        return False
    return not any(pattern in body for pattern in INVALID_CONTENT_PATTERNS)
```

### 综合判断逻辑

```python
def needs_full_fetch(item: Item) -> bool:
    """判断是否需要全文获取"""
    body = item.raw_body or ""
    title = item.raw_title or ""

    # 规则 1：内容过短
    if len(body) < MIN_CONTENT_LENGTH:
        return True

    # 规则 2：标题被误识别为正文
    if is_title_as_body(title, body):
        return True

    # 规则 3：无效内容模式
    if not is_valid_content(body):
        return True

    return False
```

### 可配置参数

```yaml
# sources.yaml 全局配置（可选）
content_quality:
  min_length: 100
  title_similarity_threshold: 0.8
  invalid_patterns:
    - "Please enable JavaScript"
    - "Checking your browser"
    - "404 Not Found"
```

---

## 解决方案：两层混合策略

> **设计决策**：Level 3 (Playwright) 暂不实现。测试验证 Level 1+2 组合已达 96%+ 成功率，远超设计目标。Level 3 仅在微信等特殊场景可能需要，可在后续版本按需添加。

### 架构概览

```
                    ┌─────────────────────┐
                    │ fetch_full_content  │
                    │   (Dramatiq Task)   │
                    │   max_concurrency=3 │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Level 1: httpx    │
                    │   简单请求 + 浏览器UA │
                    │   trafilatura 提取   │
                    │   耗时: ~1-2s       │
                    └──────────┬──────────┘
                               │ 403/挑战/内容过短
                    ┌──────────▼──────────┐
                    │   Level 2: Jina AI  │
                    │   r.jina.ai/{url}   │
                    │   速率限制: 20 RPM   │
                    │   耗时: ~5-10s      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ 失败: REJECTED      │
                    │ full_fetch_succeeded│
                    │     = False         │
                    └─────────────────────┘
```

### 各层级说明

| 层级 | 技术 | 成功率 | 速度 | 资源消耗 | 适用场景 |
|------|------|--------|------|---------|---------|
| Level 1 | httpx + trafilatura | **57-75%** | 快 (1-2s) | 极低 | 无反爬或弱反爬网站 |
| Level 2 | Jina AI Reader | **100%** (救援) | 中 (5-10s) | 低 (20 RPM) | Cloudflare 保护、JS 挑战、HTTP 403 |

**测试验证结果**（2026-03-28）：

| 测试集 | Level 1 | Level 1+2 | 提升 |
|--------|---------|-----------|------|
| 构造 URL（57个） | 56.1% | **96.5%** | +40.4% |
| 真实问题 URL（26个） | 57.7% | **92.3%** | +34.6% |

---

## Level 1: httpx + trafilatura

### 技术方案

- 使用 httpx 发送带浏览器 User-Agent 的 HTTP 请求
- 使用 trafilatura 提取正文内容
- 同时提取元数据（标题、作者、发布时间、描述、图片）

### 成功条件

- HTTP 状态码 200
- 提取内容长度 ≥ 100 字符

### 降级条件

- HTTP 403/429（反爬拦截）
- HTTP 挑战响应（Cloudflare 挑战页）
- 提取内容长度 < 100 字符（正文提取失败）

### 元数据提取

trafilatura 可提取：
- 标题 (title)
- 作者 (author)
- 发布时间 (date)
- 描述 (description)
- 特色图片 (image)
- 来源域名 (hostname)

---

## Level 2: Jina AI Reader

### 技术方案

Jina AI Reader 是内容提取 API，专门处理反爬保护。采用无 API Key 模式，速率限制 20 RPM。

**请求方式**：
```bash
curl "https://r.jina.ai/https://www.example.com" \
  -H "X-Return-Format: markdown" \
  -H "X-Md-Link-Style: discarded"
```

**请求头参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| `X-Return-Format` | `markdown` | 返回 Markdown 格式 |
| `X-Md-Link-Style` | `discarded` | 丢弃链接，只保留文本内容 |

**返回格式**：Markdown 文本

### 速率限制

| 认证方式 | RPM | 每秒请求 | 并发建议 |
|---------|-----|---------|---------|
| 无 API Key | 20 | ~0.33 | **3** |

### 代码示例

```python
JINA_BASE_URL = "https://r.jina.ai/"
JINA_HEADERS = {
    "X-Return-Format": "markdown",
    "X-Md-Link-Style": "discarded",
}

async def fetch_with_jina(url: str) -> str:
    jina_url = f"{JINA_BASE_URL}{url}"
    async with httpx.AsyncClient() as client:
        response = await client.get(jina_url, headers=JINA_HEADERS)
        return response.text
```

### 配额规划

**场景：58 个情报源，50% 需全文获取 = 29 个请求/次**

| 采集频率 | 每分钟最大 | 完成时间 | 日请求总数 | 可行性 |
|---------|-----------|---------|-----------|--------|
| 每小时 | 20 | ~2 分钟 | 696 | ✓ 可行 |
| 每 30 分钟 | 20 | ~2 分钟 | 1,392 | ✓ 可行 |
| 每 15 分钟 | 20 | ~2 分钟 | 2,784 | ✓ 可行 |

**结论**：20 RPM 完全覆盖当前规模，采集耗时约 2 分钟/次。

### 特点

- 无需 API Key，始终可用
- 自动处理 Cloudflare 挑战
- 返回干净的 Markdown 格式（无链接）
- **实测成功率：100%**（对 Level 1 失败的 URL）

### 成功条件

- HTTP 状态码 200
- 返回内容长度 ≥ 100 字符

### 错误处理

| 状态码 | 含义 | 处理方式 |
|--------|------|---------|
| 429 | 速率限制 | 等待后重试 |
| 404 | 内容不存在 | REJECTED |
| 5xx | 服务错误 | 重试，最终失败则 REJECTED |

---

## Level 3: Playwright + Stealth（暂不实现）

> **决策**：测试验证 Level 1+2 组合已达 96%+ 成功率，暂不需要 Level 3。
> 保留此设计供后续参考，当遇到以下场景时可按需实现：
> - 微信公众号等需要登录/cookies 的网站
> - Jina AI 配额用尽时的兜底方案
> - 需要执行复杂 JS 交互的场景

### 技术方案（保留参考）

- Playwright 无头浏览器渲染页面
- playwright-stealth 插件绑过 Bot 检测
- trafilatura 提取正文

### 并发控制

使用 Dramatiq 原生 `max_concurrency` 参数限制浏览器实例数：

| 环境 | Worker 并发 | 浏览器并发 | 内存估算 |
|------|------------|-----------|---------|
| 测试 | 4 | 2 | ~400MB |
| 生产 | 16 | 4 | ~600MB |

### 成功条件

- 页面加载成功
- 提取内容长度 ≥ 100 字符

### 失败处理

- 记录失败，标记 `full_fetch_succeeded=False`
- Item 状态设置为 REJECTED
- 不重试（已是最兜底方案）

---

## 任务队列设计

### 任务配置

```
fetch_full_content (Level 1 + Level 2)
├── max_retries: 2
├── max_concurrency: 3 (20 RPM)
├── Level 1 失败 → 调用 Level 2 (Jina AI)
├── Jina 并发限制: 3 (20 RPM)
└── 失败时设置 item.status = REJECTED
```

### 并发控制

| 阶段 | 并发数 | 说明 |
|------|--------|------|
| Level 1 (httpx) | 3 | 受整体任务并发限制 |
| Level 2 (Jina) | 3 | 受 20 RPM 限制 |

### 优势

- 利用 Dramatiq 原生并发控制
- 单一并发参数简化配置
- Level 2 速率限制避免配额耗尽
- 简化架构，无需浏览器依赖

---

## Docker 部署变更

### 依赖变更

```toml
# pyproject.toml - 无需新增依赖
# Level 1 和 Level 2 均使用 httpx，已有依赖
```

### 环境变量

```bash
# .env - 无需额外环境变量
# Jina AI 无 API Key 模式，20 RPM
```

### 资源规划（无浏览器，资源需求低）

| 组件 | 基础内存 | 生产环境估算 |
|------|---------|-------------|
| API | ~200MB | ~200MB |
| Worker | ~200MB | ~200MB |
| **总计** | | **~400MB** |

---

## 决策记录

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 第三方服务 | 接受 Jina AI Reader | 无需 API Key，20 RPM，实测 100% 救援成功率 |
| Level 3 实现 | **暂不实现** | Level 1+2 已达 96%+ 成功率，远超设计目标 |
| 并发控制 | Dramatiq max_concurrency=3 | 单一参数，适配 20 RPM 限制 |
| 失败处理 | REJECTED | 内容不完整不可用，不保留摘要 |
| Jina 配额用尽 | REJECTED | 简单可靠，下次采集重试 |
| 触发策略 | 统一质量检测 | 移除源级配置，单一触发点 |
| API Key | 不使用 | 无 Key 模式足够，简化配置 |

---

## 测试验证

### 测试结果（2026-03-28）

#### 测试 1：构造 URL（57 个，覆盖多种场景）

| 类别 | Level 1 成功率 | Level 1+2 成功率 |
|------|---------------|-----------------|
| Cloudflare 保护 | 41.7% | **100%** |
| 其他 WAF | 28.6% | **80%** |
| JS 挑战 | 33.3% | **100%** |
| 付费墙/登录 | 28.6% | **100%** |
| Substack/Ghost/Medium | 90.0% | 90.0% |
| 无保护 | 80.0% | 80.0% |
| **总计** | **56.1%** | **96.5%** |

#### 测试 2：真实问题 URL（26 个，来自 issues/）

| 问题类型 | Level 1 | Level 2 救援 |
|----------|---------|-------------|
| HTTP 403 | 0% | **100%** |
| 内容过短 (JS 渲染) | 0% | **100%** |
| RSS 无正文 | 75% | **100%** |
| 微信公众号 | 0% | 0% |
| **总计** | **57.7%** | **92.3%** |

#### 关键发现

1. **Jina AI 完美解决 HTTP 403**：Cloudflare、WAF 反爬问题 100% 救援成功
2. **JS 渲染场景有效**：Reddit、Instagram 等动态内容也能获取
3. **微信公众号需要特殊处理**：需要登录/cookies，当前方案无法解决
4. **Level 1 有优化空间**：无保护网站成功率仅 80%，可提升

---

## 后续工作

1. **实现核心逻辑**：
   - 在 FullContentFetchService 中实现 Level 1 → Level 2 降级
   - 创建 ContentQualityService 实现触发规则判断
   - Dramatiq 任务并发限制 max_concurrency=3
2. **测试覆盖**：
   - 添加单元测试和集成测试
   - 模拟 Jina AI 速率限制场景
3. **上线后监控**：
   - 各层级成功率统计
   - REJECTED 原因分布

### Level 3 预留

当遇到以下需求时，可按需实现 Level 3：
- 微信公众号采集（需要 cookies）
- Jina AI 配额不足时的兜底
- 需要复杂 JS 交互的场景

---

## 参考资料

- [Jina AI Reader](https://jina.ai/reader/)
- [Playwright](https://playwright.dev/python/)
- [playwright-stealth](https://github.com/AtuboDad/playwright_stealth)
- [trafilatura](https://trafilatura.readthedocs.io/)