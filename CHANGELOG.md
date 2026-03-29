# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] - 2026-03-28

### Added

#### 两级全文提取策略
- **Level 1**: httpx + trafilatura 直接抓取（快速，无限制）
- **Level 2**: Jina AI Reader 作为降级方案（20 RPM 限制）
- `FullContentFetchService` 实现两级策略自动切换
- `ContentQualityService` 统一内容质量评估和全文提取触发
- `PENDING_FULL_FETCH` 状态：等待全文提取的 Item

#### Redis 分布式 Rate Limiter
- 使用 Redis Sorted Set (ZSET) 实现滑动窗口算法
- 跨进程/跨容器 Rate Limit 同步
- 解决多 Worker 进程导致的 HTTP 429 问题

#### 自动重试机制
- `retry_pending_full_fetch` 定时任务（每 30 分钟）
- 自动重试卡在 PENDING_FULL_FETCH 状态的 Item
- 任务超时配置：10 分钟（适应 Rate Limiting）

#### Job/Source 生命周期管理
- `JobLifecycleService`: 任务删除、重试、清理
- `DELETE /admin/jobs/{job_id}`: 删除失败任务
- `POST /admin/jobs/{job_id}/retry`: 重试失败任务（最多 3 次）
- `POST /admin/jobs/cleanup`: 清理旧任务
- `POST /admin/sources/cleanup`: 物理删除已删除的源（级联删除 items 和 jobs）
- CLI 命令: `jobs delete/retry/cleanup`, `sources cleanup`
- 完整错误处理：数据库回滚、任务分发失败恢复

### Changed

- 内容质量阈值提升：MIN_CONTENT_LENGTH 500（原 100），MIN_WORD_COUNT 50（新增）
- Item 状态流转优化：NORMALIZED → QUALITY_CHECK → PENDING_FULL_FETCH/MAPPED
- Source 创建后自动触发采集任务

### Fixed

- **asyncio.Lock 事件循环绑定问题**：`asyncio.run()` 每次创建新事件循环导致 Lock 绑定失败
- **多进程 Rate Limit 失效**：threading.Lock 无法跨进程同步，改用 Redis 分布式锁
- **内容质量检查未触发全文提取**：检查顺序调整，先检查内容质量再检查元数据

## [1.4.0] - 2026-03-27

### Added

#### API 架构重构
- Admin API 端点统一到 `/api/v1/admin/` 前缀
- 新增 Jobs API：任务创建、状态查询、历史记录
- 新增 Logs API：日志查询、过滤、导出
- 新增 Clients API：客户端管理、权限控制
- 新增 Diagnose API：系统诊断、健康检查
- OPML 导入/导出支持

#### 数据模型增强
- Job 模型：任务跟踪（type, status, result, error tracking）
- Source 模型新增字段：`consecutive_failures`, `last_error_at`, `last_error_message`, `last_job_id`
- Source 模型全文拉取字段：`needs_full_fetch`, `full_fetch_threshold`, `content_type`, `avg_content_length`, `quality_score`
- Item 模型全文拉取字段：`full_fetch_attempted`, `full_fetch_succeeded`
- Item cursor 格式简化：`item_{uuid8}`（移除时间戳前缀）

#### RSS 采集增强
- 自动触发初始采集：创建源后立即启动采集任务
- OPML 导入后自动触发采集
- HTTP 重定向跟随（301/308）
- 默认 User-Agent 头，避免 403 错误
- 内容质量检测和全文拉取触发

#### 部署优化
- `api.sh` 脚本替代 CLI 工具
- 简化部署命令：`./scripts/api.sh configure`、`./scripts/api.sh diagnose`
- 本地测试环境部署指南

### Changed

- CLI 工具已移除，改用 `api.sh` 脚本
- Unhealthy sources 现在在 diagnose 中可见

### Fixed

- CLI JSON 中文编码问题
- IMPORT job 未触发处理的问题
- 静默失败问题：ingestion 触发失败时添加警告
- `api.sh jobs run` 调用正确的 API 端点
- `api.sh sources create --url` 正确映射到 `config.feed_url`

### Documentation

- SQLAlchemy 2.0 Mapped 迁移设计文档
- 全文拉取混合策略设计文档

## [1.3.0] - 2026-03-22

### Added

#### Documentation
- 完整用户文档体系
  - 快速入门教程 (docs/quickstart.md)
  - 部署指南 (docs/deployment-guide.md)
  - API 使用指南 (docs/api-guide.md)
  - API 参考 (docs/api-reference.md)
  - 安全配置指南 (docs/security-guide.md)
  - 故障排查手册 (docs/troubleshooting.md)
  - 备份与恢复指南 (docs/backup-restore.md)
  - 升级迁移指南 (docs/upgrade-guide.md)
  - 情报源配置示例 (docs/source-config-examples.md)
  - 监控与告警指南 (docs/monitoring.md)

### Fixed
- SSRF 防护 DNS 解析失败时改为 fail closed（防止绕过）
- Docker Compose healthcheck 使用 POSTGRES_USER 环境变量

## [1.2.0] - 2026-03-21

### Added

#### diagnose 命令增强
- `diagnose system` 新增 API 服务健康检查
- `diagnose system` 新增 Dramatiq 任务队列状态检查
- `diagnose sources` 新增 Recent Collection Activity 表格，显示采集状态（Fresh/Recent/Stale/Never）
- `diagnose errors` 新增 Rejection Reason 列，显示 Item 被拒绝的具体原因

#### log 命令增强
- `log export` 命令：导出日志到文件，支持 `--since` 和 `--level` 过滤
- `log clear` 命令：清理旧日志条目，支持 `--older-than` 和确认提示
- `log errors` 和 `log search` 新增 `--format json` 选项，支持 JSON 格式输出

### Fixed
- 修复 `tempfile.mktemp` 已弃用警告，改用 `tempfile.mkstemp`（安全加固）
- 修复 `diagnose system` 静默异常吞没问题，添加日志记录
- 修复 `log clear` 数据丢失风险，改用从文件末尾读取并增大限制
- 修复 `diagnose errors` rejection_reason 类型假设未验证问题
- 更新 `diagnose_system()` 和 `diagnose_errors()` 的 docstring

### Documentation
- 更新 CLI 使用手册（docs/cli-usage-manual.md），添加新命令文档

## [1.1.0] - 2026-03-20

### Added

#### Verification System
- `scripts/verify.sh` - 2-level verification script (Level 1: System Readiness, Level 2: Functional Verification)
- `Makefile` with `verify` and `verify-report` targets
- `sources.yaml` template for verification intelligence sources
- `docs/verification-guide.md` - Usage documentation

### Fixed
- Added `DRAMATIQ_BROKER_URL` environment variable to docker-compose.yml
- Fixed scheduler asyncio event loop issue in `scheduler/main.py`
- Fixed Dockerfile build order for editable install

## [1.0.0] - 2026-03-20

### Added

#### Phase 1: Core Infrastructure
- SQLAlchemy models (Source, Item, Content, ApiClient)
- PostgreSQL database with Alembic migrations
- SourceService for source management
- RSSConnector for RSS/Atom feed collection

#### Phase 2A: Data Processing Pipeline
- ItemService for item lifecycle management
- NormalizationService (content extraction, HTML cleaning, Markdown conversion)
- QualityGateService (metadata integrity, content quality, structure validation)
- ContentService for cross-source deduplication

#### Phase 2B: Multi-Source Collection
- APIConnector for REST API data sources
- WebConnector (trafilatura-based web scraping)
- MediaConnector for YouTube and media platforms
- ConnectorFactory for type-based connector creation

#### Phase 2C: API Service
- FastAPI REST API with API Key authentication
- Content API (incremental pull with cursor)
- Source management API
- Client management API
- Health check endpoint

#### Phase 2D: Scheduling System
- APScheduler for scheduled job management
- Dramatiq task queue with Redis broker
- Worker for async task execution
- Scheduler service with job lifecycle management

#### Phase 2E: Scoring System
- SourceScoreService with three-dimension scoring
- Stability (40%), Activity (30%), Quality (30%)
- Tier evolution based on score changes

#### Phase 2F: CLI Tools
- Typer CLI with 7 command modules
- Interactive TUI with auto-completion
- Source, Job, Content, Client, Config, Log, Diagnose commands

#### Phase 3: End-to-End Integration
- Docker Compose deployment (5 services)
- E2E tests (542 lines, complete workflow)
- Dockerfile with security hardening
- CLI usage manual
- Project summary report

### Security
- Environment variable substitution for sensitive data
- API Key format: `cp_live_{hex32}` (avoids GitHub false positives)
- Production Docker image excludes dev dependencies

### Documentation
- Technical specification (`docs/superpowers/specs/`)
- Implementation plans (`docs/superpowers/plans/`)
- CLI usage manual (`docs/cli-usage-manual.md`)
- Design documents (10 files, progressive loading)

### Testing
- 706 test cases
- Unit tests (~600), Integration tests (~80), E2E tests (~26)
- Core modules coverage ≥ 80%

## [0.1.0] - 2026-03-18

### Added
- Initial project structure
- Basic configuration and dependencies

---

[1.5.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.5.0
[1.4.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.4.0
[1.3.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.3.0
[1.0.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v1.0.0
[0.1.0]: https://github.com/cyberstrat-forge/cyber-pulse/releases/tag/v0.1.0