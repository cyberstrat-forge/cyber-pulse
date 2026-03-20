# CLAUDE.md

## 项目信息

**仓库**: `cyberstrat-forge/cyber-pulse`
**状态**: 生产就绪
**版本**: v1.0.0

**进度**: Phase 1-3 全部完成，详见 [CHANGELOG.md](./CHANGELOG.md)

**定位**: 内部战略情报采集与标准化系统，向下游分析系统提供清洗后的数据。

**技术栈**: Python 3.11+ | PostgreSQL 15 | FastAPI | SQLAlchemy | APScheduler | Dramatiq | Redis

详细设计见: `docs/superpowers/specs/2026-03-18-cyber-pulse-design.md`

---

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
.venv/bin/ruff check src/ tests/              # Lint
.venv/bin/mypy src/ --ignore-missing-imports  # 类型检查

# 数据库
.venv/bin/alembic upgrade head                # 迁移
.venv/bin/alembic revision --autogenerate -m "description"  # 创建迁移

# Docker
docker-compose up -d                          # 启动所有服务
docker-compose logs -f                        # 查看日志
docker-compose down                           # 停止服务
```

---

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
├── database.py      # DB 配置
└── config.py        # 配置管理
```

---

## 编码规范

### 代码模式

- **Service 层**: 继承 `BaseService`（需 DB 时），独立服务无需继承
- **ID 格式**: `item_{uuid8}`, `cnt_{YYYYMMDDHHMMSS}_{uuid8}`, `src_{uuid8}`
- **API Key 格式**: `cp_live_{32_hex_chars}`（避免 `sk_live_`，触发 GitHub 误报）
- **去重模式**: `create_or_get` 需处理 `IntegrityError` 竞态条件
- **类型引用**: 使用 `TYPE_CHECKING` 避免循环导入
- **测试组织**: 按类分组（如 `TestCreateItem`）

### 错误处理规范

- **禁止静默失败**：所有 `except` 块必须记录日志或显式处理
- **禁止空 `except: pass`**
- **捕获特定异常**：避免 `except Exception` 隐藏系统异常
- **数据库并发**：`IntegrityError` 需 `rollback()` 后重试或抛出
- **循环安全**：必须有退出条件，避免无限循环

### 提交前检查

```bash
ruff check src/ tests/     # Lint
mypy src/                  # 类型检查
pytest                      # 测试（覆盖率 ≥ 80%）
```

---

## Git 工作流

### 分支规范

- **命名**: `feature/*` | `bugfix/*` | `refactor/*`
- **提交格式**: `type: description`（feat/fix/docs/refactor/test）
- **开发**: 所有开发在 feature 分支进行，禁止直接在 main 开发

### 开发偏好

- **跳过 Worktree**：单任务开发直接在主仓库创建分支，利用 LSP 能力
- **Worktree 场景**：仅用于多任务并行开发

### PR 合并后清理

```bash
git checkout main && git pull origin main
git branch -d feature/xxx
git push origin --delete feature/xxx  # 如未自动删除
```

---

## 开发工作流

### Superpowers 流程

| 阶段 | Skill |
|------|-------|
| 需求分析 | `brainstorming` |
| 计划编写 | `writing-plans` |
| 计划执行 | `subagent-driven-development` |
| 代码审查 | `requesting-code-review` |
| 分支完成 | `finishing-a-development-branch` |

### PR 要求

- 所有检查通过（ruff + mypy + pytest）
- 代码审查通过
- 无静默失败

---

## 版本管理

遵循 [SemVer](https://semver.org/)：`MAJOR.MINOR.PATCH`

- **发布流程**：更新版本号 → 更新 CHANGELOG → 创建标签 → GitHub Release
- **文档同步**：版本发布时更新 README 和 CHANGELOG

---

## 文档索引

- [技术规格说明书](./docs/superpowers/specs/2026-03-18-cyber-pulse-design.md)
- [CLI 使用手册](./docs/cli-usage-manual.md) - 部署、运维、故障排查
- [项目总结报告](./docs/2026-03-20-project-summary-report.md)
- [变更日志](./CHANGELOG.md)