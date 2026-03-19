# 数据处理流水线

> 所属：[cyber-pulse 技术规格](../2026-03-18-cyber-pulse-design.md)

---

## 采集阶段（Ingestion）

**输入：** Source 配置
**输出：** Item（原始记录）

**处理：**
1. 调用对应的 Connector
2. 获取原始数据（HTML/RSS/JSON）
3. 提取基础字段（title, url, published_at）
4. 生成 `content_hash`
5. 写入 Item 表

---

## 标准化阶段（Normalization）

**输入：** Item
**输出：** 标准化内容（Markdown）

**处理流程：**

### 1. 正文提取
- 使用 `trafilatura` 提取正文
- 处理 JavaScript 动态内容（如需）

### 2. 数据清洗（标准清洗）
- 移除 HTML 标签
- 转换为 Markdown（标题、段落、列表、表格、代码块、引用）
- 统一换行符（`\n`）
- 去除多余空白
- Unicode 标准化
- 移除广告标识（"广告"、"推广"、"推荐阅读"等）

### 3. 元数据补全
- `source_id`, `source_name`, `source_tier`
- `publish_time`（UTC + ISO 8601）
- `connector_type`
- `language`（可选）

### 4. 去重处理
- 计算 `canonical_hash`（标题 + 正文）
- 如已存在相同 hash，复用已有 Content
- 新 Item 关联到该 Content

---

## 质量控制阶段（Quality Gate）

**目标：** 确保进入可用域的数据满足最低质量契约

### 核心字段（必须满足，否则拒绝）

| 字段 | 要求 | 失败处理 |
|------|------|---------|
| `published_at` | 有效日期（非空、合理范围） | ❌ 拒绝 |
| `title` | 非空、长度 ≥ 5 字符 | ❌ 拒绝 |
| `body`（正文） | 非空 | ❌ 拒绝 |
| `url` | 非空、格式合法 | ❌ 拒绝 |

### 可选字段（缺失仅警告，但允许通过）

| 字段 | 要求 | 失败处理 |
|------|------|---------|
| `author` | 可选 | ⚠️ 标记警告 |
| `body_length` | 短文本检测 | ⚠️ 标记"短正文" |

### 统计指标（用于 Source Score，不影响准入）
- 正文纯文本比例
- 广告/噪音比例
- HTML 标签密度
- 标题-正文一致性
- 元数据完整度

### 处理结果
- ✅ **Pass** → 进入 Curated Storage（对外 API 数据源）
- ❌ **Drop** → 不进入可用数据域（记录拒绝原因）