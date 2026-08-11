# 设计规格：Web 类型情报源采集功能完整支持

> **状态：** 已审批
> **创建：** 2026-08-11
> **供 pi-smith/plan 消费**

## 背景与目标

- **要解决什么问题**：web 类型情报源（`connector_type=web`）的采集链路存在 7 处缺口——API 层 test/validate 无 web 分支、api.sh 无法生成 web 配置、无增量采集、创建时无质量验证、无 JS 渲染兜底、文档配置键与实现不一致、article 判定启发式弱（实测 listing 页 861 字符被误判为文章）
- **面向谁**：管理员（通过 api.sh / API 管理 web 源）、下游分析系统（消费清洗后数据）
- **成功标准**：① 现有测试全绿 + 新增单元测试覆盖（覆盖率 ≥ 80%，CLAUDE.md 硬门槛）；② 两个真实源端到端验证——Perplexity（listing 5 篇，验证增量归零）、TechOperators（存量 13 条，验证去重与 external_id 不变）；③ `docs/source-config-examples.md` Web 部分重写为实际配置键

**实测依据**（2026-07-31 抓取）：
- TechOperators listing 页 trafilatura 提取 861 字符 > 100 阈值 → 无 `article_url_pattern` 时误判（缺口 7 实锤）
- Perplexity listing 链接含 curly apostrophe `’`（`...perplexity’s-client-endpoints...`），urljoin 保留原始字符，httpx 请求自动编码 `%E2%80%99` → 同文两 MD5（URL 规范化缺口，新增）
- 两源均无 `article:published_time` / JSON-LD / author meta，trafilatura `metadata.date` 不可靠（Perplexity 返回页面生成日期 2026-07-29，真实发布 Jun 8, 2026）→ 日期提取裁剪为轻量校验
- 两源均为静态站（Framer），httpx 直接抓取成功，JS 渲染为可选兜底
- **TechOperators 文章页与 listing 页在 HTML 结构信号上无区分度**（均无 `<article>`、h1 长度均在 10-200、链接密度均 <0.3、canonical 均指向自身）→ R21 信号打分方案废弃，改用 URL 形态 + 正文裁决
- **Perplexity listing 存在两个 URL 形态**（`/` 5 篇 vs `/articles` 9 篇），base_url 选择决定收录范围

## 数据模型

无新 DB 模型。变更范围：

```python
# Source.config 新增可选键（现有键全部不变）
"render_js": bool = False   # JS 渲染降级开关（httpx 失败或正文 <min_content_length 时触发）
"min_content_length": int = 150  # 正文质量门：trafilatura 提取 ≥ 阈值才入库（可配，默认 150）

# WebScraperConnector 新增内部状态
self._existing_urls: set[str] | None = None   # set_existing_ids 注入的已收录 URL（规范化形态）

# SourceValidationResult 复用（validate_web_source 返回同类型，无 schema 变更）
```

**不变量**：
- URL 形态统一：`_extract_links` 输出 / `set_existing_ids` 注入 / `Item.url` / `external_id` 的 md5 输入，全部为规范化后 URL
- `fetch()` 返回契约不变：`list[dict]`，字段 external_id/url/title/published_at/content/author/tags

## 架构

### 模块划分

| 模块 | 变更 | 职责 | 依赖 |
|---|---|---|---|
| `services/web_connector.py` | 重构 | 两阶段 fetch、`set_existing_ids`、URL 规范化、article 判定增强、日期轻量校验 | httpx / trafilatura / browser_fetcher |
| `services/browser_fetcher.py` | **新建** | Playwright 渲染 HTML 兜底 | playwright |
| `services/source_quality_validator.py` | 扩展 | `validate_web_source`（抓文章样本评估质量，样本不足仅置 pending_review） | WebScraperConnector（复用提取代码） |
| `tasks/ingestion_tasks.py` | 扩展 | web 分支预查 `Item.url` → `set_existing_ids` | Item 模型 |
| `api/routers/admin/sources.py` | 扩展 | `_test_web_source` / `_validate_web_source` / create 分支 | connector + validator |
| `scripts/api.sh` | 扩展 | `--config` 参数 + web 分支 + help | — |
| `docs/source-config-examples.md` | 重写 | Web 部分改为实际配置键 | — |

### 数据流

**采集链路**：

```
ingest_source (web)
  → 预查 Item.url（按 source_id）→ set_existing_ids
  → connector.fetch()
      阶段一：抓 base_url + 分页页（max_pages 上限）→ _extract_links（规范化）→ candidates
              ├─ 兼容路径：candidates 为空且 base_url 命中 article_url_pattern → [base_url]（直接配置文章 URL 的源）
              └─ 过滤 existing → 新链接列表（保持 listing 顺序，MAX_ITEMS 作用于新链接）
      阶段二：逐个抓正文（请求 URL 显式用规范化 URL，与 external_id 一致）
              ├─ URL 形态排除（见 R21 规则定义）：与 base_url 同路径 / 纯数字段 / 导航词黑名单 → 跳过
              ├─ httpx 抓取 → 正文 <min_content_length 且 render_js=true → BrowserFetcher 降级重抓
              └─ 正文裁决：trafilatura 提取 ≥min_content_length（默认 150）→ item；< 阈值 → 跳过不入库
  → create_item（external_id = md5(规范化URL)）→ IntegrityError 去重 → normalize → 下游
```

**管理链路**：

```
POST /sources/{id}/test (web)   → httpx 抓 base_url → _extract_links 计数 → items_found
POST /sources/{id}/validate     → validate_web_source → content_type/avg_content_length 写入
POST /sources (web create)      → 同 validate，容错：失败仅置 pending_review，不阻断创建
```

### 设计原则

- 验证与采集共用同一套提取代码（`_extract_links`/`_extract_content`），杜绝行为偏差
- API 层只做分发与聚合，抓取细节全部收敛到 connector / validator
- BrowserFetcher 按源启用（`render_js` 才实例化），资源可控

### 复杂度自检

- 模块接口一句话说清：是（fetch / test / validate 各司其职）
- 需要 BrowserFetcher 吗：是（方案 A 已定，依赖已存在）；不直接复用 transcript_extractor（YouTube transcript 语义，职责污染）
- 能用已有模块达到目标吗：不能（transcript_extractor 是 transcript 专属）

## 关键接口

### `WebScraperConnector.set_existing_ids`

```python
def set_existing_ids(self, urls: set[str]) -> None:
    """注入已收录的规范化 URL 集合；fetch 阶段二跳过这些链接的正文抓取。"""
```

- **设计考量**：与 YouTube `set_existing_video_ids` 对称；存 URL 原文（非 hash）——`_extract_links` 输出即 URL 原文，直接比对免去先算 MD5
- **错误处理**：无异常路径（纯状态注入）
- **输入约束**：URL 须为规范化形态（与 `_extract_links` 输出一致）；调用方（ingest_source）负责从 `Item.url` 预查

### `SourceQualityValidator.validate_web_source`

```python
async def validate_web_source(self, source_config: dict[str, Any]) -> SourceValidationResult:
    """抓取文章样本评估正文质量，复用 _analyze_samples 与 RSS 同口径阈值。"""
```

- **设计考量**：复用 `_analyze_samples` + MIN_AVG_CONTENT_LENGTH=50 / MAX_SAMPLE_ITEMS=10 阈值（口径与 RSS 统一）；**样本下限放宽**：web 分支 ≥1 篇内容达标即有效（小型博客 listing 可能仅 2 篇，沿用 RSS 的 MIN_SAMPLE_ITEMS=3 会误杀）；样本不足时仅置 pending_review 不判失败（与 create 容错语义一致）；内部实例化 `WebScraperConnector(config)` 调用 `_extract_links`/`_extract_content`
- **错误处理**：listing 抓取失败 / 链接为 0 / 文章页提取失败 → `is_valid=False` + 具体 rejection_reason（与 RSS 分支同构，不抛异常）
- **输入约束**：config 含 `base_url`；SSRF 校验 base_url 与每个样本 URL

### `BrowserFetcher`

```python
class BrowserFetcher:
    """无头浏览器渲染 HTML，为 SPA 站点提供兜底。按源启用（render_js: true）。"""

    async def render(self, url: str) -> str | None:
        """渲染页面返回完整 HTML；失败返回 None（调用方走 httpx 原始结果）。"""
```

- **设计考量**：独立组件；复用 transcript_extractor 的 `chromium.launch_persistent_context` 模式
- **错误处理**：渲染失败 → None → fetch 阶段二用 httpx 结果（有总比没有好）
- **输入约束**：url 须为 http(s)；调用方负责按源启用

### API 层 / 脚本（复用现有 schema，无新增）

- `test` 返回：`items_found` = `_extract_links` 链接数（link_pattern 命中率直接可见）；无 link_pattern 时追加 warning；403/404/429 复用 suggestion_map 思路
- `validate` 返回：`ValidationResponse` 复用（content_type / avg_content_length / sample_completeness / samples_analyzed），**新增 `warnings: list[str] = []` 字段**（默认值向后兼容，承载 R37 的无 link_pattern 提示）
- `create`：web 分支跑 `validate_web_source`，失败仅置 `pending_review`（与 RSS 同容错）；无 link_pattern 提示走 `SourceResponse.warnings`（extra_warnings 机制，无需改动）
- api.sh：`sources create --type web --url URL [--config '{"link_pattern": "..."}'] [--tier T]`

## 错误处理

| 场景 | 策略 | 调用方看到 |
|---|---|---|
| listing 抓取失败（阶段一） | 现有 `_fetch_page_with_retry` 全复用（重试/退避/429/SSRF）→ 整体 `ConnectorError` | 采集失败 → 失败计数 → 冻结逻辑不变 |
| 单篇文章页抓取失败（阶段二） | 语义改进：跳过该 URL 继续抓其他新链接 | 该文章缺失，其余正常入库 |
| render_js 降级失败 | `BrowserFetcher.render` → None → 用 httpx 原始结果 | 正文可能偏短，但不丢文章 |
| 增量过滤后无新链接 | fetch 返回空列表 → 走现有 "No items fetched" 分支 | 正常结束，更新 next_ingest_at |
| external_id 重复（残余） | create_item 的 IntegrityError 去重兜底（现有） | 静默跳过重复 |
| validate / test 抓取失败 | `is_valid=False` / `failed` + rejection_reason / suggestion_map | 不抛异常，不阻断创建 |

## 测试策略

**mock 策略**：沿用现有 `patch("httpx.AsyncClient")` + MagicMock/AsyncMock + HTML fixture（不引入 respx）。fetch 两阶段通过 mock client 断言**请求 URL 序列**。

| 测试类 / 文件 | 覆盖场景 |
|---|---|
| `TestWebScraperConnectorIncremental`（web_connector 测试扩展） | ① existing 注入后只抓新链接（断言请求 URL 序列）② 全部已收录 → 空列表 ③ 未设置 → 抓全部 ④ MAX_ITEMS 作用于新链接 |
| `TestWebScraperConnectorNormalizeUrl` | ① 非 ASCII → quote 规范化 ② 已有 `%XX` 不二次编码（safe 含 `%`）③ 规范化后 external_id 稳定 |
| `TestWebScraperConnectorArticleDetection` | ① pattern 优先 ② base_url 特判（listing 恒非文章）③ URL 形态排除三规则（同路径 / 纯数字段 / 导航词黑名单）④ 正文裁决（≥min_content_length → 文章，< 阈值 → 跳过）⑤ 反向用例：TechOperators listing fixture（旧信号 3/4 命中）不得误判 |
| `TestWebScraperConnectorDateValidation` | ① date > now+7d → 回退收录时间 ② 正常日期保持 |
| `TestWebScraperConnectorFetchTwoPhase` | ① 分页 candidates 合并 ② candidates 空 + base_url 为文章页 → 兼容路径 ③ 阶段二单 URL 失败跳过 |
| `test_browser_fetcher.py`（新建） | render 成功返回 HTML / 失败返回 None（mock playwright） |
| `test_source_quality_validator.py`（新建） | validate_web_source 正常 / listing 失败 / 链接 0 / 文章提取失败 / 阈值生效 |
| `test_admin_sources.py` 扩展 | web test（成功/403/404/429/无 pattern warning）、validate（写入/置 pending_review）、create（触发验证/容错） |
| `test_ingestion_tasks.py` 扩展 | ingest_source web 分支预查 `Item.url` 传给 set_existing_ids |
| `test_api_sh.sh` 扩展 | web create 生成 base_url 配置、`--config` JSON 透传 |
| **现有 fetch 测试适配** | `TestWebScraperConnectorFetchAutoMode` 等 fixture（listing 即文章页混合结构）两阶段重构后断言核对（请求序列/items 数量）——Task 1 内完成，非事后修复 |

**E2E 验证**（真实源，验收标准；断言动态，不硬编码篇数）：
- Perplexity：建源（base_url 选 `/` 或 `/articles`，收录范围分别为 5/9 篇）→ test → validate → 首次采集 ≥1 篇 → 二次采集增量归零 → 新文章出现时只收增量
- TechOperators：存量 13 条去重（规范化后 external_id 不变）→ 二次采集 0 新文章

**可测试边界检查**：所有逻辑均可通过现有 mock 模式直接调用（fetch 全流程 mock AsyncClient、内部方法直接调实例、validator 的 httpx 同样 mock），无需提取额外纯函数。

## 向后兼容性

| 变更 | 兼容性 |
|---|---|
| `fetch()` 返回契约 | 不变（同字段）✓ |
| 未调用 `set_existing_ids` | 行为 = 抓全部 candidates（兼容模式）✓ |
| **采集范围收窄**（BFS → listing-only） | **有意行为变更**（设计决策）：当前库仅 TechOperators（listing 9/9 全量）无实际影响 |
| URL 规范化 | TechOperators 全 ASCII → external_id 不变 → 存量 13 条不受影响 ✓；非 ASCII 存量源当前不存在 |
| `MAX_ITEMS` 语义 | 从"总 items 上限"→"新链接上限"（已收录不占配额）——行为增强 |
| config / API / api.sh | 新增 `render_js` 键、`--config` 参数，现有全部兼容 ✓ |

## 现有模式遵循

- `set_existing_ids` ↔ `set_existing_video_ids`（命名/签名对称）
- `_test_web_source` / `_validate_web_source` ↔ `_test_youtube_source` / `_validate_rss_source`（分支结构同构）
- `validate_web_source` 复用 `_analyze_samples` + 阈值（口径统一）
- `BrowserFetcher` 复用 `transcript_extractor` 的 persistent context 模式
- 测试按类分组（`TestWebScraperConnectorIncremental` 等），延续现有组织

## 需求清单

| ID | 需求 | 来源节 | 优先级 |
| --- | --- | --- | --- |
| R01 | WebScraperConnector 新增 `_existing_urls` 状态与 `set_existing_ids(urls)` 注入方法 | 关键接口 | P0 |
| R02 | `fetch()` 重构为两阶段：阶段一只抓 base_url + 分页页提取链接，阶段二只抓过滤 existing 后的新链接正文 | 架构 | P0 |
| R03 | 兼容路径：candidates 为空且 base_url 命中 article_url_pattern 时，将 base_url 作为唯一候选（直接配置文章 URL 的源） | 架构 | P0 |
| R04 | MAX_ITEMS 作用于新链接（已收录不占配额） | 架构 | P0 |
| R05 | config 新增 `render_js` 键（默认 false）与 `min_content_length` 键（默认 150，正文质量门） | 数据模型 | P0 |
| R06 | 新建 `browser_fetcher.py`，`BrowserFetcher.render(url) -> str | None`，复用 persistent context 模式 | 架构 | P1 |
| R07 | `_extract_links` 对 urljoin 结果做 URL 规范化（quote 非 ASCII，safe 含 `%` 防二次编码） | 关键接口 | P0 |
| R08 | external_id = md5(规范化 URL)；Item.url 与预查注入同形态；阶段二请求 URL 显式用规范化 URL（请求与 ID 一致） | 关键接口 | P0 |
| R09 | `SourceQualityValidator.validate_web_source(config)` 复用 `_analyze_samples` + 阈值，样本下限放宽（≥1 篇达标即有效），样本不足仅置 pending_review；内部实例化 WebScraperConnector 复用提取代码 | 关键接口 | P0 |
| R10 | BrowserFetcher 按源启用（render_js=true 才实例化） | 关键接口 | P1 |
| R11 | 阶段二单 URL 抓取失败 → 跳过继续；阶段一 listing 失败 → 整体 ConnectorError | 错误处理 | P0 |
| R12 | render_js 降级失败 → 用 httpx 原始结果 | 错误处理 | P0 |
| R13 | 增量过滤后无新链接 → fetch 返回空列表 | 错误处理 | P0 |
| R14 | 未调用 set_existing_ids 时行为向后兼容（抓全部 candidates） | 向后兼容 | P0 |
| R15 | 存量 web 源（TechOperators）配置与 external_id 不受影响 | 向后兼容 | P0 |
| R16 | `test_source` 增加 web 分支：httpx 抓 base_url + `_extract_links` 计数（items_found），403/404/429 针对性建议，无 link_pattern 追加 warning | API 层 | P0 |
| R17 | `validate_source_quality` 增加 web 分支：validate_web_source 结果写入 content_type/avg_content_length，统一 pending_review | API 层 | P0 |
| R18 | `create_source` 对 web 源执行质量验证，失败仅置 pending_review 不阻断创建 | API 层 | P0 |
| R19 | api.sh `cmd_sources_create` 增加 web 分支（config 用 base_url）+ `--config` JSON 透传 + help 更新 | 脚本 | P1 |
| R20 | `ingest_source` 对 web 源预查 `Item.url`（按 source_id）注入 `set_existing_ids` | 任务层 | P0 |
| R21 | `_is_article_page` 重写：article_url_pattern 优先；base_url 恒按 listing；无 pattern 时 URL 形态排除三规则（①与 base_url 同路径 ②路径末段纯数字 ③导航词黑名单完全匹配：about/contact/team/terms/privacy/policy/careers/tags/category/archive）+ 正文裁决（提取 ≥min_content_length → 文章，< 阈值 → 跳过）；废弃 HTML 信号打分（实测无区分度）；正文裁决语义为内容质量门，与 listing 判定解耦 | 健壮性 | P0 |
| R22 | 日期轻量校验：metadata.date > now+7d 回退收录时间；文档注明 web 源日期可能偏差，精确场景用 manual selectors 的 date 选择器 | 健壮性 | P1 |
| R23 | docs/source-config-examples.md Web 部分重写为实际配置键（base_url/extraction_mode/link_pattern/link_selector/article_url_pattern/selectors/pagination_*/max_pages/user_agent/headers/render_js） | 文档 | P0 |
| R24 | TestWebScraperConnectorIncremental：增量过滤/空列表/兼容模式/MAX_ITEMS | 测试策略 | P0 |
| R25 | TestWebScraperConnectorNormalizeUrl：quote 规范化/不二次编码/ID 稳定 | 测试策略 | P0 |
| R26 | TestWebScraperConnectorArticleDetection：pattern 优先/base_url 特判/URL 形态排除三规则（含分页、导航词、纯数字段边界）/正文裁决/反向用例（TechOperators listing 旧信号 3/4 命中不得误判） | 测试策略 | P0 |
| R27 | TestWebScraperConnectorDateValidation：超期回退/正常保持 | 测试策略 | P0 |
| R28 | TestWebScraperConnectorFetchTwoPhase：分页合并/兼容路径/单 URL 失败跳过 | 测试策略 | P0 |
| R29 | test_browser_fetcher.py：render 成功/失败 | 测试策略 | P0 |
| R30 | test_source_quality_validator.py：validate_web_source 各场景 | 测试策略 | P0 |
| R31 | test_admin_sources.py：web test/validate/create 分支 | 测试策略 | P0 |
| R32 | test_ingestion_tasks.py：web 分支预查 | 测试策略 | P0 |
| R33 | test_api_sh.sh：web create 与 --config | 测试策略 | P0 |
| R34 | 现有 fetch 测试适配（TestWebScraperConnectorFetchAutoMode 等断言核对） | 测试策略 | P0 |
| R35 | Perplexity E2E：建源（base_url 选 `/` 或 `/articles`）/首次采集 ≥1 篇/二次增量归零/新文章只收增量（断言动态） | 测试策略 | P0 |
| R36 | TechOperators E2E：存量去重/二次 0 新 | 测试策略 | P0 |
| R37 | 无 link_pattern 时 validate 返回 warning 提示配置（candidates 会混入导航链接，正文裁决兜底）；ValidationResponse 新增 `warnings: list[str] = []` 字段（向后兼容），create 时提示走 SourceResponse.warnings | 风险与假设 | P1 |

## 替代方案（讨论过但未选的）

| 方案 | 为什么不选 |
| --- | --- |
| 保持 BFS 发现（文章页交叉链接也采集） | 采集范围不可预测（文章互相链接可致爬取爆炸）；listing 即源发布面，收窄更贴近语义 |
| URL 规范化放 ID 生成处 | external_id 稳定但请求 URL / existing 对比仍原始形态，未来 sitemap 接入时比对 miss |
| 从 listing 文本提取日期 | 仅覆盖部分源（TechOperators 无日期文本）；成本高价值低，裁剪为已知限制 |
| JS 渲染本次不做 | 不满足"全覆盖"；SPA 型源（Next.js/React 博客）无兜底 |
| 新建独立 WebSourceValidator | validate_web_source 复用 `_analyze_samples` + 阈值更省，且与 RSS 口径统一 |
| HTML 信号打分（`<article>`/h1/链接密度/canonical）判定文章 | 实测 TechOperators listing 与文章页无区分度（均无 `<article>`、链接密度均 <0.3、canonical 均指向自身），任何阈值组合均失效；改用 URL 形态 + 正文裁决 |

## 风险与假设

**核心假设**：
- listing 链接即源发布面（两阶段收窄的前提）——设计决策已确认
- httpx 对规范化 URL 请求无副作用——已实测（`%E2%80%99` 请求 200）
- Playwright 环境可用（transcript_extractor 已依赖，chromium 已随部署安装）

**主要风险**：
| 风险 | 缓解 |
|---|---|
| 非 ASCII 存量 URL 迁移（external_id 变化致重复） | 当前库仅 TechOperators（全 ASCII）无此风险；残余靠 create_item 去重兜底 |
| metadata.date 偏差（Perplexity 返回页面生成日期） | 裁剪为已知限制：轻量校验拦截明显荒谬值；文档注明精确场景用 manual selectors 的 date 选择器 |
| 无 link_pattern 时 candidates 混入导航链接 | 正文裁决（<200 跳过）兜底 + validate 时 warning 提示配置 link_pattern |
| 导航页/404 页正文超阈值（实测 TechOperators 404 页 trafilatura 306 字符 > min_content_length） | 影响有限：仅无/宽泛 link_pattern 时混入，单条污染可删；URL 形态排除导航词黑名单拦截 + validate warning 提示配置 link_pattern |
| Playwright chromium 未随部署镜像安装 | 实施时在 Docker 镜像验证（P1）；render_js 默认 false 不影响主链路 |
| 现有 fetch 测试断言需适配 | Task 1 内完成核对（非事后修复），fixture 结构兼容 |
| E2E 依赖真实网络与已部署环境 | 验收标准明确两个源的预期结果（Perplexity ≥1 篇/归零；TechOperators 去重/0 新），断言动态不硬编码 |

## 下一步

→ 将本 spec 交给 pi-smith/plan 分解为可执行的任务计划（依赖序：connector 层 → 质量验证 → 任务层 → API 层 → 脚本 → 文档 → E2E）
