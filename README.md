# Cyber Pulse

Cyber Pulse 是一个内部战略情报采集与标准化系统，定位为"数据生产引擎层"。采用批处理模式，从多个情报源采集数据，进行标准化处理，通过拉取式游标 API 向下游分析系统提供清洗后的数据。

## 项目状态

**当前版本**: v1.5.0 (生产就绪)

| 模块 | 状态 | 说明 |
|------|------|------|
| 核心基础设施 | ✅ 已完成 | 数据模型、数据库、SourceService、RSSConnector |
| 数据处理管道 | ✅ 已完成 | ItemService、NormalizationService、QualityGateService |
| 多源采集 | ✅ 已完成 | RSSConnector、APIConnector、WebConnector、MediaConnector |
| API 服务 | ✅ 已完成 | FastAPI REST API、API Key 认证、Admin API |
| 调度系统 | ✅ 已完成 | APScheduler + Dramatiq + Redis |
| 评分系统 | ✅ 已完成 | SourceScoreService（稳定性、活跃度、质量三维度评分） |
| 生命周期管理 | ✅ 已完成 | JobLifecycleService（任务删除/重试/清理）、Source 清理 |
| 管理脚本 | ✅ 已完成 | api.sh（源管理、任务管理、系统诊断） |
| 端到端集成 | ✅ 已完成 | Docker 部署、E2E 测试、完整文档 |

**规模目标**: 200-500 个情报源，日处理 1,000-10,000 条

## 核心功能

- **源治理**：情报源分级管理（T0-T3）、准入评估、等级演化
- **多源采集**：RSS、API、Web 抓取、媒体平台
- **数据标准化**：正文提取、HTML 清洗、Markdown 转换
- **质量控制**：元数据完整性检查、内容质量评估
- **去重机制**：基于 `canonical_hash` 的内容去重
- **增量 API**：Pull + Cursor 模式，at-least-once 语义

## 快速开始

### 环境要求

- **Docker** (必需)
- **git** (必需)

> 数据库、Redis 等服务均由 Docker 容器提供，无需单独安装。

### 部署方式

项目支持两种部署方式：

| 方式 | 适用场景 | 说明 |
|------|----------|------|
| **生产部署** | 生产环境、测试环境 | 拉取预构建镜像，快速部署 |
| **本地构建部署** | 开发测试、PR 验证 | 本地构建镜像，支持代码修改 |

#### 方式一：生产部署

> 💡 **加速提示**：镜像托管在阿里云容器镜像仓库，中国用户无需配置镜像加速即可快速拉取。

```bash
# 第一步：安装
curl -fsSL https://raw.githubusercontent.com/cyberstrat-forge/cyber-pulse/main/install.sh | bash
cd cyber-pulse

# 第二步：部署（拉取预构建镜像、启动服务）
./scripts/cyber-pulse.sh deploy

# 第三步：使用
# 访问 http://localhost:8000/docs 查看 API 文档
# 使用 api.sh 管理情报源：./scripts/api.sh sources list
```

#### 方式二：本地构建部署

适用于开发测试和 PR 验证场景，详见 [本地部署指南](./docs/local-deployment-guide.md)。

```bash
# 克隆仓库
git clone https://github.com/cyberstrat-forge/cyber-pulse.git
cd cyber-pulse

# 本地构建并部署测试环境
./scripts/cyber-pulse.sh deploy --env test --local

# 获取 Admin Key
docker logs deploy-api-1 2>&1 | grep -A2 "Admin API Key"

# 配置 API 管理工具
./scripts/api.sh configure
```

---

部署完成后，系统将自动：
- 从镜像仓库拉取镜像（生产部署）或本地构建镜像（本地部署）
- 生成安全配置（数据库密码、密钥等）
- 启动所有服务（PostgreSQL、Redis、API、Worker、Scheduler）
- 完成数据库初始化

### 服务组件

| 服务 | 端口 | 说明 |
|------|------|------|
| API | 8000 | FastAPI REST API |
| Worker | - | Dramatiq 任务处理 |
| Scheduler | - | APScheduler 定时调度 |
| PostgreSQL | 5432 (内部) | 数据库 |
| Redis | 6379 (内部) | 任务队列 + 缓存 |

## 管理 API

使用 `api.sh` 脚本管理情报源、任务、客户端等。

### 配置连接

```bash
./scripts/api.sh configure
# 输入 API URL 和 Admin Key
```

### 情报源管理

```bash
./scripts/api.sh sources list                    # 列出所有源
./scripts/api.sh sources get <source_id>         # 查看源详情
./scripts/api.sh sources create --name "名称" --type rss --url "URL"  # 创建源
./scripts/api.sh sources delete <source_id>      # 删除源（软删除，标记为 REMOVED）
./scripts/api.sh sources cleanup                 # 清理已删除的源（物理删除）
./scripts/api.sh sources test <source_id>        # 测试源连接
./scripts/api.sh sources schedule <source_id> --interval 3600  # 设置调度
./scripts/api.sh sources unschedule <source_id>  # 取消调度
./scripts/api.sh sources import opml.xml         # OPML 导入
./scripts/api.sh sources export                  # OPML 导出
```

### 任务管理

```bash
./scripts/api.sh jobs list                       # 列出任务
./scripts/api.sh jobs get <job_id>               # 查看任务详情
./scripts/api.sh jobs run <source_id>            # 触发采集任务
./scripts/api.sh jobs delete <job_id>            # 删除失败任务
./scripts/api.sh jobs retry <job_id>             # 重试失败任务
./scripts/api.sh jobs cleanup [--days 30]        # 清理旧任务
```

### 客户端管理

```bash
./scripts/api.sh clients list                    # 列出客户端
./scripts/api.sh clients create --name "名称"    # 创建客户端
./scripts/api.sh clients rotate <client_id>      # 轮换 API Key
./scripts/api.sh clients suspend <client_id>     # 暂停客户端
./scripts/api.sh clients activate <client_id>    # 激活客户端
```

### 数据查询

```bash
./scripts/api.sh items list                      # 列出情报条目
./scripts/api.sh items get <item_id>             # 查看条目详情
```

### 系统诊断

```bash
./scripts/api.sh diagnose                        # 系统健康诊断
```

## 业务 API

下游系统通过业务 API 拉取标准化后的情报数据。

### 认证

所有业务 API 请求需要 API Key 认证：

```bash
curl -H "Authorization: Bearer <api_key>" http://localhost:8000/api/v1/items
```

### 增量拉取

使用游标实现增量拉取：

```bash
# 首次拉取（从最新开始）
curl -H "Authorization: Bearer <api_key>" \
  "http://localhost:8000/api/v1/items?limit=50"

# 后续拉取（使用返回的 next_cursor）
curl -H "Authorization: Bearer <api_key>" \
  "http://localhost:8000/api/v1/items?cursor=item_abc12345&limit=50"

# 从最早开始拉取
curl -H "Authorization: Bearer <api_key>" \
  "http://localhost:8000/api/v1/items?from=beginning&limit=50"

# 按时间范围过滤
curl -H "Authorization: Bearer <api_key>" \
  "http://localhost:8000/api/v1/items?since=2024-01-01T00:00:00Z&until=2024-01-31T23:59:59Z"
```

### 响应格式

```json
{
  "data": [
    {
      "id": "item_abc12345",
      "title": "情报标题",
      "body": "标准化后的正文内容...",
      "url": "https://example.com/article",
      "author": "作者",
      "published_at": "2024-01-15T10:00:00Z",
      "fetched_at": "2024-01-15T12:00:00Z",
      "completeness_score": 0.85,
      "word_count": 1500,
      "tags": ["安全", "威胁情报"],
      "full_fetch_attempted": true,
      "full_fetch_succeeded": true,
      "source": {
        "source_id": "src_xyz12345",
        "source_name": "情报源名称",
        "source_url": "https://example.com/feed.xml",
        "source_tier": "T1",
        "source_score": 75.0
      }
    }
  ],
  "next_cursor": "item_def67890",
  "has_more": true,
  "count": 50,
  "server_timestamp": "2024-01-15T14:30:00Z"
}
```

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    cyber-pulse                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Connector Layer (services/)              │  │
│  │  • RSSConnector (feedparser)                          │  │
│  │  • APIConnector (httpx)                               │  │
│  │  • WebConnector (trafilatura)                        │  │
│  │  • MediaConnector                                     │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │    Normalization & Quality Gate (services/)           │  │
│  │    • 内容抽取 → 清洗 → Markdown → 质量控制             │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │         Source Governance Layer (services/)           │  │
│  │         • SourceScoreService + 治理 + 等级演化         │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │              PostgreSQL (核心存储)                     │  │
│  │  • Source (永久) • Item (365天) • Job • ApiClient     │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │              API Layer (FastAPI)                      │  │
│  │              • 业务 API • Admin API • API Key 认证     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 核心数据模型

### 实体关系

```
Source ──< Item >── ApiClient
   │
   └──< Job
```

| 实体 | 职责 | 说明 |
|------|------|------|
| **Source** | 情报源 | 元数据、分级、评分、采集配置 |
| **Item** | 情报条目 | 原始内容 + 标准化内容 + 质量指标 |
| **Job** | 异步任务 | 采集任务、导入任务的状态跟踪 |
| **ApiClient** | API 客户端 | 认证、权限管理 |

### Item 字段

| 字段 | 说明 |
|------|------|
| `raw_content` | 原始内容（来自 RSS/网页） |
| `normalized_title` | 标准化标题 |
| `normalized_body` | 标准化正文（Markdown） |
| `canonical_hash` | 内容哈希（用于去重） |
| `meta_completeness` | 元数据完整性评分 |
| `content_completeness` | 内容完整性评分 |
| `full_fetch_attempted` | 是否尝试全文拉取 |
| `full_fetch_succeeded` | 全文拉取是否成功 |

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
达标 → 计算 canonical_hash → 去重
    ↓
下游系统通过 API 拉取
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

## 目录结构

```
cyber-pulse/
├── src/cyberpulse/
│   ├── models/              # SQLAlchemy 模型
│   │   ├── source.py        # Source, SourceTier, SourceStatus
│   │   ├── item.py          # Item, ItemStatus
│   │   ├── job.py           # Job, JobType, JobStatus
│   │   └── api_client.py    # ApiClient, ApiClientStatus
│   ├── services/            # 业务逻辑层
│   │   ├── source_service.py
│   │   ├── source_score_service.py
│   │   ├── item_service.py
│   │   ├── normalization_service.py
│   │   ├── quality_gate_service.py
│   │   ├── rss_connector.py
│   │   ├── api_connector.py
│   │   ├── web_connector.py
│   │   ├── media_connector.py
│   │   ├── full_content_fetch_service.py
│   │   └── source_quality_validator.py
│   ├── api/                 # FastAPI REST API
│   │   ├── routers/         # API 路由
│   │   │   ├── items.py     # 业务 API
│   │   │   ├── health.py    # 健康检查
│   │   │   └── admin/       # Admin API
│   │   └── schemas/         # Pydantic 模型
│   ├── scheduler/           # APScheduler 调度系统
│   ├── tasks/               # Dramatiq 异步任务
│   ├── database.py          # DB 配置
│   └── config.py            # 配置管理
├── scripts/                 # 管理脚本
│   ├── cyber-pulse.sh       # 部署管理
│   └── api.sh               # API 管理
├── tests/                   # 测试用例
├── docs/                    # 文档
├── CHANGELOG.md             # 变更日志
└── pyproject.toml           # 项目配置
```

## 开发指南

详细开发规范请参考 [CLAUDE.md](./CLAUDE.md)

### 提交前检查

```bash
uv run ruff check src/ tests/     # Lint
uv run mypy src/                  # 类型检查
uv run pytest                      # 测试
```

## 文档

| 文档 | 说明 |
|------|------|
| [本地部署指南](./docs/local-deployment-guide.md) | Worktree 环境部署 |
| [情报源配置示例](./docs/source-config-examples.md) | 各类情报源配置 |
| [变更日志](./CHANGELOG.md) | 版本变更记录 |

## 许可证

[MIT License](./LICENSE)