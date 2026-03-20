# CLAUDE.md

## 项目信息

**仓库**: `cyberstrat-forge/cyber-pulse`

**状态**: 开发阶段

**进度**:
- ✅ Phase 1: 核心基础设施（Models, Database, SourceService, RSSConnector）
- ✅ Phase 2A: 数据处理管道（ItemService, NormalizationService, QualityGateService, ContentService）
- ✅ Phase 2B: 多源采集（APIConnector, WebScraperConnector, MediaAPIConnector, Connector Factory）
- ✅ Phase 2C: API 服务（FastAPI REST API, API Key 认证, Content/Source/Client API）
- ✅ Phase 2D: 调度系统（APScheduler + Dramatiq）
- ✅ Phase 2E: 评分系统（SourceScoreService）
- ✅ Phase 2F: CLI 工具（Typer CLI, TUI, 7 个命令模块）
- ✅ Phase 3: 端到端集成（Docker 部署、E2E 测试）

**当前版本**: v1.0.0（生产就绪）

## 快速开始

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
.venv/bin/ruff check src/ tests/              # Lint（含未使用变量检测）
.venv/bin/mypy src/ --ignore-missing-imports  # 类型检查

# 数据库
.venv/bin/alembic upgrade head                # 迁移
.venv/bin/alembic revision --autogenerate -m "description"  # 创建迁移

# Docker
docker-compose up -d                          # 启动所有服务
docker-compose up -d --build                  # 重建并启动
docker-compose logs -f                        # 查看日志
docker-compose down                           # 停止服务
```

## 项目结构

```
src/cyberpulse/
├── models/          # SQLAlchemy 模型
├── services/        # 业务逻辑层
├── api/             # FastAPI REST API
│   ├── routers/     # API 路由
│   └── schemas/     # Pydantic 模型
├── scheduler/       # APScheduler 调度系统
├── tasks/           # Dramatiq 异步任务
├── cli/             # Typer CLI 工具
│   ├── app.py       # 主入口
│   ├── tui.py       # 交互式 TUI
│   └── commands/    # 命令模块
├── database.py      # DB 配置
└── config.py        # 配置管理
```

## 概述

cyber-pulse 是一个内部战略情报采集与标准化系统。采用批处理模式，从多个情报源采集数据，进行标准化处理，通过拉取式游标 API 向下游分析系统提供清洗后的数据。

**规模**: 200-500 个情报源，日处理 1,000-10,000 条。

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

### 设计原则

- 批处理优先（非实时）
- 稳定性优先于性能
- 最终一致性
- 源优先：控制进入什么，而非如何处理

### 技术栈

Python 3.11+ | PostgreSQL 15 | FastAPI | SQLAlchemy | APScheduler | Dramatiq | Redis | trafilatura | httpx | Typer

详细设计见: `docs/superpowers/specs/2026-03-18-cyber-pulse-design.md`

## 编码规范

### 代码模式

- **Service 层**: 继承 `BaseService`（需 DB 时），独立服务无需继承
- **ID 格式**: `item_{uuid8}`, `cnt_{YYYYMMDDHHMMSS}_{uuid8}`, `src_{uuid8}`
- **API Key 格式**: `cp_live_{32_hex_chars}`（避免使用 `sk_live_`，会触发 GitHub push protection 误报）
- **去重模式**: `create_or_get` 需处理 `IntegrityError` 竞态条件
- **路径参数**: 验证格式，无效返回 400（如 `client_id` 需匹配 `cli_[a-f0-9]{16}`）
- **类型引用**: 使用 `TYPE_CHECKING` 避免循环导入
- **测试组织**: 按类分组（如 `TestCreateItem`）

### 错误处理规范

**禁止静默失败**：

```python
# ❌ 错误：吞掉异常，无法追踪问题
except Exception:
    pass

# ✅ 正确：记录日志，保留异常上下文
except Exception as e:
    logging.warning(f"Operation failed, using fallback: {e}")
```

**规则**：
- 所有 `except` 块必须记录日志或显式处理
- 禁止空的 `except: pass`
- 使用 `logging.debug/warning/error` 记录异常上下文
- 下沉异常时保留原始异常信息

### 错误避免清单

基于 PR Review 发现的重复问题：

#### 1. 数据库并发 (IntegrityError 处理)

```python
# create_or_get 模式必须处理竞态
try:
    self.db.commit()
except IntegrityError:
    self.db.rollback()
    existing = self.db.query(Model).filter(...).first()
    if existing:
        return existing
    raise  # 未知 IntegrityError，重新抛出
```

#### 2. 循环安全 (必须有退出条件)

```python
# ❌ 危险：可能无限循环
while condition:
    if rate_limited:
        continue  # 无计数器

# ✅ 正确：添加计数器
max_retries = 3
for attempt in range(max_retries + 1):
    if rate_limited:
        if attempt >= max_retries:
            raise Error("Rate limit exceeded")
        continue
```

#### 3. 异常捕获范围

```python
# ❌ 太宽泛：隐藏 MemoryError、RecursionError
except Exception as e:
    logger.warning(...)
    continue

# ✅ 正确：捕获特定异常
except (ValueError, KeyError, TypeError) as e:
    logger.warning(...)
    continue
except Exception as e:
    logger.error(f"Unexpected: {e}")
    raise
```

**规则**：
- 外部库同理：捕获库特定异常（如 `SQLAlchemyError`、bcrypt 的 `ValueError`）
- 数据库 commit 失败时需 `rollback()` 后处理（关键操作 re-raise，非关键可继续）

#### 4. 测试质量

- 每个测试必须有断言
- 关键错误处理路径必须有测试
- 避免使用 `__bases__[0]` 等脆弱模式

### 提交前检查清单

- [ ] `ruff check src/ tests/` 通过
- [ ] `mypy src/` 通过
- [ ] `pytest` 通过
- [ ] 测试覆盖率 ≥ 80%
- [ ] 无静默失败（空 except 块）

## Git 工作流

### 分支规范

**分支命名**: `feature/*` | `bugfix/*` | `refactor/*`

**提交格式**: `type: description`

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 重构 |
| `test` | 测试 |

### Worktree 使用

**⚠️ 开发偏好：跳过 Worktree**

对于单任务开发场景（无并行开发任务），**直接在主仓库创建分支**，不使用 worktree。
原因：利用 LSP 能力（Pyright 类型检查、代码导航）。

```bash
# 单任务开发流程
git checkout -b feature/xxx
# 开发完成后
git checkout main && git merge feature/xxx
```

**使用 worktree 的场景**：
- 多个并行开发任务
- 需要隔离测试环境
- 长期运行的 feature 分支

**所有开发必须在 feature 分支进行，禁止直接在 main 分支开发。**

```bash
# 创建 worktree（仅在并行开发时使用）
git worktree add .worktrees/feature-xxx -b feature/xxx

# ⚠️ 验证工作目录
pwd  # 应显示 .worktrees/xxx
git branch --show-current  # 应显示 feature/xxx

# 清理
git worktree remove .worktrees/feature-xxx
```

**⚠️ Worktree LSP 配置（如使用 worktree）**

在 worktree 中工作时，Pyright 需要正确识别虚拟环境：

1. **创建 worktree 后，初始化虚拟环境**：
   ```bash
   cd .worktrees/feature-xxx
   python3 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

2. **项目已配置 Pyright**（见 `pyproject.toml`）：`venvPath = "."` 确保 LSP 在当前目录查找 `.venv`。

3. **LSP 诊断异常时**：确认终端工作目录是 worktree 路径，而非主项目路径。

**⚠️ subagent-driven-development 场景（如使用 worktree）**

当使用 `subagent-driven-development` skill 派发子代理在 worktree 中工作时，**LSP 无法动态切换虚拟环境**。子代理应使用以下替代方法：

| 功能 | LSP 方法 | CLI 替代 |
|------|---------|---------|
| 类型检查 | `LSP hover` | `.venv/bin/pyright <file>` |
| 查找定义 | `LSP goToDefinition` | `grep -r "def <name>" src/` |
| 查找引用 | `LSP findReferences` | `grep -r "<symbol>" src/` |
| 查找文件 | - | `glob` 工具 |

**经验规则**：
- 单任务开发：直接在主仓库开发，使用 LSP
- 多任务并行：使用 worktree，子代理使用 CLI 工具

### PR 合并后清理

`finishing-a-development-branch` skill 处理开发完成到创建 PR 的流程。
PR 合并后需手动清理分支：

```bash
# 检查已合并的 PR
gh pr list --state merged --json number,title,headRefName

# 切换到 main 并更新
git checkout main && git pull origin main

# 删除本地分支
git branch -d feature/xxx

# 删除远程分支（如未自动删除）
git push origin --delete feature/xxx
```

**注意**: 此步骤在 skill 流程之外，PR 合并后需主动执行。

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
  - **例外**: 在 worktree 子代理中，LSP 无法识别 worktree 虚拟环境，应使用 CLI 替代：
    - 类型检查: `.venv/bin/pyright <file>`
    - 查找定义: `grep -r "def <name>" src/`
    - 查找引用: `grep -r "<symbol>" src/`

**PR 要求**：
- 所有检查通过
- 代码审查通过
- 无静默失败（空 except 块）

---

## 部署运维

### 生产环境检查清单

- [ ] 环境变量已配置（DATABASE_URL, REDIS_URL）
- [ ] 数据库迁移已执行
- [ ] API Key 已创建并妥善保存
- [ ] 日志目录已创建且可写
- [ ] 定时任务已配置

### 服务启动顺序

```bash
# 1. 启动基础设施
docker-compose up -d postgres redis

# 2. 等待基础设施就绪
docker-compose exec postgres pg_isready

# 3. 启动应用服务
docker-compose up -d api worker scheduler

# 4. 验证服务健康
curl http://localhost:8000/health
```

### 常用运维命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f api
docker-compose logs -f worker

# 重启服务
docker-compose restart api

# 扩展 Worker
docker-compose up -d --scale worker=3

# 手动触发采集
.venv/bin/cyberpulse job run src_xxxxxxxx
```

### 监控指标

| 指标 | 阈值 | 处理 |
|------|------|------|
| 采集失败率 | > 10% | 检查源状态 |
| 队列积压 | > 100 | 扩展 Worker |
| API 响应时间 | > 1s | 性能优化 |
| 数据库连接数 | > 80% | 连接池调优 |

---

## 文档索引

**最新设计**: `docs/superpowers/specs/2026-03-18-cyber-pulse-design.md`

**实现计划**:
- Phase 1: `docs/superpowers/plans/2026-03-18-cyber-pulse-phase1-implementation.md`
- Phase 2: `docs/superpowers/plans/2026-03-19-cyber-pulse-phase2-implementation.md`
- Phase 3: `docs/superpowers/plans/2026-03-19-cyber-pulse-phase3-integration.md`

**运维文档**:
- CLI 使用手册: `docs/cli-usage-manual.md`
- 项目总结报告: `docs/2026-03-20-project-summary-report.md`

历史设计文档见 `docs/` 目录。

---

## 版本管理

### 版本号规范

遵循语义化版本（Semantic Versioning）：`MAJOR.MINOR.PATCH`

| 变更类型 | 版本更新 | 示例 |
|----------|----------|------|
| 不兼容 API 变更 | MAJOR | 1.0.0 → 2.0.0 |
| 新增功能（向后兼容） | MINOR | 1.0.0 → 1.1.0 |
| Bug 修复 | PATCH | 1.0.0 → 1.0.1 |

### 发布流程

```bash
# 1. 更新版本号（pyproject.toml 和 src/cyberpulse/__init__.py）
# 2. 更新 CHANGELOG.md
# 3. 创建标签
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0

# 4. 创建 GitHub Release
gh release create v1.0.0 --title "v1.0.0" --notes-file CHANGELOG.md
```

### CHANGELOG 维护

每次发布需更新 `CHANGELOG.md`，格式参考 [Keep a Changelog](https://keepachangelog.com/)。

---

## 文档维护

### 文档分类

| 类型 | 位置 | 维护频率 | 说明 |
|------|------|----------|------|
| README | `README.md` | 功能变更时更新 | 项目入口，面向用户 |
| CHANGELOG | `CHANGELOG.md` | 每次发布更新 | 版本变更记录 |
| 技术规格 | `docs/superpowers/specs/` | 功能变更时更新 | 设计文档 |
| 实现计划 | `docs/superpowers/plans/` | 计划创建后归档 | 开发计划 |
| 运维文档 | `docs/*.md` | 持续更新 | 操作指南 |
| API 文档 | FastAPI 自动生成 | 代码变更时自动更新 | `/docs` 端点 |
| CLI 文档 | `docs/cli-usage-manual.md` | 命令变更时更新 | CLI 使用指南 |

### 文档更新触发条件

- **版本发布**：更新 README 版本号、CHANGELOG
- **新功能发布**：更新 README 功能列表、CLI 使用手册、API 文档
- **架构变更**：更新 README 项目结构、技术规格
- **流程优化**：更新运维文档、最佳实践
- **Bug 修复**：如影响用户操作，更新相关文档

### README 维护清单

- [ ] 版本号与 pyproject.toml 一致
- [ ] 项目状态反映当前进度
- [ ] 目录结构与源码一致
- [ ] 文档链接有效且完整