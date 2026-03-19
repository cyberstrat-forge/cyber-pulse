# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供项目指导。

## 项目状态

**开发阶段** - Phase 1 核心基础设施和 Phase 2A 数据处理管道已实现。

**实现进度：**
- ✅ Phase 1: 核心基础设施（Models, Database, SourceService, RSSConnector）
- ✅ Phase 2A: 数据处理管道（ItemService, NormalizationService, QualityGateService, ContentService）
- 🚧 Phase 2B-2F: 多源采集、API 服务、调度系统、评分系统、CLI 工具

## 概述

cyber-pulse 是一个内部战略情报采集与标准化系统。采用批处理模式，从多个情报源采集数据，进行标准化处理，通过拉取式 API 向下游分析系统提供清洗后的数据。

**规模假设**：200-500 个情报源，日处理 1,000-10,000 条（可扩展至 2,000 个源，50,000 条/日）。**延迟目标**：原型阶段统一每小时采集，生产版支持分级频率。

## 核心架构

### 数据模型：Source → Item → Content

三个实体，职责分离：

- **Source**：情报源元数据（分级、评分、采集配置）。不存储内容。
- **Item**：每次采集的原始记录（追加写入，按 `external_id`/`url` 去重）。
- **Content**：去重后的逻辑内容实体。多个 Item 可映射到同一 Content（跨源去重）。

### 任务模型：Job → Task

两层执行模型：

- **Job**：调度动作（定时触发或手动触发）。组织任务，不执行处理。
- **Task**：最小执行单元。一个 Task = 一个 Source 在一个处理阶段。

处理链：`Ingestion → Normalization → Quality Gate`

**关键约束**：
- 所有任务必须幂等
- 任务无状态（仅依赖持久化数据）
- 单源并发 = 1

### Source 分级

**等级说明：**

| 级别 | 含义 | 评分范围 |
|------|------|---------|
| T0 | 核心战略源 | ≥ 80 |
| T1 | 重要参考源 | 60-80 |
| T2 | 普通观察源 | 40-60 |
| T3 | 观察/降频源 | < 40 |

**原型阶段调度**：所有活跃 Source 统一每小时调度一次（简化设计），保留 `fetch_interval` 配置为未来分级采集预留。

### 工作流

1. Source Governance（准入、评分）
2. Source-Driven Scheduling（源驱动调度）
3. 通过 Connector 采集内容：
   - `RSSConnector`：复杂度最低，用 guid/link 去重（**包括微信公众号通过 RSSHub 包装**）
   - `APIConnector`：需认证，支持分页
   - `WebScraperConnector`：复杂度最高，需内容提取
   - `MediaAPIConnector`：YouTube 等，需检查字幕是否存在
4. Normalization（提取内容、清洗 HTML、转 Markdown）
5. Quality Gate（仅结构校验，不做语义分析）
6. API Publication（拉取式游标 API）

## 系统边界

**范围内**：源治理、采集、标准化、结构质量过滤、API 输出。

**范围外**：情报分类、战略分析、聚类、决策支持（由下游系统处理）。

## API 模型

拉取式游标模型。消费方自行维护游标状态。通过 `content_id` 实现至少一次语义。

## 设计原则

- 批处理优先（非实时）
- 稳定性优先于性能
- 最终一致性
- 源优先：控制进入什么，而非如何处理

## 技术栈（规划）

**单机原型版（当前）：**

| 层级 | 技术 | 说明 |
|------|------|------|
| 数据库 | PostgreSQL 15 | 单机部署，支持 JSONB |
| 调度器 | APScheduler | 轻量级，无需 Airflow 复杂度 |
| 任务队列 | Dramatiq + Redis | 单 Worker 足够 |
| 存储 | 本地文件系统 | 开发期简单 |
| CLI | Typer + Prompt Toolkit + Rich | 终端 TUI，交互式体验 |
| 正文提取 | trafilatura | 高质量正文提取 |
| HTTP 客户端 | httpx | 支持 async，功能强大 |
| RSS 解析 | feedparser + feedfinder2 | 标准库，稳定可靠 |

**生产版（未来扩展）：**

| 层级 | 技术 | 说明 |
|------|------|------|
| 数据库 | CockroachDB | 分布式，支持横向扩展 |
| 调度器 | Apache Airflow | 批任务编排 |
| 任务队列 | Redis + Celery（或类似） | Worker 协调 |
| 存储 | S3 / MinIO | 原始数据存储 |
| API 认证 | JWT / OAuth 2.0 | 令牌认证 |
| 运行时 | Python（主） | Connector 实现 |

## 文档索引

所有设计文档位于 `docs/` 目录：

**最新设计文档（2026-03-18）：**

| 文档 | 描述 |
|------|------|
| superpowers/specs/2026-03-18-cyber-pulse-design.md | v1.1 技术规格说明书（最新完整设计） |

**历史设计文档：**

| 文档 | 描述 |
|------|------|
| 系统架构.md | 整体架构 |
| Core Data Model 设计.md | 数据模型详情 |
| Task Model 设计说明.md | 任务执行模型 |
| Source 分级模型设计说明.md | 分级体系 |
| Source Governance Model.md | 源管理 |
| Source Score v2.2.md | 源评分体系 |
| Source Connector 模型.md | Connector 实现 |
| 业务 Workflow.md | 业务流程 |
| 时效性设计说明.md | 延迟设计 |
| 数据服务接口规范.md | API 规范 |
| NFR Specification v1.0.md | 非功能需求规格 |
| NFR 说明.md | NFR 说明 |
| 战略情报框架.md | 战略情报框架 |
| 开源数据采集工具.md | 开源采集工具 |

## 设计阶段工作流

1. **新建文档**：文件名使用 `YYYY-MM-DD` 前缀
2. **更新文档**：直接编辑，通过 git 保留历史
3. **文档评审**：提交变更，通过 PR 或直接讨论
4. **进入实现**：设计稳定后，创建实现任务

**设计迭代原则：**
- 修改内容直接整合到规范章节，不使用独立的 Q&A 部分
- 所有澄清必须更新到对应的设计文档中
- 使用 v1.x 版本号管理重大修订

## 开发指南

### 常用命令

```bash
# 运行测试
.venv/bin/pytest                                    # 全部测试
.venv/bin/pytest tests/test_services/ -v            # 特定目录

# 代码检查
.venv/bin/ruff check src/                           # Lint
.venv/bin/mypy src/ --ignore-missing-imports        # 类型检查

# 数据库
.venv/bin/alembic upgrade head                      # 迁移
```

### 代码模式

- **Service 层**: 继承 `BaseService`（需要 DB 时），独立服务无需继承
- **ID 格式**: `item_{uuid8}`, `cnt_{YYYYMMDDHHMMSS}_{uuid8}`, `src_{uuid8}`
- **去重模式**: `create_or_get` 需处理 `IntegrityError` 竞态条件
- **类型引用**: 使用 `TYPE_CHECKING` 避免循环导入
- **测试组织**: 按类分组（如 `TestCreateItem`, `TestGetItems`）

### 目录结构

```
src/cyberpulse/
├── models/          # SQLAlchemy 模型
├── services/        # 业务逻辑层
└── database.py      # DB 配置
```