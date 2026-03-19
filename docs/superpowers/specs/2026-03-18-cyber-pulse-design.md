# cyber-pulse 单机原型版技术规格说明书

**版本：** v1.1
**日期：** 2026-03-18
**作者：** 老罗
**状态：** 已批准

---

## 文档导航

本文档是 cyber-pulse 技术规格的总入口。详细设计请参考以下子文档：

| 文档 | 说明 |
|------|------|
| [01-data-model.md](./design/01-data-model.md) | 核心数据模型（Source、Item、Content） |
| [02-source-governance.md](./design/02-source-governance.md) | Source 分级、准入、演化规则 |
| [03-connector.md](./design/03-connector.md) | Connector 体系（RSS、API、Web、Media） |
| [04-pipeline.md](./design/04-pipeline.md) | 数据处理流水线（采集、标准化、质量控制） |
| [05-source-score.md](./design/05-source-score.md) | Source Score 评分系统 |
| [06-api-service.md](./design/06-api-service.md) | API 服务（Pull + Cursor） |
| [07-cli-tool.md](./design/07-cli-tool.md) | CLI 交互式终端工具 |
| [08-error-handling.md](./design/08-error-handling.md) | 错误处理与诊断工具 |
| [09-operations.md](./design/09-operations.md) | 部署、运维、监控 |
| [10-nfr.md](./design/10-nfr.md) | 非功能需求（性能、安全、可扩展性） |

---

## 1. 项目概述

### 1.1 目标与定位

cyber-pulse 是一个**内部战略情报采集与标准化系统**，定位为"数据生产引擎层"，负责：

- 从多个情报源自动化采集数据
- 内容抽取与结构化处理
- 数据清洗与标准化（转为 Markdown）
- 数据结构质量控制
- 增量更新机制
- 通过拉取式 API 向下游分析系统提供数据

**关键定位：**
- ✅ **职责分离**：只负责数据生产，不负责情报分析
- ✅ **下游系统**：cyber-nexus（情报分析应用）负责长期存储情报卡片、主题报告等战略资产
- ✅ **数据保留**：cyber-pulse 数据保留 1 年，长期价值数据由 cyber-nexus 保存

---

### 1.2 单机原型范围

**本次实现范围（v1 单机原型）：**
- ✅ 单机部署，适合开发验证
- ✅ 支持 200-500 个情报源
- ✅ 日处理量 1,000-10,000 条
- ✅ 核心功能完整（采集、标准化、数据结构质量控制、API 服务）
- ✅ 完整的 Source Governance 体系

**暂不实现：**
- ❌ 分布式部署
- ❌ 大数据架构（Kafka、Flink 等）
- ❌ 消息队列（单机场景不需要）
- ❌ 多租户模式

---

### 1.3 与生产版的差异

| 方面 | 单机原型版 | 生产版 |
|------|-----------|--------|
| 数据库 | PostgreSQL | CockroachDB |
| 调度器 | APScheduler | Airflow |
| 任务队列 | Dramatiq | Celery + Redis Cluster |
| 存储 | 本地文件系统 | S3/MinIO |
| 消息组件 | 无 | Kafka（如需） |
| 部署方式 | `docker-compose up` | Kubernetes |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    cyber-pulse (单机原型)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Connector Layer                          │  │
│  ├───────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  内置 Connector (轻量)         外部服务 Connector      │  │
│  │  • RSS (feedparser)           • RSSHub (包装为 RSS)   │  │
│  │  • API (httpx)                • FreshRSS (订阅模式)   │  │
│  │  • Web (trafilatura)          • Nifi (HTTP 推送)      │  │
│  │  • Media (google-api)         • ...                   │  │
│  │                                                       │  │
│  └───────────────┬───────────────────────┬───────────────┘  │
│                  │                       │                  │
│  ┌───────────────▼───────────────────────▼───────────────┐  │
│  │           Normalization & Quality Gate                │  │
│  │      (内容抽取 → 清洗 → 质量控制 → 标准化)             │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              Source Governance Layer                  │  │
│  │      (Source Score + 治理 + 等级演化)                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              PostgreSQL (核心存储)                     │  │
│  │  • Source 表 (永久)                                    │  │
│  │  • Item 表 (365 天)                                    │  │
│  │  • Content 表 (365 天)                                 │  │
│  │  • api_clients 表 (永久)                               │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              API Layer (FastAPI)                      │  │
│  │      • 增量拉取 API (Pull + Cursor)                    │  │
│  │      • API Key 认证                                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              APScheduler (调度器)                      │  │
│  │      • 统一调度频率（原型阶段简化）                    │  │
│  │      • 默认每小时一次（所有活跃 Source）               │  │
│  │      • 支持手动触发                                    │  │
│  │      • 保留 fetch_interval 配置（未来分级预留）       │  │
│  └───────────────────────────────────────────────────────┘  │
│                  │                                           │
│  ┌───────────────▼───────────────────────────────────────┐  │
│  │              Dramatiq (任务队列)                       │  │
│  │      • 采集任务                                          │  │
│  │      • 标准化任务                                        │  │
│  │      • 质量控制任务                                      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              CLI 工具 (终端 TUI)                        │  │
│  │      • source / job / content / client 管理             │  │
│  │      • config / log / diagnose 诊断工具                 │  │
│  │      • 交互式模式 (类似 Claude Code)                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 技术栈选型

| 层级 | 技术 | 说明 |
|------|------|------|
| **运行时** | Python 3.11+ | 主语言，生态成熟 |
| **Web 框架** | FastAPI | 类型安全，自动生成 API docs |
| **数据库** | PostgreSQL 15 | 单机部署简单，支持 JSONB |
| **调度器** | APScheduler | 单机调度，无需 Airflow 复杂度 |
| **任务队列** | Dramatiq + Redis | 轻量级，单 worker 足够 |
| **缓存** | Redis | 去重、状态管理、速率控制 |
| **存储** | 本地文件系统 | 开发期直接写入本地目录 |
| **CLI 工具** | Typer + Prompt Toolkit + Rich | 终端 TUI，交互式体验 |
| **正文提取** | trafilatura | 高质量正文提取 |
| **HTTP 客户端** | httpx | 支持 async，功能强大 |
| **RSS 解析** | feedparser + feedfinder2 | 标准库，稳定可靠 |

---

### 2.3 数据流

```
用户添加 Source
    ↓
[检查重复] - 检查 name 或 URL 是否已存在
    ↓ (重复) 标记为重复，提示用户
    ↓ (不存在)
[快速准入评估]
  • 连接测试
  • 首次采集（5-10 条样本）
  • 质量评估（元数据、正文、噪音）
    ↓
达标 → 定级为 T2 → 立即加入调度队列
    ↓
APScheduler 统一调度（每小时触发所有活跃 Source）
    ↓
Connector 采集原始数据 → Item
    ↓
Normalization（正文提取、清洗、转 Markdown）
    ↓
Quality Gate（数据结构质量控制）
    ↓
达标 → 关联/创建 Content → 写入数据库
    ↓
Source Score 更新（统计反馈）
    ↓
cyber-nexus 通过 Pull API 拉取增量数据
```

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| **Source** | 情报来源，如"安全客"、"FreeBuf" |
| **Item** | 每次采集的原始记录 |
| **Content** | 去重后的逻辑内容实体 |
| **Connector** | 采集器，如 RSSConnector、WebScraper |
| **Curated Storage** | 通过质量控制后的标准化数据存储 |
| **Pull API** | 拉取式增量数据接口 |
| **Cursor** | 增量游标，用于标记消费位置 |
| **Source Score** | 情报来源评分系统 |
| **T0/T1/T2** | Source 分级（核心/重要/普通） |
| **iNBox** | cyber-nexus 的本地数据目录 |

---

### B. 参考文档索引

| 文档 | 说明 |
|------|------|
| `docs/2026-03-17 cyber-pulse 系统架构.md` | 整体架构 |
| `docs/2026-03-17 cyber-pulse Core Data Model 设计.md` | 核心数据模型 |
| `docs/2026-03-17 cyber-pulse Source Governance Model.md` | 源治理模型 |
| `docs/2026-03-17 cyber-pulse Source Score v2.2.md` | 源评分体系 |
| `docs/2026-03-17 cyber-pulse 数据服务接口规范.md` | API 规范 |
| `docs/2026-03-17 cyber-pulse NFR Specification v1.0.md` | 非功能需求 |

---

### C. 技术栈依赖清单

**Python 依赖（requirements.txt）：**

```txt
# Web 框架
fastapi>=0.104.0
uvicorn>=0.24.0

# 数据库
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
alembic>=1.12.0

# 调度器
apscheduler>=3.10.0

# 任务队列
dramatiq>=1.14.0
redis>=5.0.0

# HTTP 客户端
httpx>=0.25.0

# RSS 处理
feedparser>=6.0.10
feedfinder2>=0.0.4

# 正文提取
trafilatura>=1.6.0
beautifulsoup4>=4.12.0

# 媒体 API
google-api-python-client>=2.100.0

# CLI 工具
typer>=0.9.0
prompt_toolkit>=3.0.0
rich>=13.0.0
pygments>=2.15.0

# 工具库
python-dateutil>=2.8.2
pydantic>=2.0.0
```

---

## 修订记录

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v1.0 | 2026-03-18 | 老罗 | 初始版本 |
| v1.1 | 2026-03-18 | 老罗 | 整合 Q&A 澄清，修正术语，完善细节 |
| v1.2 | 2026-03-19 | 老罗 | 拆分文档，实现渐进式上下文加载 |

**v1.1 主要更新：**
- ✅ 统一调度频率（原型阶段简化）
- ✅ Source 评分低的提醒机制
- ✅ API 响应增加 `source_score` 和 `source_quality_metrics`
- ✅ 微信公众号采集方案（RSSHub）
- ✅ 消费者实现样例（cyber-nexus）
- ✅ content get 命令增强（时间过滤、多条件）
- ✅ 交互式界面详细行为规范
- ✅ 硬件要求文档

---

**文档结束**