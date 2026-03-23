# CLAUDE.md

## 项目信息

**仓库**: `cyberstrat-forge/cyber-pulse`
**版本**: v1.3.0
**状态**: 生产就绪

**定位**: 内部战略情报采集与标准化系统，向下游分析系统提供清洗后的数据。

**技术栈**: Python 3.11+ | PostgreSQL 15 | FastAPI | SQLAlchemy | APScheduler | Dramatiq | Redis

**进度**: Phase 1-3 全部完成，详见 [CHANGELOG.md](./CHANGELOG.md)

---

## 快速开始

```bash
# 环境变量（必需）
DATABASE_URL=postgresql://cyberpulse:cyberpulse123@localhost:5432/cyberpulse
REDIS_URL=redis://localhost:6379/0

# 初始化
uv sync
uv run alembic upgrade head
```

### 常用命令

```bash
# 测试
uv run pytest                           # 全部测试
uv run pytest tests/test_services/ -v   # 特定目录

# 代码检查
uv run ruff check src/ tests/           # Lint
uv run mypy src/ --ignore-missing-imports  # 类型检查

# 数据库
uv run alembic upgrade head             # 迁移
uv run alembic revision --autogenerate -m "description"  # 创建迁移

# Docker
cd deploy && docker-compose up -d       # 启动服务
docker-compose logs -f                  # 查看日志
docker-compose down                     # 停止服务

# CLI
uv run cyber-pulse --help               # CLI 帮助
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

### 错误处理

- 禁止静默失败：所有 `except` 块必须记录日志或显式处理
- 禁止空 `except: pass`
- 捕获特定异常：避免 `except Exception` 隐藏系统异常
- 数据库并发：`IntegrityError` 需 `rollback()` 后重试或抛出

### 提交前检查

```bash
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest  # 覆盖率 ≥ 80%
```

---

## 版本管理

遵循 [SemVer](https://semver.org/)：`MAJOR.MINOR.PATCH`

发布流程：更新版本号 → 更新 CHANGELOG → 创建标签 → GitHub Release

---

## 文档索引

- [技术规格说明书](./docs/superpowers/specs/2026-03-18-cyber-pulse-design.md)
- [CLI 使用手册](./docs/cli-usage-manual.md)
- [项目总结报告](./docs/2026-03-20-project-summary-report.md)
- [变更日志](./CHANGELOG.md)