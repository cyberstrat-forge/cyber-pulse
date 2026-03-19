# Cyber Pulse

Cyber Pulse 是一个内部战略情报采集与标准化系统，定位为"数据生产引擎层"。采用批处理模式，从多个情报源采集数据，进行标准化处理，通过拉取式游标 API 向下游分析系统提供清洗后的数据。

## 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 核心基础设施 | ✅ 已完成 | 数据模型、数据库、SourceService、RSSConnector |
| 数据处理管道 | ✅ 已完成 | ItemService、NormalizationService、QualityGateService、ContentService |
| 多源采集 | 🚧 开发中 | APIConnector、WebScraper、MediaAPIConnector |
| API 服务 | 🚧 开发中 | Pull API、认证机制 |
| 调度系统 | 🚧 开发中 | APScheduler 集成 |
| 评分系统 | 🚧 开发中 | Source Score 体系 |
| CLI 工具 | 🚧 开发中 | 交互式终端工具 |

**规模目标**: 200-500 个情报源，日处理 1,000-10,000 条

## 核心功能

- **源治理**：情报源分级管理（T0-T3）、准入评估、等级演化
- **多源采集**：RSS、API、Web 抓取、媒体平台
- **数据标准化**：正文提取、HTML 清洗、Markdown 转换
- **质量控制**：元数据完整性检查、内容质量评估
- **去重机制**：同源去重（Item）、跨源去重（Content）
- **增量 API**：Pull + Cursor 模式，at-least-once 语义

## 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 15
- Redis 7

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -e ".[dev]"

# 配置环境变量
export DATABASE_URL=postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse
export REDIS_URL=redis://localhost:6379/0

# 初始化数据库
alembic upgrade head
```

### 运行测试

```bash
# 运行全部测试
pytest

# 运行特定测试
pytest tests/test_services/ -v

# 代码检查
ruff check src/ tests/
mypy src/ --ignore-missing-imports
```

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    cyber-pulse                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Connector Layer                          │  │
│  │  • RSSConnector (feedparser)                          │  │
│  │  • APIConnector (httpx)      [开发中]                 │  │
│  │  • WebScraper (trafilatura)  [开发中]                 │  │
│  │  • MediaAPIConnector         [开发中]                 │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │    Normalization & Quality Gate (已完成)              │  │
│  │    • 内容抽取 → 清洗 → Markdown → 质量控制             │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │         Source Governance Layer [开发中]              │  │
│  │         • Source Score + 治理 + 等级演化               │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │              PostgreSQL (核心存储)                     │  │
│  │  • Source (永久) • Item (365天) • Content (365天)      │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │              API Layer (FastAPI) [开发中]              │  │
│  │              • 增量拉取 API • API Key 认证              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 核心数据模型

### 实体关系

```
Source → Item → Content
```

| 实体 | 职责 | 去重方式 |
|------|------|----------|
| **Source** | 情报源元数据（分级、评分、采集配置） | - |
| **Item** | 每次采集的原始记录 | `external_id` / `url` |
| **Content** | 去重后的逻辑内容实体 | `canonical_hash` |

### Source 分级

| 等级 | 含义 | 评分范围 |
|------|------|----------|
| T0 | 核心战略源 | ≥ 80 |
| T1 | 重要参考源 | 60–80 |
| T2 | 普通观察源 | 40–60 |
| T3 | 观察/降频源 | < 40 |

## 数据处理流程

```
用户添加 Source
    ↓
[准入评估] → 连接测试 → 首次采集 → 质量评估
    ↓
达标 → 定级为 T2 → 加入调度队列
    ↓
Connector 采集 → Item (原始记录)
    ↓
Normalization (正文提取、清洗、Markdown)
    ↓
Quality Gate (数据结构质量控制)
    ↓
达标 → 关联/创建 Content
    ↓
下游系统通过 Pull API 拉取
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 运行时 | Python 3.11+ |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 |
| 调度器 | APScheduler |
| 任务队列 | Dramatiq + Redis |
| 正文提取 | trafilatura |
| HTTP 客户端 | httpx |
| RSS 解析 | feedparser |
| CLI 工具 | Typer + Rich |

## 目录结构

```
cyber-pulse/
├── src/cyberpulse/
│   ├── models/              # SQLAlchemy 模型
│   ├── services/            # 业务逻辑层
│   │   ├── source_service.py
│   │   ├── item_service.py
│   │   ├── normalization_service.py
│   │   ├── quality_gate_service.py
│   │   └── content_service.py
│   ├── connectors/          # 采集器
│   ├── database.py          # DB 配置
│   └── config.py            # 配置管理
├── tests/                   # 测试用例
├── docs/                    # 设计文档
└── pyproject.toml           # 项目配置
```

## 开发指南

详细开发规范请参考 [CLAUDE.md](./CLAUDE.md)

### 代码规范

- **Service 层**: 继承 `BaseService`（需 DB 时）
- **ID 格式**: `item_{uuid8}`, `cnt_{YYYYMMDDHHMMSS}_{uuid8}`, `src_{uuid8}`
- **去重模式**: `create_or_get` 需处理 `IntegrityError` 竞态条件
- **错误处理**: 禁止静默失败，所有 `except` 块必须记录日志

### 提交前检查

```bash
ruff check src/ tests/     # Lint
mypy src/                  # 类型检查
pytest                      # 测试
```

## 文档

- [技术规格说明书](./docs/superpowers/specs/2026-03-18-cyber-pulse-design.md)
- [Phase 1 实现计划](./docs/superpowers/plans/2026-03-18-cyber-pulse-phase1-implementation.md)
- [Phase 2 实现计划](./docs/superpowers/plans/2026-03-19-cyber-pulse-phase2-implementation.md)

## 许可证

[MIT License](./LICENSE)