---
spec: docs/specs/2026-08-11-web-source-support-design.md
created: 2026-08-11
---

# 实现计划：Web 类型情报源采集功能完整支持

> 基于已审批 spec `docs/specs/2026-08-11-web-source-support-design.md`（R01-R37，经两轮评审修订）
> 执行顺序：Task 1 → 2 → 3 → 4/5/6（可并行）→ 7 → 8 → 9 → 10/11（可并行）→ 12

## File Structure Map

| 文件 | 操作 | 职责 |
|---|---|---|
| `src/cyberpulse/services/web_connector.py` | 修改 | fetch 两阶段重构、URL 规范化、`set_existing_ids`、`_is_article_page` 重写、日期校验 |
| `src/cyberpulse/services/browser_fetcher.py` | **新建** | `BrowserFetcher.render()` Playwright 渲染兜底 |
| `src/cyberpulse/services/source_quality_validator.py` | 修改 | `validate_web_source` + `_fetch_web_samples` |
| `src/cyberpulse/tasks/ingestion_tasks.py` | 修改 | web 分支预查 `Item.url` → `set_existing_ids` |
| `src/cyberpulse/api/routers/admin/sources.py` | 修改 | `_test_web_source` / `_validate_web_source` / create 分支 |
| `src/cyberpulse/api/schemas/source.py` | 修改 | `ValidationResponse` 新增 `warnings` 字段 |
| `scripts/api.sh` | 修改 | `cmd_sources_create` web 分支 + `--config` 参数 + help |
| `docs/source-config-examples.md` | 修改 | Web 部分重写为实际配置键 |
| `tests/test_services/test_web_connector.py` | 修改 | 新增 Incremental/NormalizeUrl/ArticleDetection/DateValidation 类 + 现有 fetch 测试适配 |
| `tests/test_services/test_browser_fetcher.py` | **新建** | render 成功/失败 |
| `tests/test_services/test_source_quality_validator.py` | **新建** | validate_web_source 各场景 |
| `tests/test_api/test_admin_sources.py` | 修改 | web test/validate/create 分支 |
| `tests/test_tasks/test_ingestion_tasks.py` | 修改 | web 分支预查 |
| `tests/test_api_sh.sh` | 修改 | web create 与 `--config` |

---

### task-1：fetch 两阶段重构 + 现有测试适配

**目标：** 将 `WebScraperConnector.fetch()` 从 BFS 单阶段重构为"listing 提取 → 正文抓取"两阶段，适配现有测试断言。

**Covers:** R02, R03, R04, R11, R13, R14, R28, R34
**TDD 策略：** 🟢 纯逻辑（fetch 流程重构，mock httpx 全流程验证）

**涉及文件：** `src/cyberpulse/services/web_connector.py`、`tests/test_services/test_web_connector.py`

- [ ] Step 1: 写 `TestWebScraperConnectorFetchTwoPhase` 测试（先 RED）
      新建测试类，覆盖：① 分页页 candidates 合并（断言 mock client 的请求 URL 序列 = listing + 分页页 + 各文章页）② candidates 为空且 base_url 命中 article_url_pattern → 兼容路径 ③ 阶段二单 URL 抛 ConnectorError → 跳过继续（断言其他文章仍入库）
      ```python
      @pytest.mark.asyncio
      async def test_fetch_two_phase_only_article_pages(self):
          """两阶段：只抓 listing + 文章页，不抓导航页。"""
          listing_html = """<html><body>
              <a href="https://example.com/article/1">A1</a>
              <a href="https://example.com/about">About</a>
          </body></html>"""
          article_html = "<html><body><article><h1>T1</h1><p>" + "x" * 500 + "</p></article></body></html>"
          calls = []
          async def fake_get(url, headers=None):
              calls.append(str(url))
              r = MagicMock(); r.status_code = 200; r.raise_for_status = MagicMock()
              r.text = listing_html if "example.com/" == str(url).rstrip("/") + "/" or "/article/" not in str(url) else article_html
              return r
          with patch("httpx.AsyncClient") as mock_cls:
              mock_client = AsyncMock(); mock_client.__aenter__.return_value = mock_client
              mock_client.__aexit__.return_value = None; mock_client.get.side_effect = fake_get
              mock_cls.return_value = mock_client
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              items = await connector.fetch()
          # 断言：只请求了 listing + article/1（未请求 /about）
          assert any("/article/1" in c for c in calls)
          assert not any("/about" in c for c in calls)
      ```
      运行 `uv run pytest tests/test_services/test_web_connector.py -k FetchTwoPhase` → RED（新方法不存在或行为不符）

- [ ] Step 2: 重构 `fetch()` 为两阶段
      替换 `fetch()` 主体（保持 `validate_config()` 与 `httpx.AsyncClient` 配置不变）：
      ```python
      async def fetch(self) -> list[dict[str, Any]]:
          self.validate_config()
          base_url = self.config["base_url"]
          extraction_mode = self.config.get("extraction_mode", "auto")

          async with httpx.AsyncClient(
              timeout=httpx.Timeout(self.CONNECT_TIMEOUT, read=self.READ_TIMEOUT),
              follow_redirects=True,
          ) as client:
              # 阶段一：抓 listing（base_url + 分页页），提取文章链接
              listing_htmls = await self._fetch_listing_pages(client, base_url)
              candidates: list[str] = []
              for html in listing_htmls:
                  candidates.extend(self._extract_links(html, base_url))
              candidates = list(dict.fromkeys(candidates))  # 跨页去重（保序）

              # 兼容路径：candidates 为空且 base_url 命中 article_url_pattern
              if not candidates and listing_htmls and self._is_article_page(
                  base_url, listing_htmls[0]
              ):
                  candidates = [base_url]

              # 阶段二：抓正文
              items: list[dict[str, Any]] = []
              for url in candidates:
                  if self._existing_urls is not None and url in self._existing_urls:
                      continue
                  if len(items) >= self.MAX_ITEMS:
                      logger.warning(
                          f"Web scraper reached max items limit at {self.MAX_ITEMS} items"
                      )
                      break
                  try:
                      html = await self._fetch_page_with_retry(client, url)
                  except ConnectorError as e:
                      # 单 URL 失败：跳过继续（listing 是源健康信号，单篇是局部问题）
                      logger.warning(f"Skipping article '{url}': {e}")
                      continue
                  if not self._is_article_page(url, html):
                      continue
                  item = self._extract_content(html, url, extraction_mode)
                  if item:
                      items.append(item)

          return items
      ```

- [ ] Step 3: 新增 `_fetch_listing_pages` 私有方法（含分页）
      ```python
      async def _fetch_listing_pages(
          self, client: httpx.AsyncClient, base_url: str
      ) -> list[str]:
          """抓取 listing 页（base_url + 分页页），返回 HTML 列表。"""
          pagination_type = self.config.get("pagination_type", "none")
          pagination_param = self.config.get("pagination_param", "page")
          max_pages = self.config.get("max_pages", self.MAX_PAGES)

          pages: list[str] = []
          for page_num in range(1, max_pages + 1):
              url = base_url if page_num == 1 else self._get_next_page_url(
                  base_url, page_num, pagination_param
              )
              if pagination_type != "page" and page_num > 1:
                  break  # 非 page 分页：只抓第一页
              try:
                  html = await self._fetch_page_with_retry(client, url)
              except ConnectorError:
                  raise  # listing 失败 = 源健康信号，整体失败
              if html:
                  pages.append(html)
          return pages
      ```
      注意：`pagination_type != "page"` 时只抓 base_url 本身（第一页）；`pagination_type == "page"` 时按 `pagination_param` 递增直到 `max_pages`。

- [ ] Step 4: 运行新增测试 → GREEN
      `uv run pytest tests/test_services/test_web_connector.py -k FetchTwoPhase` → 全部通过

- [ ] Step 5: 适配现有 fetch 测试（R34）
      运行 `uv run pytest tests/test_services/test_web_connector.py` → 记录失败用例
      逐用例适配：
      - `TestWebScraperConnectorFetchAutoMode.test_fetch_auto_mode`：fixture 中 base_url 是 `https://example.com/article/test`（直接配文章 URL），需在 fixture 或断言层调整——兼容路径（candidates 为空 + article_url_pattern 命中）已覆盖此场景；若仍失败，检查 `_extract_links` 对 fixture 的提取结果
      - `test_fetch_with_custom_user_agent` 等：断言请求序列/items 数量按两阶段语义修正
      目标：`uv run pytest tests/test_services/test_web_connector.py` 全绿（含新增 + 既有）

- [ ] Step 6: 验证全量服务层测试无回归
      `uv run pytest tests/test_services/ -x` → 通过（Task 3 的 `set_existing_ids` 未实现前，`self._existing_urls` 需在 `__init__` 或 fetch 内初始化为 None，见 Step 2 前置：在 `fetch()` 开头加 `if not hasattr(self, "_existing_urls"): self._existing_urls = None`，Task 3 再正式初始化）

---

### task-2：URL 规范化

**目标：** `_extract_links` 对 urljoin 结果做 URL 规范化（quote 非 ASCII），保证 external_id 稳定（实测 Perplexity curly apostrophe 坑）。

**Covers:** R07, R08, R15, R25
**TDD 策略：** 🟢 纯逻辑

**涉及文件：** `src/cyberpulse/services/web_connector.py`、`tests/test_services/test_web_connector.py`

- [ ] Step 1: 写 `TestWebScraperConnectorNormalizeUrl` 测试（先 RED）
      ```python
      class TestWebScraperConnectorNormalizeUrl:
          def test_extract_links_normalizes_non_ascii(self):
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              html = '<a href="/articles/perplexity\u2019s-client">Post</a>'
              links = connector._extract_links(html, "https://example.com/")
              assert links == ["https://example.com/articles/perplexity%E2%80%99s-client"]

          def test_normalize_url_keeps_existing_escapes(self):
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              html = '<a href="/articles/perplexity%E2%80%99s">Post</a>'
              links = connector._extract_links(html, "https://example.com/")
              assert links == ["https://example.com/articles/perplexity%E2%80%99s"]  # 不二次编码

          def test_normalize_url_stable_external_id(self):
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              html = '<a href="/articles/perplexity\u2019s">Post</a>'
              links = connector._extract_links(html, "https://example.com/")
              eid1 = connector._generate_external_id(links[0])
              html2 = '<a href="/articles/perplexity%E2%80%99s">Post</a>'
              links2 = connector._extract_links(html2, "https://example.com/")
              assert connector._generate_external_id(links2[0]) == eid1
      ```
      `uv run pytest tests/test_services/test_web_connector.py -k NormalizeUrl` → RED

- [ ] Step 2: 实现 `_normalize_url` 并在 `_extract_links` 应用
      ```python
      # 模块级常量或类方法；safe 含 % 防止二次编码已有转义
      def _normalize_url(self, url: str) -> str:
          """规范化 URL：仅编码非 ASCII 字符，保留已有 %XX 转义与合法保留字符。"""
          return urllib.parse.quote(url, safe="%/:#@?&=+~,;!$'()*_-")
      ```
      `_extract_links` 中 `urljoin` 后紧跟规范化：
      ```python
      absolute_url = urllib.parse.urljoin(base_url, href)
      absolute_url = self._normalize_url(absolute_url)
      ```

- [ ] Step 3: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_web_connector.py -k NormalizeUrl` → 通过

- [ ] Step 4: 回归验证既有链接测试（`test_extract_links_*` 8 个用例不受影响——ASCII URL 规范化后不变）
      `uv run pytest tests/test_services/test_web_connector.py` → 全绿

---

### task-3：set_existing_ids 增量过滤

**目标：** 新增 `set_existing_ids()` 注入已收录 URL，fetch 阶段二跳过已收录链接（增量采集核心）。

**Covers:** R01, R24
**TDD 策略：** 🟢 纯逻辑

**涉及文件：** `src/cyberpulse/services/web_connector.py`、`tests/test_services/test_web_connector.py`

- [ ] Step 1: 写 `TestWebScraperConnectorIncremental` 测试（先 RED）
      ```python
      class TestWebScraperConnectorIncremental:
          @pytest.fixture
          def listing_html(self):
              return """<html><body>
                  <a href="https://example.com/article/1">A1</a>
                  <a href="https://example.com/article/2">A2</a>
                  <a href="https://example.com/article/3">A3</a>
              </body></html>"""

          @pytest.fixture
          def article_html(self):
              return "<html><body><h1>T</h1><p>" + "x" * 500 + "</p></body></html>"

          async def _fetch_with_existing(self, existing, listing_html, article_html):
              calls = []
              def fake_get(url, headers=None):
                  calls.append(str(url))
                  r = MagicMock(); r.status_code = 200; r.raise_for_status = MagicMock()
                  r.text = listing_html if str(url).rstrip("/") == "https://example.com" else article_html
                  return r
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = AsyncMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None; mock_client.get.side_effect = fake_get
                  mock_cls.return_value = mock_client
                  connector = WebScraperConnector({"base_url": "https://example.com/"})
                  connector.set_existing_ids(existing)
                  items = await connector.fetch()
              return items, calls

          @pytest.mark.asyncio
          async def test_skips_existing_urls(self, listing_html, article_html):
              items, calls = await self._fetch_with_existing(
                  {"https://example.com/article/1"}, listing_html, article_html
              )
              assert not any("/article/1" in c for c in calls)  # 已收录不抓
              assert any("/article/2" in c for c in calls)

          @pytest.mark.asyncio
          async def test_all_existing_returns_empty(self, listing_html, article_html):
              items, calls = await self._fetch_with_existing(
                  {"https://example.com/article/1", "https://example.com/article/2",
                   "https://example.com/article/3"}, listing_html, article_html
              )
              assert items == []  # 全部已收录 → 空列表（走 No items fetched 分支）

          @pytest.mark.asyncio
          async def test_no_existing_fetches_all(self, listing_html, article_html):
              items, calls = await self._fetch_with_existing(set(), listing_html, article_html)
              assert len(items) == 3  # 兼容模式：未设置 existing 抓全部
      ```
      `uv run pytest tests/test_services/test_web_connector.py -k Incremental` → RED

- [ ] Step 2: 实现 `set_existing_ids` + `__init__` 初始化
      ```python
      def __init__(self, config: dict[str, Any]):
          super().__init__(config)
          self._existing_urls: set[str] | None = None

      def set_existing_ids(self, urls: set[str]) -> None:
          """注入已收录的规范化 URL 集合；fetch 阶段二跳过这些链接的正文抓取。"""
          self._existing_urls = set(urls)
      ```
      fetch 阶段二已含过滤逻辑（Task 1 Step 2 已写 `if self._existing_urls is not None and url in self._existing_urls: continue`），此处仅补 `__init__`，可移除 Task 1 Step 6 的临时 `hasattr` 兜底。

- [ ] Step 3: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_web_connector.py -k Incremental` → 通过

- [ ] Step 4: 回归
      `uv run pytest tests/test_services/test_web_connector.py` → 全绿

---

### task-4：_is_article_page 重写（URL 形态三规则 + 正文裁决）

**目标：** 废弃 HTML 信号打分（实测无区分度），改为 article_url_pattern 优先 + base_url 恒 listing + URL 形态排除三规则 + 正文裁决（min_content_length 内容质量门）。

**Covers:** R05（min_content_length 部分）, R21, R26
**TDD 策略：** 🟢 纯逻辑

**涉及文件：** `src/cyberpulse/services/web_connector.py`、`tests/test_services/test_web_connector.py`

- [ ] Step 1: 写 `TestWebScraperConnectorArticleDetection` 测试（先 RED）
      ```python
      class TestWebScraperConnectorArticleDetection:
          NAV_BLACKLIST = {"about", "contact", "team", "terms", "privacy",
                           "policy", "careers", "tags", "category", "archive"}

          def test_pattern_priority(self):
              connector = WebScraperConnector({
                  "base_url": "https://example.com/insights",
                  "article_url_pattern": r"/insights/",
              })
              assert connector._is_article_page("https://example.com/insights/post", "<html></html>")

          def test_base_url_always_listing(self):
              connector = WebScraperConnector({"base_url": "https://example.com/insights"})
              # 旧信号 3/4 命中（长文本 h1/链接密度/canonical）也不得判为文章
              html = "<html><body><h1>Operator Insightsfor Cybersecurity Founders.</h1>" + "<p>x</p>" * 300 + "</body></html>"
              assert not connector._is_article_page("https://example.com/insights", html)

          def test_same_path_excluded(self):
              connector = WebScraperConnector({"base_url": "https://example.com/insights"})
              assert not connector._is_article_page("https://example.com/insights?page=2", "")

          def test_numeric_segment_excluded(self):
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              assert not connector._is_article_page("https://example.com/articles/page/2", "")

          def test_nav_word_excluded(self):
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              for nav in self.NAV_BLACKLIST:
                  assert not connector._is_article_page(f"https://example.com/{nav}", "")

          def test_nav_word_partial_match_not_excluded(self):
              # 黑名单完全匹配：/about-cybersecurity 不应被误杀
              connector = WebScraperConnector({"base_url": "https://example.com/"})
              assert connector._is_article_page("https://example.com/about-cybersecurity", "")

          def test_article_slug_detected(self):
              connector = WebScraperConnector({"base_url": "https://example.com/insights"})
              assert connector._is_article_page("https://example.com/insights/the-endpoint-wars", "")
      ```
      `uv run pytest tests/test_services/test_web_connector.py -k ArticleDetection` → RED

- [ ] Step 2: 重写 `_is_article_page` + 新增 `_looks_like_article_url`
      ```python
      # 类常量
      NAV_BLACKLIST = frozenset({
          "about", "contact", "team", "terms", "privacy",
          "policy", "careers", "tags", "category", "archive",
      })

      def _is_article_page(self, url: str, html: str) -> bool:
          """文章判定：pattern 优先；base_url 恒 listing；URL 形态三规则。"""
          # 1. article_url_pattern 优先（信任管理员配置）
          article_pattern = self.config.get("article_url_pattern")
          if article_pattern:
              return bool(re.search(article_pattern, url))
          # 2. base_url 恒按 listing
          if url == self.config["base_url"]:
              return False
          # 3. URL 形态排除
          return self._looks_like_article_url(url)

      def _looks_like_article_url(self, url: str) -> bool:
          """URL 形态三规则：同路径 → 排除；末段纯数字 → 排除；导航词黑名单完全匹配 → 排除。"""
          base_path = urllib.parse.urlparse(self.config["base_url"]).path.rstrip("/")
          path = urllib.parse.urlparse(url).path.rstrip("/")
          if base_path and path == base_path:
              return False
          last_segment = path.rsplit("/", 1)[-1] if path else ""
          if last_segment.isdigit():
              return False
          if last_segment.lower() in self.NAV_BLACKLIST:
              return False
          return True
      ```

- [ ] Step 3: fetch 阶段二接入正文裁决（min_content_length 内容质量门）
      在 `fetch()` 阶段二 item 生成后加长度过滤：
      ```python
      min_content_length = self.config.get("min_content_length", 150)
      ...
      item = self._extract_content(html, url, extraction_mode)
      if item and len(item["content"]) >= min_content_length:
          items.append(item)
      ```
      （`min_content_length` 在 fetch 开头读取一次，传入循环）

- [ ] Step 4: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_web_connector.py -k "ArticleDetection or FetchTwoPhase"` → 通过
      （现有 `TestWebScraperConnectorHelpers` 中若有直接断言旧 `_is_article_page` 行为的用例，同步适配）

- [ ] Step 5: 回归
      `uv run pytest tests/test_services/test_web_connector.py` → 全绿

---

### task-5：日期轻量校验

**目标：** `_extract_content_auto` 中 metadata.date 超过 now+7d 回退收录时间（实测 Perplexity 返回页面生成日期）。

**Covers:** R22, R27
**TDD 策略：** 🟢 纯逻辑

**涉及文件：** `src/cyberpulse/services/web_connector.py`、`tests/test_services/test_web_connector.py`

- [ ] Step 1: 写 `TestWebScraperConnectorDateValidation` 测试（先 RED）
      ```python
      class TestWebScraperConnectorDateValidation:
          @pytest.mark.asyncio
          async def test_future_date_falls_back(self):
              # mock trafilatura.extract 返回内容、extract_metadata 返回未来日期
              with patch("trafilatura.extract", return_value="content " * 50), \
                   patch("trafilatura.extract_metadata") as mock_meta:
                  md = MagicMock(); md.title = "T"; md.author = ""; md.date = "2099-01-01"
                  mock_meta.return_value = md
                  connector = WebScraperConnector({"base_url": "https://example.com/"})
                  item = connector._extract_content_auto("<html></html>", "https://example.com/a")
              # 未来日期 → 回退到当前时间附近（非 2099）
              assert item is not None
              assert item["published_at"].year < 2099

          @pytest.mark.asyncio
          async def test_normal_date_kept(self):
              with patch("trafilatura.extract", return_value="content " * 50), \
                   patch("trafilatura.extract_metadata") as mock_meta:
                  md = MagicMock(); md.title = "T"; md.author = ""; md.date = "2026-06-08"
                  mock_meta.return_value = md
                  connector = WebScraperConnector({"base_url": "https://example.com/"})
                  item = connector._extract_content_auto("<html></html>", "https://example.com/a")
              assert item["published_at"].year == 2026 and item["published_at"].month == 6
      ```
      `uv run pytest tests/test_services/test_web_connector.py -k DateValidation` → RED

- [ ] Step 2: `_extract_content_auto` 加日期校验
      ```python
      if metadata:
          title = metadata.title or ""
          author = metadata.author or ""
          if metadata.date:
              published_at = self._parse_date(metadata.date)
              # 轻量校验：明显未来日期（> now + 7d）回退收录时间
              if published_at > self.get_current_utc_time() + timedelta(days=7):
                  logger.warning(
                      f"Suspicious future date '{metadata.date}' for '{url}', "
                      f"falling back to current UTC time"
                  )
                  published_at = self.get_current_utc_time()
      ```
      注意：`timedelta` 需在文件顶部 `from datetime import UTC, datetime, timedelta` 导入（当前已导入 UTC/datetime，补 timedelta）。

- [ ] Step 3: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_web_connector.py -k DateValidation` → 通过

---

### task-6：BrowserFetcher（Playwright 渲染兜底）

**目标：** 新建 `browser_fetcher.py`，`BrowserFetcher.render()` 渲染 HTML；fetch 阶段二在 `render_js: true` 且正文不足时降级。

**Covers:** R05（render_js 部分）, R06, R10, R12, R29
**TDD 策略：** 🟢 纯逻辑（mock playwright）

**涉及文件：** `src/cyberpulse/services/browser_fetcher.py`（新建）、`tests/test_services/test_browser_fetcher.py`（新建）、`src/cyberpulse/services/web_connector.py`

- [ ] Step 1: 写 `tests/test_services/test_browser_fetcher.py`（先 RED，mock playwright）
      ```python
      class TestBrowserFetcher:
          @pytest.mark.asyncio
          async def test_render_success(self):
              with patch("playwright.async_api.async_playwright") as mock_pw:
                  mock_ctx = AsyncMock()
                  mock_page = AsyncMock()
                  mock_page.content.return_value = "<html>rendered</html>"
                  mock_browser = AsyncMock()
                  mock_browser.pages = [mock_page]
                  mock_ctx.chromium.launch_persistent_context.return_value = mock_browser
                  mock_pw.return_value.__aenter__.return_value = mock_ctx
                  fetcher = BrowserFetcher()
                  html = await fetcher.render("https://example.com/")
              assert html == "<html>rendered</html>"
              mock_page.goto.assert_awaited_once()

          @pytest.mark.asyncio
          async def test_render_failure_returns_none(self):
              with patch("playwright.async_api.async_playwright") as mock_pw:
                  mock_ctx = AsyncMock()
                  mock_ctx.chromium.launch_persistent_context.side_effect = Exception("browser failed")
                  mock_pw.return_value.__aenter__.return_value = mock_ctx
                  fetcher = BrowserFetcher()
                  html = await fetcher.render("https://example.com/")
              assert html is None  # 失败返回 None，调用方用 httpx 原始结果
      ```
      `uv run pytest tests/test_services/test_browser_fetcher.py` → RED（模块不存在）

- [ ] Step 2: 实现 `BrowserFetcher`（对齐 transcript_extractor 的 persistent context 模式）
      ```python
      """BrowserFetcher - Playwright headless browser HTML rendering."""

      import logging
      import tempfile
      from typing import Any

      logger = logging.getLogger(__name__)


      class BrowserFetcher:
          """无头浏览器渲染 HTML，为 SPA 站点提供兜底。按源启用（render_js: true）。"""

          def __init__(self, headless: bool = True, timeout: float = 30.0):
              self.headless = headless
              self.timeout = timeout

          async def render(self, url: str) -> str | None:
              """渲染页面返回完整 HTML；失败返回 None（调用方走 httpx 原始结果）。"""
              try:
                  from playwright.async_api import async_playwright

                  async with async_playwright() as p:
                      browser = await p.chromium.launch_persistent_context(
                          user_data_dir=tempfile.mkdtemp(prefix="cyberpulse-bf-"),
                          headless=self.headless,
                          args=[
                              "--disable-blink-features=AutomationControlled",
                              "--mute-audio",
                          ],
                      )
                      try:
                          page = browser.pages[0] if browser.pages else await browser.new_page()
                          await page.goto(
                              url, wait_until="networkidle", timeout=self.timeout * 1000
                          )
                          return await page.content()
                      finally:
                          await browser.close()
              except Exception as e:
                  logger.warning(
                      f"BrowserFetcher render failed for '{url}': {type(e).__name__}: {e}"
                  )
                  return None
      ```

- [ ] Step 3: fetch 阶段二接入 render_js 降级（web_connector.py）
      在 `fetch()` 阶段二：
      ```python
      html = await self._fetch_page_with_retry(client, url)
      item = self._extract_content(html, url, extraction_mode)
      # JS 渲染降级：render_js=true 且正文不足时用浏览器重抓
      if (not item or len(item["content"]) < min_content_length) and self.config.get("render_js"):
          rendered = await self._render_with_browser(url)
          if rendered:
              html = rendered
              item = self._extract_content(html, url, extraction_mode)
      if item and len(item["content"]) >= min_content_length:
          items.append(item)
      ```
      新增私有方法：
      ```python
      async def _render_with_browser(self, url: str) -> str | None:
          """Playwright 渲染页面（render_js=true 时降级用）。"""
          from .browser_fetcher import BrowserFetcher
          fetcher = BrowserFetcher(headless=True)
          return await fetcher.render(url)
      ```
      注意：`min_content_length` 已在 fetch 开头读取（Task 4 Step 3）；`render_js` 降级在 Task 6 才生效（Task 4 无 render_js 时行为不变）。

- [ ] Step 4: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_browser_fetcher.py` → 通过

- [ ] Step 5: 回归
      `uv run pytest tests/test_services/test_web_connector.py tests/test_services/test_browser_fetcher.py` → 全绿

---

### task-7：validate_web_source 质量验证

**目标：** `SourceQualityValidator.validate_web_source()` 抓文章样本评估质量，复用 `_analyze_samples` + 阈值，样本下限放宽（≥1 篇达标即有效），样本不足仅置 pending_review 不判失败。

**Covers:** R09, R30
**TDD 策略：** 🟢 纯逻辑（mock httpx）

**涉及文件：** `src/cyberpulse/services/source_quality_validator.py`、`tests/test_services/test_source_quality_validator.py`（新建）

- [ ] Step 1: 写 `tests/test_services/test_source_quality_validator.py`（先 RED）
      ```python
      class TestValidateWebSource:
          @pytest.fixture
          def validator(self):
              return SourceQualityValidator()

          @pytest.mark.asyncio
          async def test_valid_web_source(self, validator):
              listing_html = '<html><body><a href="https://example.com/a">A</a><a href="https://example.com/b">B</a></body></html>'
              article_html = "<html><body><h1>T</h1><p>" + "x" * 2000 + "</p></body></html>"
              def fake_get(url, follow_redirects=True):
                  r = MagicMock(); r.status_code = 200; r.raise_for_status = MagicMock()
                  r.text = listing_html if "/a" not in str(url) and "/b" not in str(url) else article_html
                  return r
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = MagicMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None; mock_client.get.side_effect = fake_get
                  mock_cls.return_value = mock_client
                  result = await validator.validate_web_source({"base_url": "https://example.com/"})
              assert result.is_valid is True
              assert result.content_type == "article"
              assert result.samples_analyzed == 2

          @pytest.mark.asyncio
          async def test_listing_fetch_failure(self, validator):
              def fake_get(url, follow_redirects=True):
                  r = MagicMock(); r.status_code = 500; r.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=r)
                  return r
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = MagicMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None; mock_client.get.side_effect = fake_get
                  mock_cls.return_value = mock_client
                  result = await validator.validate_web_source({"base_url": "https://example.com/"})
              assert result.is_valid is False
              assert result.rejection_reason is not None

          @pytest.mark.asyncio
          async def test_missing_base_url(self, validator):
              result = await validator.validate_web_source({})
              assert result.is_valid is False
              assert "base_url" in (result.rejection_reason or "")

          @pytest.mark.asyncio
          async def test_no_links_returns_empty(self, validator):
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = MagicMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None
                  r = MagicMock(); r.status_code = 200; r.raise_for_status = MagicMock()
                  r.text = "<html><body>no links</body></html>"
                  mock_client.get.return_value = r
                  mock_cls.return_value = mock_client
                  result = await validator.validate_web_source({"base_url": "https://example.com/"})
              assert result.is_valid is False
              assert result.content_type == "empty"
      ```
      `uv run pytest tests/test_services/test_source_quality_validator.py` → RED

- [ ] Step 2: 实现 `validate_web_source` + `_fetch_web_samples`
      ```python
      async def validate_web_source(
          self, source_config: dict[str, Any]
      ) -> SourceValidationResult:
          """验证 web 源质量：抓文章样本评估正文质量（≥1 篇达标即有效）。"""
          base_url = source_config.get("base_url")
          if not base_url:
              return SourceValidationResult(
                  is_valid=False, content_type="unknown",
                  sample_completeness=0.0, avg_content_length=0,
                  rejection_reason="Missing base_url in configuration",
              )
          # SSRF 保护
          try:
              validate_url_for_ssrf(base_url)
          except SSRFError as e:
              return SourceValidationResult(
                  is_valid=False, content_type="unknown",
                  sample_completeness=0.0, avg_content_length=0,
                  rejection_reason=f"SSRF validation failed: {e}",
              )
          # 抓样本
          samples = await self._fetch_web_samples(base_url, source_config)
          if not samples:
              return SourceValidationResult(
                  is_valid=False, content_type="empty",
                  sample_completeness=0.0, avg_content_length=0,
                  rejection_reason="Could not fetch any article samples from listing",
              )
          # 复用 RSS 分析逻辑与阈值（样本下限放宽：≥1 篇达标即有效）
          analysis = self._analyze_samples(samples)
          if analysis["avg_content_length"] == 0:
              content_type = "empty"
              rejection_reason = "Web source has no content"
          elif analysis["avg_content_length"] < self.MIN_AVG_CONTENT_LENGTH:
              content_type = "summary_only"
              rejection_reason = "Web content quality below threshold"
          else:
              content_type = "article"
              rejection_reason = None
          is_valid = (
              len(samples) >= 1
              and analysis["avg_completeness"] >= self.MIN_AVG_COMPLETENESS
              and analysis["avg_content_length"] >= self.MIN_AVG_CONTENT_LENGTH
          )
          return SourceValidationResult(
              is_valid=is_valid, content_type=content_type,
              sample_completeness=analysis["avg_completeness"],
              avg_content_length=analysis["avg_content_length"],
              rejection_reason=rejection_reason if not is_valid else None,
              samples_analyzed=len(samples),
          )

      async def _fetch_web_samples(
          self, base_url: str, source_config: dict[str, Any]
      ) -> list[dict[str, Any]]:
          """抓 listing 提取链接，抓前 MAX_SAMPLE_ITEMS 篇文章提取正文。"""
          from .web_connector import WebScraperConnector

          connector = WebScraperConnector(source_config)
          # 抓 listing
          try:
              async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                  response = await client.get(base_url, follow_redirects=True)
                  final_url = str(response.url)
                  if final_url != base_url:
                      try:
                          validate_url_for_ssrf(final_url)
                      except SSRFError as e:
                          logger.error(f"SSRF validation failed for redirect {final_url}: {e}")
                          return []
                  response.raise_for_status()
                  html = response.text
          except Exception as e:
              logger.error(f"Failed to fetch listing {base_url}: {e}")
              return []
          # 提取链接（复用 connector 提取代码，保证验证与采集同逻辑）
          links = connector._extract_links(html, base_url)
          if not links:
              return []
          # 抓样本文章
          samples: list[dict[str, Any]] = []
          for url in links[: self.MAX_SAMPLE_ITEMS]:
              try:
                  async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                      response = await client.get(url, follow_redirects=True)
                      response.raise_for_status()
                      article_html = response.text
              except Exception as e:
                  logger.warning(f"Failed to fetch sample article {url}: {e}")
                  continue
              item = connector._extract_content(article_html, url)
              if item:
                  samples.append({
                      "title": item.get("title", ""),
                      "content": item.get("content", ""),
                      "url": url,
                  })
          return samples
      ```

- [ ] Step 3: 运行测试 → GREEN
      `uv run pytest tests/test_services/test_source_quality_validator.py` → 通过

- [ ] Step 4: 回归（RSS 验证不受影响）
      `uv run pytest tests/test_services/` → 全绿

---

### task-8：ingest_source web 分支预查

**目标：** `ingest_source` 对 web 源预查 `Item.url` 注入 `set_existing_ids`，实现增量采集。

**Covers:** R20, R32
**TDD 策略：** 🟢 纯逻辑（mock connector）

**涉及文件：** `src/cyberpulse/tasks/ingestion_tasks.py`、`tests/test_tasks/test_ingestion_tasks.py`

- [ ] Step 1: 写测试（先 RED）
      ```python
      def test_ingest_web_source_sets_existing_ids(
          self, db_session, monkeypatch
      ):
          # 准备 web 源 + 已收录 item
          source = Source(source_id="src_web0001", name="WebTest",
                          connector_type="web", status=SourceStatus.ACTIVE,
                          config={"base_url": "https://example.com/"})
          db_session.add(source); db_session.commit()
          item = Item(source_id=source.source_id, external_id="e1",
                      url="https://example.com/article/1", title="T",
                      raw_content="c", status=ItemStatus.NEW)
          db_session.add(item); db_session.commit()
          # mock connector 记录 set_existing_ids 调用
          calls = {}
          class FakeConnector:
              def set_existing_ids(self, urls): calls["urls"] = urls
              async def fetch(self): return []
          monkeypatch.setattr("src.cyberpulse.tasks.ingestion_tasks.get_connector_for_source",
                              lambda s: FakeConnector())
          from src.cyberpulse.tasks.ingestion_tasks import ingest_source
          ingest_source(source.source_id, job_id=None)
          assert calls["urls"] == {"https://example.com/article/1"}
      ```
      参照 `tests/test_tasks/test_ingestion_tasks.py` 现有 fixture（db_session/source/item 构造方式以文件内既有模式为准，必要时复用现有 `TestIngestSource` 的 setup）
      `uv run pytest tests/test_tasks/test_ingestion_tasks.py -k web_source` → RED

- [ ] Step 2: 实现 web 预查分支
      在 `ingest_source` 的 YouTube 预查分支后追加：
      ```python
      # For web sources, pre-filter existing article URLs to skip
      # content fetching for already-collected articles
      if source.connector_type == "web":
          existing_urls = (
              db.query(Item.url)
              .filter(
                  Item.source_id == source_id,
                  Item.url.isnot(None),
              )
              .all()
          )
          connector.set_existing_ids({r[0] for r in existing_urls})
      ```

- [ ] Step 3: 运行测试 → GREEN
      `uv run pytest tests/test_tasks/test_ingestion_tasks.py -k web_source` → 通过

- [ ] Step 4: 回归
      `uv run pytest tests/test_tasks/test_ingestion_tasks.py` → 全绿

---

### task-9：API 层 web 分支 + ValidationResponse.warnings

**目标：** `test_source` / `validate_source_quality` / `create_source` 增加 web 分支；`ValidationResponse` 新增 `warnings` 字段（R37）。

**Covers:** R16, R17, R18, R31, R37
**TDD 策略：** 🟡 框架集成（API 端点，mock httpx/validator）

**涉及文件：** `src/cyberpulse/api/routers/admin/sources.py`、`src/cyberpulse/api/schemas/source.py`、`tests/test_api/test_admin_sources.py`

- [ ] Step 1: schema 增加 `warnings` 字段
      ```python
      class ValidationResponse(BaseModel):
          ...
          warnings: list[str] = Field(default_factory=list)  # 新增：附加提示（如无 link_pattern）
      ```

- [ ] Step 2: 写 `TestSourceTestWeb` 测试（先 RED，mock httpx）
      ```python
      class TestSourceTestWeb:
          def test_web_source_test_success(self, client, db_session, mock_admin_client):
              source = Source(source_id="src_web0001", name="WebTest",
                              connector_type="web", status=SourceStatus.ACTIVE,
                              config={"base_url": "https://example.com/"})
              db_session.add(source); db_session.commit()
              html = '<html><body><a href="https://example.com/a">A</a></body></html>'
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = AsyncMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None
                  r = MagicMock(); r.status_code = 200; r.raise_for_status = MagicMock(); r.text = html
                  mock_client.get.return_value = r; mock_cls.return_value = mock_client
                  resp = client.post(f"/api/v1/admin/sources/{source.source_id}/test")
              assert resp.status_code == 200
              data = resp.json()
              assert data["test_result"] == "success"
              assert data["items_found"] == 1
              assert any("link_pattern" in w for w in data["warnings"])  # 无 pattern → warning

          def test_web_source_test_http_403(self, client, db_session, mock_admin_client):
              source = Source(source_id="src_web0002", name="WebTest2",
                              connector_type="web", status=SourceStatus.ACTIVE,
                              config={"base_url": "https://example.com/"})
              db_session.add(source); db_session.commit()
              with patch("httpx.AsyncClient") as mock_cls:
                  mock_client = AsyncMock(); mock_client.__aenter__.return_value = mock_client
                  mock_client.__aexit__.return_value = None
                  r = MagicMock(); r.status_code = 403; r.reason_phrase = "Forbidden"
                  r.raise_for_status.side_effect = httpx.HTTPStatusError("403", request=MagicMock(), response=r)
                  mock_client.get.return_value = r; mock_cls.return_value = mock_client
                  resp = client.post(f"/api/v1/admin/sources/{source.source_id}/test")
              assert resp.json()["test_result"] == "failed"
              assert resp.json()["error_type"] == "http_403"
      ```
      参照现有 `TestSourceTest` 的 client/db_session/mock_admin_client fixture 模式
      `uv run pytest tests/test_api/test_admin_sources.py -k TestSourceTestWeb` → RED

- [ ] Step 3: 实现 `_test_web_source` + test_source 分发
      ```python
      # test_source 中，RSS 分支之前插入：
      elif source.connector_type == "web":
          return await _test_web_source(source)

      async def _test_web_source(source: Source) -> TestResult:
          """测试 web 源：抓 base_url，用 _extract_links 统计链接数（link_pattern 命中率）。"""
          source_id = source.source_id
          config = source.config or {}
          base_url = config.get("base_url")
          if not base_url:
              return TestResult(
                  source_id=source_id, test_result="failed",
                  error_type="config", error_message="No base URL configured",
                  suggestion="Configure base_url in source config",
              )
          try:
              start_time = time.time()
              async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                  response = await client.get(
                      base_url,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; CyberPulse/1.0)"},
                  )
                  response.raise_for_status()
                  html = response.text
              elapsed_ms = int((time.time() - start_time) * 1000)
              from ....services.web_connector import WebScraperConnector
              connector = WebScraperConnector(config)
              links = connector._extract_links(html, base_url)
              warnings: list[str] = []
              if not config.get("link_pattern"):
                  warnings.append("未配置 link_pattern，将抓取页面全部链接，建议配置文章链接正则")
              return TestResult(
                  source_id=source_id, test_result="success",
                  response_time_ms=elapsed_ms, items_found=len(links),
                  warnings=warnings,
              )
          except httpx.TimeoutException:
              return TestResult(
                  source_id=source_id, test_result="failed",
                  error_type="timeout", error_message="Connection timeout after 30s",
                  suggestion="检查网络连接或增加超时时间",
              )
          except httpx.HTTPStatusError as e:
              error_type = f"http_{e.response.status_code}"
              suggestion_map = {
                  403: "检查网站反爬策略，可能需要添加 User-Agent 或 IP 白名单",
                  404: "页面不存在，检查 base_url 是否有效",
                  429: "请求过于频繁，降低采集频率或添加请求间隔",
              }
              return TestResult(
                  source_id=source_id, test_result="failed", error_type=error_type,
                  error_message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                  suggestion=suggestion_map.get(e.response.status_code, "检查网站访问权限"),
              )
          except Exception as e:
              logger.error(f"Web source {source_id} test failed: {e}", exc_info=True)
              return TestResult(
                  source_id=source_id, test_result="failed",
                  error_type="connection", error_message=str(e),
                  suggestion="检查 URL 是否正确，确认网络连接",
              )
      ```

- [ ] Step 4: 写 `TestSourceValidateWeb` 测试（先 RED，mock validator）
      ```python
      class TestSourceValidateWeb:
          def test_web_source_validate_success(self, client, db_session, mock_admin_client):
              source = Source(source_id="src_web0003", name="WebTest3",
                              connector_type="web", status=SourceStatus.ACTIVE,
                              config={"base_url": "https://example.com/",
                                      "link_pattern": r"/a"})
              db_session.add(source); db_session.commit()
              with patch("src.cyberpulse.api.routers.admin.sources.SourceQualityValidator") as mock_vc:
                  instance = mock_vc.return_value
                  result = SourceValidationResult(is_valid=True, content_type="article",
                                                  sample_completeness=1.0, avg_content_length=500)
                  instance.validate_web_source = AsyncMock(return_value=result)
                  resp = client.post(f"/api/v1/admin/sources/{source.source_id}/validate")
              data = resp.json()
              assert data["is_valid"] is True
              assert data["content_type"] == "article"
              assert data["warnings"] == []  # 有 link_pattern → 无 warning
              db_session.refresh(source)
              assert source.content_type == "article"
      ```
      （`SourceValidationResult` 从 `source_quality_validator` import；`ValidationResponse` 新增字段生效）
      `uv run pytest tests/test_api/test_admin_sources.py -k TestSourceValidateWeb` → RED

- [ ] Step 5: 实现 `_validate_web_source` + validate 分发
      ```python
      # validate_source_quality 中，RSS 分支之前插入：
      elif source.connector_type == "web":
          return await _validate_web_source(source, db)

      async def _validate_web_source(source: Source, db: Session) -> ValidationResponse:
          """验证 web 源质量：validate_web_source 结果写入 content_type/avg_content_length。"""
          source_id = source.source_id
          config = source.config or {}
          base_url = config.get("base_url")
          if not base_url:
              return ValidationResponse(
                  source_id=source_id, is_valid=False, content_type="unknown",
                  sample_completeness=0.0, avg_content_length=0,
                  rejection_reason="No base_url configured for this source",
              )
          try:
              validator = SourceQualityValidator()
              result = await validator.validate_web_source(config)
              source.content_type = result.content_type
              source.avg_content_length = result.avg_content_length
              if not result.is_valid:
                  source.pending_review = True
                  source.review_reason = result.rejection_reason
                  logger.warning(f"Source {source_id} web validation failed: {result.rejection_reason}")
              else:
                  source.pending_review = False
                  source.review_reason = None
              db.commit()
              warnings: list[str] = []
              if not config.get("link_pattern"):
                  warnings.append("未配置 link_pattern，candidates 会混入导航链接，建议配置")
              return ValidationResponse(
                  source_id=source_id, is_valid=result.is_valid,
                  content_type=result.content_type,
                  sample_completeness=result.sample_completeness,
                  avg_content_length=result.avg_content_length,
                  rejection_reason=result.rejection_reason,
                  samples_analyzed=result.samples_analyzed,
                  warnings=warnings,
              )
          except Exception as e:
              logger.error(f"Web source {source_id} validation error: {e}", exc_info=True)
              return ValidationResponse(
                  source_id=source_id, is_valid=False, content_type="unknown",
                  sample_completeness=0.0, avg_content_length=0,
                  rejection_reason=f"Validation error: {str(e)}",
              )
      ```

- [ ] Step 6: `create_source` 增加 web 验证分支（R18）
      在现有 `if source.connector_type == "rss" ...` 块后追加：
      ```python
      elif source.connector_type == "web" and source.config:
          base_url = source.config.get("base_url")
          if base_url:
              try:
                  validator = SourceQualityValidator()
                  validation_result = await validator.validate_web_source(source.config)
                  content_type = validation_result.content_type
                  avg_content_length = validation_result.avg_content_length
                  if not validation_result.is_valid:
                      pending_review = True
                      review_reason = validation_result.rejection_reason
                      logger.warning(
                          f"Web source quality validation failed for {source.name}: "
                          f"{validation_result.rejection_reason}"
                      )
                  else:
                      logger.info(
                          f"Web source quality validation passed for {source.name}: "
                          f"content_type={content_type}, avg_length={avg_content_length}"
                      )
              except Exception as e:
                  logger.error(f"Web quality validation error for {source.name}: {e}", exc_info=True)
                  pending_review = True
                  review_reason = f"Validation error: {str(e)}"
      ```
      无 link_pattern 提示：`build_source_response` 的 extra_warnings 参数承载（在 create 返回处追加）：
      ```python
      create_warnings = list(warnings or [])
      if source.connector_type == "web" and source.config and not source.config.get("link_pattern"):
          create_warnings.append("未配置 link_pattern，建议配置文章链接正则")
      return build_source_response(new_source, create_warnings if create_warnings else None)
      ```

- [ ] Step 7: 运行全部 API 测试 → GREEN
      `uv run pytest tests/test_api/test_admin_sources.py` → 全绿

---

### task-10：api.sh web 分支与 --config 参数

**目标：** `cmd_sources_create` 支持 web 类型（config 用 base_url）+ `--config` JSON 透传 + help 更新。

**Covers:** R19, R33
**TDD 策略：** 🔵 数据/配置（shell 脚本，用现有 tests/test_api_sh.sh 模式验证）

**涉及文件：** `scripts/api.sh`、`tests/test_api_sh.sh`

- [ ] Step 1: `cmd_sources_create` 增加 `--config` 参数解析
      ```bash
      local config_json=""
      while [[ $# -gt 0 ]]; do
          case "$1" in
              --name)     name="$2"; shift 2 ;;
              --type)     connector_type="$2"; shift 2 ;;
              --url)      url="$2"; shift 2 ;;
              --tier)     tier="$2"; shift 2 ;;
              --config)   config_json="$2"; shift 2 ;;
              --needs-full-fetch) needs_full_fetch="$2"; shift 2 ;;
              *)          shift ;;
          esac
      done
      ```

- [ ] Step 2: 增加 web 分支（在 youtube 分支前）
      ```bash
      if [[ "$connector_type" == "web" ]]; then
          # Web 使用 base_url，透传 --config 的 link_pattern 等
          if [[ -n "$config_json" ]]; then
              data=$(jq -n \
                  --arg name "$name" --arg type "$connector_type" --arg url "$url" \
                  --arg tier "$tier" --argjson cfg "$config_json" \
                  '{name: $name, connector_type: $type, config: ({base_url: $url} + $cfg)} + if $tier != "" then {tier: $tier} else {} end'
              )
          else
              data=$(jq -n \
                  --arg name "$name" --arg type "$connector_type" --arg url "$url" \
                  --arg tier "$tier" \
                  '{name: $name, connector_type: $type, config: {base_url: $url}} + if $tier != "" then {tier: $tier} else {} end'
              )
          fi
      elif [[ "$connector_type" == "youtube" ]]; then
          ... # 现有逻辑不变
      else
          ... # 现有 RSS 逻辑不变
      fi
      ```

- [ ] Step 3: `print_sources_help` 增加 web 类型说明
      ```bash
      echo "  web      - Web page scraping (--url: listing URL, supports --config JSON)"
      ...
      echo "  # Web 源"
      echo "  api.sh sources create --name \"TechOperators\" --type web --url \"https://www.techoperators.com/insights\" --config '{\"link_pattern\":\"\\\\.techoperators\\\\.com/insights/\"}' --tier T1"
      ```

- [ ] Step 4: 更新 `tests/test_api_sh.sh` 增加 web create 用例
      参照现有 create 用例模式，断言请求 body 含 `base_url` 与透传的 link_pattern：
      ```bash
      test_sources_create_web() {
          local response
          response=$(api_post "/api/v1/admin/sources" \
              "$(jq -n --arg name "TO" --arg type "web" --arg url "https://example.com/" \
                  --argjson cfg '{"link_pattern":"\\.example\\.com/a"}' \
                  '{name: $name, connector_type: $type, config: ({base_url: $url} + $cfg)}')")
          echo "$response" | jq -e '.config.base_url == "https://example.com/" and .config.link_pattern == "\\.example\\.com/a"' >/dev/null
      }
      ```

- [ ] Step 5: 运行脚本测试
      `bash tests/test_api_sh.sh` → 通过（若测试需要 mock API 环境，按现有模式运行）

---

### task-11：文档对齐

**目标：** `docs/source-config-examples.md` Web 部分重写为实际配置键（消除缺口 6 的键不一致）。

**Covers:** R23
**TDD 策略：** 🔵 数据/配置

**涉及文件：** `docs/source-config-examples.md`

- [ ] Step 1: 重写「Web 抓取源配置」节（替换现有 `selector`/`pagination`/`timeout` 等假键）
      新表（实际配置键）：
      | 参数 | 类型 | 默认值 | 说明 |
      |---|---|---|---|
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
      Web 源模板 JSON 同步替换；常见问题节的选择器示例改用 `link_selector`/`selectors`；新增已知限制说明（日期可能偏差，精确场景用 manual selectors 的 date 选择器）。

- [ ] Step 2: 验证文档无残留假键
      `grep -n "selector\b\|pagination.*object\|timeout" docs/source-config-examples.md | grep -i web` 检查 Web 节无 `selector`（裸）/`pagination`（对象型）等旧键残留（`link_selector`/`pagination_type` 等新键不受影响）

---

### task-12：E2E 验证（真实源）

**目标：** 用真实源验证整条链路：创建 → test → validate → 采集 → 增量归零。断言动态，不硬编码篇数。

**Covers:** R35, R36
**TDD 策略：** 🔵 数据/配置（真实环境验证）

**涉及文件：** 无（运行验证）；可复用 `deploy/` 环境或本地 `scripts/cyber-pulse.sh deploy --env dev --local`

- [ ] Step 1: 构建并启动环境
      `./scripts/cyber-pulse.sh deploy --env dev --local`（或连接已有环境）
      确认 worker/scheduler/api 健康：`./scripts/api.sh --env dev diagnose`

- [ ] Step 2: 创建 Perplexity 源（base_url 选 `/articles` 以获得更全收录）
      ```bash
      ./scripts/api.sh --env dev sources create --name "Perplexity Research E2E" --type web \
        --url "https://research.perplexity.ai/articles" --tier T1 \
        --config '{"link_pattern":"\\.perplexity\\.ai/articles/","article_url_pattern":"\\.perplexity\\.ai/articles/"}'
      ```
      验证：返回 `config.base_url` 正确

- [ ] Step 3: test + validate
      `./scripts/api.sh --env dev sources test <source_id>` → success，items_found ≥ 1
      `./scripts/api.sh --env dev sources validate <source_id>` → is_valid=true（或 pending_review 但有 samples_analyzed ≥ 1）

- [ ] Step 4: 首次采集
      `./scripts/api.sh --env dev jobs run <source_id>` → job completed，new_items ≥ 1
      `./scripts/api.sh --env dev sources get <source_id>` → total_items ≥ 1

- [ ] Step 5: 二次采集增量归零
      再次 `jobs run` → job result 中 new_items == 0（duplicates = 上次数）；验证 `set_existing_ids` 生效（零正文抓取，job 秒级完成）
      或等待下一个调度周期后检查 `items_last_7d` 不再增长

- [ ] Step 6: TechOperators 存量去重验证
      ```bash
      ./scripts/api.sh --env dev sources create --name "TechOperators E2E" --type web \
        --url "https://www.techoperators.com/insights" --tier T1 \
        --config '{"link_pattern":"\\.techoperators\\.com/insights/","article_url_pattern":"\\.techoperators\\.com/insights/"}'
      ```
      `jobs run` → 注意：存量库中 src_fadea6bb 已收录 13 条（同 URL 规范化后 external_id 一致）——若新源与存量源重复 URL，create_item 的 (source_id, url) 唯一约束下**同源内去重**，不同源不冲突；本步骤主要验证：采集成功 ≥1、URL 规范化后无异常 external_id、二次运行增量归零
      验证 external_id 稳定性：`jobs run` 两次，第二次 new_items == 0

- [ ] Step 7: 汇总 E2E 结果
      记录：各源首次/二次采集的 new_items/duplicates/failed、响应时间、warnings；确认无 500 错误
      输出到临时文件供验收：`echo "Perplexity: first=X, second=0; TechOperators: first=Y, second=0" > /tmp/e2e-web-result.txt`

---

## 自审记录

- **需求覆盖**：R01-R37 全部映射（见各 Task Covers；R06/R10/R12→task-6，R16-R18/R31/R37→task-9，R19/R33→task-10，R23→task-11，R35/R36→task-12）；P1 项（R06/R10/R22/R37）均纳入对应 Task 而非延后
- **Placeholder 扫描**：无 TBD/TODO
- **类型一致性**：`set_existing_ids`/`_normalize_url`/`_looks_like_article_url`/`validate_web_source`/`BrowserFetcher.render` 跨 Task 引用签名一致；`_existing_urls` 初始化在 task-3 完成（task-1 用 `hasattr` 兜底）
- **可构建性**：每步含精确代码块/命令
- **可测试性**：🟢 Task 均先写 RED 测试；🔵 Task（10/11/12）含显式验证命令
- **依赖序**：1→2→3→(4|5|6)→7→8→9→(10|11)→12；task-4 的正文裁决依赖 task-1 的 fetch 结构；task-6 降级逻辑依赖 task-4 的 min_content_length 读取位置
