# 全文获取混合策略设计

## 概述

**目标**: 解决 RSS 采集全文时遇到的 Cloudflare 等 WAF 反爬问题（HTTP 403）

**相关 Issue**: 待创建

**预期结果**: 全文获取成功率从 ~50% 提升至 ~90%+

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

## 解决方案：三层混合策略

### 架构概览

```
                    ┌─────────────────────┐
                    │ fetch_full_content  │
                    │   (Dramatiq Task)   │
                    │   max_concurrency=16│
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
                    │   第三方内容提取服务  │
                    │   耗时: ~2-3s       │
                    └──────────┬──────────┘
                               │ 失败/配额用尽
                    ┌──────────▼──────────┐
                    │ fetch_full_content_ │
                    │     browser         │
                    │ max_concurrency=4   │
                    │   Playwright+Stealth│
                    │   耗时: ~5-10s      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ 失败: 保留摘要内容   │
                    │ full_fetch_succeeded│
                    │     = False         │
                    └─────────────────────┘
```

### 各层级说明

| 层级 | 技术 | 成功率 | 速度 | 资源消耗 | 适用场景 |
|------|------|--------|------|---------|---------|
| Level 1 | httpx + trafilatura | ~60% | 快 (1-2s) | 极低 | 无反爬或弱反爬网站 |
| Level 2 | Jina AI Reader | ~90% | 中 (2-3s) | 低 | Cloudflare 保护、JS 挑战 |
| Level 3 | Playwright + Stealth | ~80% | 慢 (5-10s) | 高 (~100MB/实例) | Level 2 失败的边缘情况 |

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

Jina AI Reader 是免费的内容提取 API，专门处理反爬保护。

**使用方式**：
```
GET https://r.jina.ai/{原始URL}
```

**返回格式**：Markdown，包含元数据（Title、URL、Published Time）

### 特点

- 免费配额：1000 次/天
- 无需 API Key
- 自动处理 Cloudflare 挑战
- 返回干净的 Markdown 格式

### 成功条件

- HTTP 状态码 200
- 返回内容非空

### 降级条件

- HTTP 402/429（配额用尽）
- HTTP 403/404（内容不存在）
- 请求超时/网络错误

---

## Level 3: Playwright + Stealth

### 技术方案

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
- 保留 RSS 摘要内容
- 不重试（已是最兜底方案）

---

## 任务队列设计

### 任务拆分

```
fetch_full_content (Level 1 + Level 2)
├── max_retries: 2
├── max_concurrency: 16 (生产)
└── 失败时调用 → fetch_full_content_browser

fetch_full_content_browser (Level 3)
├── max_retries: 1
├── max_concurrency: 4 (生产)
└── 失败时标记 full_fetch_succeeded=False
```

### 优势

- 利用 Dramatiq 原生并发控制，无需额外实现信号量
- Level 1/2 高并发处理大部分请求
- Level 3 低并发处理资源密集型请求
- 任务独立，互不阻塞

---

## Docker 部署变更

### 依赖变更

```toml
# pyproject.toml
[project.dependencies]
playwright = ">=1.40.0"

[project.optional-dependencies]
browser = ["playwright-stealth"]
```

### Dockerfile 变更

```dockerfile
# 安装 Playwright 浏览器
RUN playwright install chromium --with-deps
```

### 资源规划

| 组件 | 基础内存 | 增量 | 生产环境估算 |
|------|---------|------|-------------|
| API | ~200MB | - | ~200MB |
| Worker (不含浏览器) | ~200MB | - | ~200MB |
| Worker (浏览器池) | - | 4×100MB | ~400MB |
| **Worker 总计** | | | **~600MB** |

---

## 决策记录

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 第三方服务 | 接受 Jina AI Reader | 免费配额足够，接入简单，成功率高 |
| 部署方式 | 服务内集成 | 实现简单，适合当前规模 |
| 并发控制 | Dramatiq max_concurrency | 利用现有机制，无需额外实现 |
| 失败处理 | 保留摘要 | 已是最兜底，重试无意义 |
| Jina 配额用尽 | 直接降级 Level 3 | 简单可靠 |
| 源级策略配置 | 统一策略 | 实现简单，后续可扩展 |

---

## 测试验证

### 已验证场景

| URL | Level 1 | Level 2 (Jina) | 备注 |
|-----|---------|----------------|------|
| OpenAI 博客 (Cloudflare) | ❌ 403 | ✅ 成功 | 验证 Level 2 必要性 |
| Substack 博客 | ✅ 成功 | ✅ 成功 | Level 1 足够 |

### 待验证场景

- Level 3 (Playwright) 实际成功率
- Jina AI 配额限制的实际影响
- 不同类型网站的成功率分布

---

## 后续工作

1. **核心代码合并后**：细化服务层实现细节
2. **实现完成后**：
   - 添加 Playwright 依赖和 Dockerfile 变更
   - 实现三层获取逻辑
   - 添加单元测试和集成测试
3. **上线后监控**：
   - 各层级成功率统计
   - Jina AI 配额使用监控
   - 浏览器实例资源监控

---

## 参考资料

- [Jina AI Reader](https://jina.ai/reader/)
- [Playwright](https://playwright.dev/python/)
- [playwright-stealth](https://github.com/AtuboDad/playwright_stealth)
- [trafilatura](https://trafilatura.readthedocs.io/)