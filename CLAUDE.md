# CLAUDE.md

## 项目信息

**仓库**: `cyberstrat-forge/cyber-pulse`

**状态**: 开发阶段

**进度**:
- ✅ Phase 1: 核心基础设施（Models, Database, SourceService, RSSConnector）
- ✅ Phase 2A: 数据处理管道（ItemService, NormalizationService, QualityGateService, ContentService）
- 🚧 Phase 2B-2F: 多源采集、API 服务、调度系统、评分系统、CLI 工具

## 概述

cyber-pulse 是一个内部战略情报采集与标准化系统。采用批处理模式，从多个情报源采集数据，进行标准化处理，通过拉取式游标 API 向下游分析系统提供清洗后的数据。

**规模**: 200-500 个情报源，日处理 1,000-10,000 条。

## 核心概念

### 数据模型

| 实体 | 职责 |
|------|------|
| **Source** | 情报源元数据（分级、评分、采集配置） |
| **Item** | 每次采集的原始记录（按 `external_id`/`url` 去重） |
| **Content** | 去重后的逻辑内容实体（跨源去重） |

### 任务模型

```
Job（调度动作）→ Task（最小执行单元）
处理链: Ingestion → Normalization → Quality Gate
```

**约束**: 任务幂等、无状态、单源并发=1

### Source 分级

| 级别 | 含义 | 评分 |
|------|------|------|
| T0 | 核心战略源 | ≥80 |
| T1 | 重要参考源 | 60-80 |
| T2 | 普通观察源 | 40-60 |
| T3 | 观察/降频源 | <40 |

### 系统边界

**范围内**: 源治理、采集、标准化、结构质量过滤、API 输出

**范围外**: 情报分类、战略分析、聚类、决策支持

## 设计原则

- 批处理优先（非实时）
- 稳定性优先于性能
- 最终一致性
- 源优先：控制进入什么，而非如何处理

## 技术栈

Python 3.11+ | PostgreSQL 15 | FastAPI | SQLAlchemy | APScheduler | Dramatiq | Redis | trafilatura | httpx | Typer

详细设计见: `docs/superpowers/specs/2026-03-18-cyber-pulse-design.md`

## 开发指南

### 环境配置

```bash
# 环境变量（必需）
DATABASE_URL=postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse
REDIS_URL=redis://localhost:6379/0

# 初始化开发环境
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
```

### 常用命令

```bash
# 测试
.venv/bin/pytest                              # 全部测试
.venv/bin/pytest tests/test_services/ -v      # 特定目录

# 代码检查
.venv/bin/ruff check src/                     # Lint
.venv/bin/mypy src/ --ignore-missing-imports  # 类型检查

# 数据库
.venv/bin/alembic upgrade head                # 迁移
.venv/bin/alembic revision --autogenerate -m "description"  # 创建迁移
```

### 代码模式

- **Service 层**: 继承 `BaseService`（需 DB 时），独立服务无需继承
- **ID 格式**: `item_{uuid8}`, `cnt_{YYYYMMDDHHMMSS}_{uuid8}`, `src_{uuid8}`
- **去重模式**: `create_or_get` 需处理 `IntegrityError` 竞态条件
- **类型引用**: 使用 `TYPE_CHECKING` 避免循环导入
- **测试组织**: 按类分组（如 `TestCreateItem`）

### 目录结构

```
src/cyberpulse/
├── models/          # SQLAlchemy 模型
├── services/        # 业务逻辑层
├── database.py      # DB 配置
└── config.py        # 配置管理
```

## 开发工作流

### Superpowers 流程

| 阶段 | Skill | 产出 |
|------|-------|------|
| 需求分析 | `brainstorming` | `docs/superpowers/specs/YYYY-MM-DD-*.md` |
| 计划编写 | `writing-plans` | `docs/superpowers/plans/YYYY-MM-DD-*.md` |
| 计划执行 | `subagent-driven-development` | 代码实现 |
| 代码审查 | `requesting-code-review` | 审查报告 |
| 分支完成 | `finishing-a-development-branch` | PR/Merge |

### 工具偏好

- **GitHub 操作**: 优先使用 GitHub MCP 工具
- **代码导航**: 优先使用 LSP（goToDefinition、findReferences、hover）
  - 已安装: `pyright-lsp`, `typescript-lsp`

### Git 规范

**分支命名**: `feature/*` | `bugfix/*` | `refactor/*`

**提交格式**: `type: description`

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 重构 |
| `test` | 测试 |

### Git Worktree

**所有开发必须在 feature 分支进行，禁止直接在 main 分支开发。**

```bash
# 创建 worktree
git worktree add .worktrees/feature-xxx -b feature/xxx

# ⚠️ 验证工作目录
pwd  # 应显示 .worktrees/xxx
git branch --show-current  # 应显示 feature/xxx

# 清理
git worktree remove .worktrees/feature-xxx
```

## 代码质量

- **测试覆盖率**: ≥ 80%
- **Lint**: `ruff check` 必须通过
- **类型检查**: `mypy` 必须通过
- **PR 要求**: 所有测试通过、代码审查通过

## 文档

**最新设计**: `docs/superpowers/specs/2026-03-18-cyber-pulse-design.md`

**实现计划**: `docs/superpowers/plans/2026-03-19-cyber-pulse-phase2-implementation.md`

历史设计文档见 `docs/` 目录。